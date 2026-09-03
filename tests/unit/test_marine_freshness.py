"""Phase 9 (Tier 1) — real marine-data freshness reporting. Regression guard
against ever labelling archival/reanalysis data as live/real-time."""
from __future__ import annotations

import os
import time

from varuna_source_adapters.marine_freshness import (
    SourceFreshness, _freshness_for, _parse_date_range_from_name, marine_context_report,
)
from pathlib import Path


def test_real_report_never_claims_live_or_real_time():
    report = marine_context_report()
    for source_id, f in report.items():
        assert "live" not in f.honest_label.lower(), f"{source_id} label must never say 'live'"
        assert "real-time" not in f.honest_label.lower() and "real time" not in f.honest_label.lower()


def test_era5_is_labelled_reanalysis_not_live():
    report = marine_context_report()
    assert report["era5"].tier == "reanalysis"
    assert "reanalysis" in report["era5"].honest_label.lower()


def test_missing_source_reports_not_configured_honestly(tmp_path):
    result = _freshness_for("fake_source", "archival", tmp_path / "does_not_exist", "*.nc", "Fake")
    assert result.found is False
    assert result.tier == "not_configured"
    assert "NOT_CONFIGURED" in result.honest_label


def test_date_range_filename_parsing():
    p = Path("era5_mc20_2023-01-11_to_2023-01-17.nc")
    parsed = _parse_date_range_from_name(p)
    assert parsed is not None
    assert parsed.year == 2023 and parsed.month == 1 and parsed.day == 17


def test_filename_without_date_range_returns_none():
    p = Path("some_random_file.nc")
    assert _parse_date_range_from_name(p) is None


def test_age_computed_from_real_file_mtime_when_no_date_range(tmp_path):
    f = tmp_path / "no_date_range_here.csv"
    f.write_text("data")
    old_time = time.time() - 3 * 86400  # 3 days ago
    os.utime(f, (old_time, old_time))
    result = _freshness_for("test_src", "archival", tmp_path, "*.csv", "Test")
    assert result.found is True
    assert result.data_as_of is None
    assert result.age_days is not None
    assert 2.9 <= result.age_days <= 3.1


def test_newest_file_is_selected_when_multiple_exist(tmp_path):
    old = tmp_path / "old.nc"
    new = tmp_path / "new.nc"
    old.write_text("x")
    time.sleep(0.01)
    new.write_text("y")
    result = _freshness_for("test_src", "archival", tmp_path, "*.nc", "Test")
    assert result.file_path.endswith("new.nc")
