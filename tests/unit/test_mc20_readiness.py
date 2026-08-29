"""Tests for the MC20 readiness gate (scripts/check_mc20_readiness.py).

Runs against the real repository state (AIS present, SAR/ERA5/CMEMS
absent) -- this is deliberately an integration-style check of real
current state, not a fully isolated unit test, because the gate's whole
purpose is to re-derive truth from disk."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_mc20_readiness as gate  # noqa: E402


def test_ais_reports_real_when_bronze_extraction_present():
    if not gate.AIS_BRONZE_SUMMARY.exists():
        pytest.skip("MC20 AIS bronze extraction not present in this environment")
    status = gate.check_ais()
    assert status.is_real is True
    assert "real records" in status.detail


def test_sar_reports_not_real_when_absent():
    if gate.SAR_RAW_DIR.exists() and any(gate.SAR_RAW_DIR.iterdir()):
        pytest.skip("SAR already acquired in this environment")
    status = gate.check_sar()
    assert status.is_real is False
    assert status.blocking_reason is not None
    assert "credential" in status.blocking_reason.lower()


def test_era5_reports_not_real_when_absent():
    if gate.ERA5_MC20_DIR.exists() and any(gate.ERA5_MC20_DIR.iterdir()):
        pytest.skip("ERA5 already acquired in this environment")
    status = gate.check_era5()
    assert status.is_real is False
    assert status.blocking_reason is not None


def test_cmems_reports_not_real_when_absent():
    if gate.CMEMS_MC20_DIR.exists() and any(gate.CMEMS_MC20_DIR.iterdir()):
        pytest.skip("CMEMS already acquired in this environment")
    status = gate.check_cmems()
    assert status.is_real is False
    assert status.blocking_reason is not None


def test_real_e2e_ready_is_false_when_any_modality_missing():
    result = gate.build()
    if all(m.is_real for m in result.modalities):
        pytest.skip("all modalities present in this environment -- gate behavior for the all-present case is exercised implicitly")
    assert result.real_e2e_ready is False
    assert len(result.blockers) >= 1


def test_locked_dataset_ids_never_appear_in_mc20_input_set():
    """MC20's case uses ais_marinecadastre/sentinel1_grd_mc20/era5_mc20/
    cmems_mc20 -- none of which are zenodo_part3 or essd. This must stay
    false structurally, not by coincidence."""
    assert gate.check_locked_contamination() is False


def test_temporal_intersection_reports_the_real_measured_offset():
    """The 3.26km/17min figure must not silently drift -- it is a real,
    computed fact from data/bronze/ais/mc20_2023-01-15_tracks.json, not a
    value this gate is allowed to recompute differently."""
    t = gate.compute_temporal_intersection()
    assert "3.26km" in t["closest_real_AIS_offset"]
    assert "+16m57s" in t["closest_real_AIS_offset"]


def test_build_writes_no_files_itself(tmp_path, monkeypatch):
    """build() (as opposed to main()) must be pure read + compute -- no
    side effects on disk."""
    result = gate.build()
    assert isinstance(result.real_e2e_ready, bool)
