"""
Track 2, Phase 2/3 -- contract tests for the real AIS SourceAdapter
(`varuna_integration.ais_source.EventAISAdapter`, re-exported at
`varuna_source_adapters.ais`).

These pin the load-bearing behaviors router-datasets-ca flagged as
currently enforced only by reading the code:

  - health_check() is two-level: join_path existing is not enough: the
    bronze file it points at must also exist.
  - fetch() raises rather than returning an empty vessel list when the
    bronze file is missing -- refusing to synthesize is the whole point.
  - is_simulated=False -> EvidenceMode.REAL through fetch_with_mode(), and
    there is no config-based path that upgrades provenance independent of
    what the adapter actually found on disk.

Uses a small local fixture join file (not the full MC20 dataset) so these
run fast and don't depend on the 276MB bronze file for the health-check /
provenance assertions. One test does use the real MC20 join to prove the
adapter's re-export path actually reaches real data end to end.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.schemas import BBox
from varuna_source_adapters.ais import AISAdapter, EventAISAdapter
from varuna_source_adapters.protocol import SourceQuery, fetch_with_mode

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_JOIN_PATH = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1" / "ais" / "event_ais_join.json"


def _fixture_join(tmp_path: Path, bronze_exists: bool) -> Path:
    bronze_path = tmp_path / "bronze_tracks.json"
    if bronze_exists:
        bronze_path.write_text("[]", encoding="utf-8")
    join = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "sar_footprint": {"min_lon": 0.0, "min_lat": 0.0, "max_lon": 1.0, "max_lat": 1.0},
        "t_sar": "2026-01-01T00:00:00+00:00",
        "window_before_hours": 48.0,
        "window_after_hours": 6.0,
        "n_tracks_total": 0,
        "n_tracks_spatially_matched": 0,
        "n_tracks_temporally_matched": 0,
        "n_tracks_temporally_unavailable": 0,
        "closest_temporally_matched": None,
        "raw_source_reference": {"bronze_tracks_path": str(bronze_path)},
        "tracks": [],
    }
    join_path = tmp_path / "event_ais_join.json"
    join_path.write_text(json.dumps(join), encoding="utf-8")
    return join_path


def _query() -> SourceQuery:
    return SourceQuery(
        bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        time_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_end=datetime(2026, 1, 1, tzinfo=timezone.utc),
        product_id="test_ais",
    )


# ───────────────────────── health_check is two-level ─────────────────────────

def test_health_check_false_when_join_path_missing(tmp_path):
    adapter = EventAISAdapter(tmp_path / "does_not_exist.json")
    assert adapter.health_check() is False


def test_health_check_false_when_bronze_file_missing_even_though_join_exists(tmp_path):
    join_path = _fixture_join(tmp_path, bronze_exists=False)
    adapter = EventAISAdapter(join_path)
    assert adapter.health_check() is False, (
        "a join manifest pointing at a vanished bronze file must be False, "
        "not True -- join_path existing is not sufficient"
    )


def test_health_check_true_when_both_join_and_bronze_exist(tmp_path):
    join_path = _fixture_join(tmp_path, bronze_exists=True)
    adapter = EventAISAdapter(join_path)
    assert adapter.health_check() is True


# ───────────────────────── fetch() refuses to synthesize ─────────────────────────

def test_fetch_raises_rather_than_returning_empty_vessel_list(tmp_path):
    join_path = _fixture_join(tmp_path, bronze_exists=False)
    adapter = EventAISAdapter(join_path)
    with pytest.raises(FileNotFoundError, match="refusing to synthesize"):
        adapter.fetch(_query())


def test_fetch_succeeds_when_bronze_file_present(tmp_path):
    join_path = _fixture_join(tmp_path, bronze_exists=True)
    adapter = EventAISAdapter(join_path)
    result = adapter.fetch(_query())
    assert result.is_simulated is False
    assert result.artifact_path.endswith("bronze_tracks.json")


# ───────────────────────── provenance: REAL / UNAVAILABLE, never upgraded ─────────────────────────

def test_is_simulated_false_becomes_evidence_mode_real_through_fetch_with_mode(tmp_path):
    join_path = _fixture_join(tmp_path, bronze_exists=True)
    adapter = EventAISAdapter(join_path)
    result, mode = fetch_with_mode(adapter, _query())
    assert result is not None
    assert mode is EvidenceMode.REAL


def test_health_check_failure_yields_unavailable_not_a_lower_but_present_mode(tmp_path):
    join_path = _fixture_join(tmp_path, bronze_exists=False)
    adapter = EventAISAdapter(join_path)
    result, mode = fetch_with_mode(adapter, _query())
    assert result is None
    assert mode is EvidenceMode.UNAVAILABLE


def test_fetch_exception_yields_unavailable_via_fetch_with_mode(tmp_path):
    # health_check() true (bronze exists at construction time) but the file
    # vanishes before fetch() -- exercises the "fetch() raises" branch of
    # fetch_with_mode(), not just the health_check() branch.
    join_path = _fixture_join(tmp_path, bronze_exists=True)
    adapter = EventAISAdapter(join_path)
    bronze_path = Path(json.loads(join_path.read_text())["raw_source_reference"]["bronze_tracks_path"])
    bronze_path.unlink()
    result, mode = fetch_with_mode(adapter, _query())
    assert result is None
    assert mode is EvidenceMode.UNAVAILABLE


def test_no_configuration_path_upgrades_provenance():
    """`EventAISAdapter.__init__` takes only `join_path` and an optional
    `source_id` label -- there is no settings/config parameter that could
    set `is_simulated` or the resulting EvidenceMode independent of what
    fetch() actually found on disk."""
    import inspect
    sig = inspect.signature(EventAISAdapter.__init__)
    params = set(sig.parameters) - {"self"}
    assert params == {"join_path", "source_id"}, (
        f"unexpected constructor parameters {params} -- any new parameter "
        f"here must not be able to set is_simulated/EvidenceMode directly"
    )


# ───────────────────────── superseded stub stays inert ─────────────────────────

def test_legacy_ais_adapter_stub_is_unrelated_and_unused():
    """The pre-existing 5-line stub is superseded, not deleted (no-delete
    constraint) -- pin that it still does nothing real, so nobody mistakes
    it for the live path."""
    stub = AISAdapter()
    result = stub.fetch_vessels(region="anywhere")
    assert result == {"region": "anywhere", "vessels": []}


# ───────────────────────── real MC20 data, end to end ─────────────────────────

@pytest.mark.skipif(not REAL_JOIN_PATH.exists(), reason="real MC20 Event Gold not present")
def test_real_mc20_join_reachable_through_the_reexported_adapter():
    adapter = EventAISAdapter(REAL_JOIN_PATH)
    assert adapter.health_check() is True
    result, mode = fetch_with_mode(adapter, _query())
    assert result is not None
    assert mode is EvidenceMode.REAL
    assert result.is_simulated is False
