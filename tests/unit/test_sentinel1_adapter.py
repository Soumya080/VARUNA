"""
Sentinel1Adapter (packages/varuna_source_adapters/sentinel1.py) —
WORKSTREAM C, Phase 2. Real local-SAFE-product adapter, mirroring the
existing Era5Adapter/CmemsAdapter honesty pattern: REAL when a local .SAFE
product genuinely exists, UNAVAILABLE (via fetch_with_mode) when it does
not — never a fabricated successful fetch.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.schemas import BBox
from varuna_source_adapters.protocol import SourceQuery, fetch_with_mode
from varuna_source_adapters.sentinel1 import Sentinel1Adapter

pytestmark = pytest.mark.unit

REAL_SAFE_ROOT = Path("data/raw/sentinel1_grd")

_HAS_REAL_SAFE = REAL_SAFE_ROOT.exists() and any(REAL_SAFE_ROOT.rglob("*.SAFE"))


def _query() -> SourceQuery:
    return SourceQuery(
        bbox=BBox(min_lon=-89, min_lat=28, max_lon=-88, max_lat=29),
        time_start=datetime(2023, 1, 15, tzinfo=timezone.utc),
        time_end=datetime(2023, 1, 16, tzinfo=timezone.utc),
        product_id="sentinel1_scene",
    )


def test_missing_directory_is_unavailable_not_fabricated(tmp_path):
    adapter = Sentinel1Adapter(tmp_path / "does_not_exist")
    assert adapter.health_check() is False
    result, mode = fetch_with_mode(adapter, _query())
    assert result is None
    assert mode is EvidenceMode.UNAVAILABLE


def test_empty_directory_is_unavailable(tmp_path):
    empty = tmp_path / "empty_safe_root"
    empty.mkdir()
    adapter = Sentinel1Adapter(empty)
    assert adapter.health_check() is False


def test_fetch_on_unavailable_source_raises_filenotfound(tmp_path):
    adapter = Sentinel1Adapter(tmp_path / "nope")
    with pytest.raises(FileNotFoundError):
        adapter.fetch(_query())


@pytest.mark.skipif(not _HAS_REAL_SAFE, reason="no local .SAFE product under data/raw/sentinel1_grd")
def test_real_safe_product_is_reported_as_real():
    adapter = Sentinel1Adapter(REAL_SAFE_ROOT)
    assert adapter.health_check() is True
    result, mode = fetch_with_mode(adapter, _query())
    assert mode is EvidenceMode.REAL
    assert result is not None
    assert result.is_simulated is False
    assert Path(result.artifact_path).suffix == ".SAFE"
    assert "scene_id=" in result.provenance.notes
    assert result.provenance.source_id == "sentinel1.real"


@pytest.mark.skipif(not _HAS_REAL_SAFE, reason="no local .SAFE product under data/raw/sentinel1_grd")
def test_real_scene_metadata_is_parsed_not_invented():
    adapter = Sentinel1Adapter(REAL_SAFE_ROOT)
    safe_dir = next(REAL_SAFE_ROOT.rglob("*.SAFE"))
    meta = adapter.scene_metadata(safe_dir)
    assert meta.scene_id == safe_dir.stem
    assert meta.product_type == "GRD"
    assert meta.acquisition_start is not None
    assert meta.acquisition_stop is not None
    assert meta.acquisition_start < meta.acquisition_stop
    assert set(meta.polarizations) <= {"VV", "VH", "HH", "HV", "UNKNOWN"}
    assert len(meta.manifest_sha256) == 64  # sha256 hex digest


@pytest.mark.skipif(not _HAS_REAL_SAFE, reason="no local .SAFE product under data/raw/sentinel1_grd")
def test_source_id_and_version_are_stable():
    adapter = Sentinel1Adapter(REAL_SAFE_ROOT)
    assert adapter.source_id == "sentinel1.real"
    assert adapter.ADAPTER_VERSION == "real-v1"
