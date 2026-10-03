"""
Track 2 Phase 1/2 — FetchResult.is_simulated -> EvidenceMode, for every
concrete SourceAdapter that exists today (real: Era5Adapter, CmemsAdapter;
mock: MockEra5Adapter, MockCmemsAdapter, MockAisAdapter, MockSentinelAdapter).

Required matrix, per adapter:
    REAL source        -> EvidenceMode.REAL
    SIMULATED source    -> EvidenceMode.SIMULATED
    unavailable source  -> EvidenceMode.UNAVAILABLE

Sentinel-1, AIS, and static-GIS have no concrete SourceAdapter implementation
yet (ais.py/sentinel1.py/static_gis.py remain unrelated 5-line stubs that do
not subclass SourceAdapter) — there is nothing to wire the helper into for
those, and this file does not fabricate one.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_source_adapters.copernicus_marine import CmemsAdapter
from varuna_source_adapters.era5 import Era5Adapter
from varuna_source_adapters.mock_ais import MockAisAdapter
from varuna_source_adapters.mock_cmems import MockCmemsAdapter
from varuna_source_adapters.mock_era5 import MockEra5Adapter
from varuna_source_adapters.mock_sentinel import MockSentinelAdapter
from varuna_contracts.evidence import Provenance
from varuna_source_adapters.protocol import (
    FetchResult, SourceQuery, evidence_mode_of, fetch_with_mode,
)
from varuna_contracts.schemas import BBox

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
ERA5_DIR = REPO_ROOT / "data" / "raw" / "era5"
CMEMS_DIR = REPO_ROOT / "data" / "raw" / "cmems"


def _query(bbox: BBox | None = None) -> SourceQuery:
    now = datetime.now(timezone.utc)
    return SourceQuery(
        bbox=bbox or BBox(min_lon=70.0, min_lat=10.0, max_lon=75.0, max_lat=15.0),
        time_start=now, time_end=now + timedelta(hours=1),
        product_id="test",
    )


# ───────────────────────── evidence_mode_of: pure mapping ─────────────────────────

def _fetch_result(is_simulated: bool) -> FetchResult:
    return FetchResult(
        artifact_path="/tmp/whatever",
        provenance=Provenance(source_id="test"),
        is_simulated=is_simulated,
    )


def test_evidence_mode_of_maps_is_simulated_false_to_real():
    assert evidence_mode_of(_fetch_result(is_simulated=False)) is EvidenceMode.REAL


def test_evidence_mode_of_maps_is_simulated_true_to_simulated():
    assert evidence_mode_of(_fetch_result(is_simulated=True)) is EvidenceMode.SIMULATED


# ───────────────────────── Mock adapters: always SIMULATED ─────────────────────────

@pytest.mark.parametrize("adapter_factory", [
    MockEra5Adapter, MockCmemsAdapter, MockAisAdapter, MockSentinelAdapter,
])
def test_mock_adapters_report_simulated(adapter_factory):
    adapter = adapter_factory()
    result, mode = fetch_with_mode(adapter, _query())
    assert mode is EvidenceMode.SIMULATED
    assert result is not None
    assert result.is_simulated is True


# ───────────────────────── Real adapters: REAL when data exists ─────────────────────────

cfgrib = pytest.importorskip("cfgrib", reason="cfgrib not installed")


@pytest.mark.skipif(not ERA5_DIR.exists(), reason="no local ERA5 data")
def test_era5_adapter_reports_real():
    adapter = Era5Adapter(grib_dir=ERA5_DIR)
    if not adapter.health_check():
        pytest.skip("no .grib files present under data/raw/era5")
    result, mode = fetch_with_mode(adapter, _query())
    assert mode is EvidenceMode.REAL
    assert result is not None
    assert result.is_simulated is False


@pytest.mark.skipif(not CMEMS_DIR.exists(), reason="no local CMEMS data")
def test_cmems_adapter_reports_real():
    adapter = CmemsAdapter(netcdf_dir=CMEMS_DIR)
    if not adapter.health_check():
        pytest.skip("no .nc files present under data/raw/cmems")
    result, mode = fetch_with_mode(adapter, _query())
    assert mode is EvidenceMode.REAL
    assert result is not None
    assert result.is_simulated is False


# ───────────────────────── Real adapters: UNAVAILABLE when the source isn't there ──

def test_era5_adapter_reports_unavailable_when_directory_missing():
    adapter = Era5Adapter(grib_dir=REPO_ROOT / "data" / "raw" / "does_not_exist_era5")
    result, mode = fetch_with_mode(adapter, _query())
    assert mode is EvidenceMode.UNAVAILABLE
    assert result is None


def test_cmems_adapter_reports_unavailable_when_directory_missing():
    adapter = CmemsAdapter(netcdf_dir=REPO_ROOT / "data" / "raw" / "does_not_exist_cmems")
    result, mode = fetch_with_mode(adapter, _query())
    assert mode is EvidenceMode.UNAVAILABLE
    assert result is None


def test_era5_adapter_reports_unavailable_when_directory_exists_but_empty(tmp_path):
    empty_dir = tmp_path / "empty_era5"
    empty_dir.mkdir()
    adapter = Era5Adapter(grib_dir=empty_dir)
    result, mode = fetch_with_mode(adapter, _query())
    assert mode is EvidenceMode.UNAVAILABLE
    assert result is None


# ───────────────────────── No adapter can claim REAL via config alone ─────────────

def test_fetch_with_mode_never_reads_settings_or_env(monkeypatch):
    """
    fetch_with_mode()'s mode comes only from health_check()/fetch() outcomes.
    Setting an unrelated "production" env var must have zero effect on the
    returned mode for a mock (still-simulated) source.
    """
    monkeypatch.setenv("VARUNA_ENV", "production")
    monkeypatch.setenv("DEMO_MODE", "false")
    result, mode = fetch_with_mode(MockCmemsAdapter(), _query())
    assert mode is EvidenceMode.SIMULATED
    assert result.is_simulated is True
