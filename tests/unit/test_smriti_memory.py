"""SMRITI v0.1 — persistence, structured similarity, and the advisory-only boundary."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from varuna_smriti.memory import CaseMemory, SmritiStore

pytestmark = pytest.mark.unit


def _store(tmp_path) -> SmritiStore:
    return SmritiStore(tmp_path / "memory.jsonl")


def _mem(case_id: str, **kw) -> CaseMemory:
    base = dict(centroid_lon=-89.7, centroid_lat=29.0, wind_speed_ms=4.0,
                area_km2=10.0, elongation=3.0,
                observed_at=datetime(2023, 1, 15, tzinfo=timezone.utc))
    base.update(kw)
    return CaseMemory(case_id=case_id, **base)


# --------------------------------------------------------------- persistence

def test_stored_case_survives_a_new_store_instance(tmp_path):
    _store(tmp_path).store_case(_mem("A", outcome="confirmed"))
    assert _store(tmp_path).get("A").outcome == "confirmed"


def test_update_is_persisted_and_bumps_updated_at(tmp_path):
    s = _store(tmp_path)
    before = s.store_case(_mem("A")).updated_at
    s.update_case("A", outcome="not_found", lessons=["wind was marginal"])
    reloaded = _store(tmp_path).get("A")
    assert reloaded.outcome == "not_found"
    assert reloaded.lessons == ["wind was marginal"]
    assert reloaded.updated_at >= before


def test_update_of_unknown_case_is_refused(tmp_path):
    with pytest.raises(KeyError, match="no memory for case"):
        _store(tmp_path).update_case("ghost", outcome="x")


def test_update_with_an_unknown_field_is_refused(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("A"))
    with pytest.raises(ValueError, match="unknown CaseMemory field"):
        s.update_case("A", not_a_real_field=1)


def test_a_corrupt_line_does_not_destroy_the_whole_memory(tmp_path):
    """One bad record must not make every future case lose its history."""
    path = tmp_path / "memory.jsonl"
    s = SmritiStore(path)
    s.store_case(_mem("GOOD"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json at all\n")
    recovered = SmritiStore(path)
    assert recovered.get("GOOD") is not None


# ---------------------------------------------------------------- similarity

def test_nearby_same_class_case_outranks_distant_different_class(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("NEAR", top_source_class="vessel_associated",
                      attribution_state="attributed"))
    s.store_case(_mem("FAR", centroid_lon=20.0, centroid_lat=-30.0,
                      wind_speed_ms=14.0, area_km2=0.2, elongation=1.0,
                      top_source_class="coastal",
                      observed_at=datetime(2023, 7, 1, tzinfo=timezone.utc)))
    q = _mem("NEW", top_source_class="vessel_associated", attribution_state="attributed")
    hits = s.retrieve_similar_cases(q).hits
    assert [h.memory.case_id for h in hits][0] == "NEAR"
    assert hits[0].similarity.score > hits[-1].similarity.score


def test_similarity_is_inspectable_component_by_component(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("A", top_source_class="vessel_associated"))
    hit = s.retrieve_similar_cases(_mem("NEW", top_source_class="vessel_associated")).hits[0]
    assert set(hit.similarity.components) >= {"geography", "environment", "morphology"}
    assert hit.similarity.components["source_hypothesis"] == 1.0
    assert 0.0 <= hit.similarity.score <= 1.0


def test_query_never_matches_itself(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("SELF"))
    assert s.retrieve_similar_cases(_mem("SELF")).hits == []


def test_sparse_records_are_excluded_by_the_coverage_floor(tmp_path):
    """
    Two near-empty records trivially agree on the one field they share. That
    similarity is an artefact of missing data, not a real neighbour relation.
    """
    s = _store(tmp_path)
    s.store_case(CaseMemory(case_id="SPARSE", top_source_class="natural_seep"))
    query = CaseMemory(case_id="ALSO_SPARSE", top_source_class="natural_seep")
    assert s.retrieve_similar_cases(query).hits == []          # default floor
    assert s.retrieve_similar_cases(query, min_coverage=0.0).hits  # opt out explicitly


def test_missing_components_are_reported_not_scored_as_zero(tmp_path):
    s = _store(tmp_path)
    s.store_case(CaseMemory(case_id="NO_ENV", centroid_lon=-89.7, centroid_lat=29.0,
                            area_km2=10.0, elongation=3.0))
    hit = s.retrieve_similar_cases(_mem("NEW"), min_coverage=0.0).hits[0]
    assert "environment" in hit.similarity.unavailable
    assert "environment" not in hit.similarity.components
    assert hit.similarity.coverage < 1.0


# ------------------------------------------------------------------ queries

def test_failure_patterns_returns_only_tagged_cases(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("CLEAN", outcome="confirmed"))
    s.store_case(_mem("FAILED", failure_tags=["ood_detection"]))
    assert [h.memory.case_id for h in s.retrieve_failure_patterns(_mem("NEW")).hits] == ["FAILED"]


def test_relevant_evidence_requires_an_outcome_or_a_lesson(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("BARE"))
    s.store_case(_mem("USEFUL", outcome="confirmed"))
    ids = [h.memory.case_id for h in s.retrieve_relevant_evidence(_mem("NEW")).hits]
    assert ids == ["USEFUL"]


def test_prior_outcomes_are_counts_not_a_prediction(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("A", outcome="confirmed"))
    s.store_case(_mem("B", outcome="confirmed"))
    s.store_case(_mem("C", outcome="not_found"))
    counts = s.retrieve_prior_outcomes(_mem("NEW"))
    assert counts == {"confirmed": 2, "not_found": 1}
    assert all(isinstance(v, int) for v in counts.values())


def test_corridor_count_is_a_real_count_within_the_radius(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("IN1"))
    s.store_case(_mem("IN2", centroid_lon=-89.6, centroid_lat=29.1))
    s.store_case(_mem("OUT", centroid_lon=0.0, centroid_lat=0.0))
    assert s.corridor_case_count(-89.7, 29.0, radius_km=50.0) == 2


def test_records_without_coordinates_are_not_counted_in_a_corridor(tmp_path):
    s = _store(tmp_path)
    s.store_case(CaseMemory(case_id="NOGEO", outcome="confirmed"))
    assert s.corridor_case_count(-89.7, 29.0, radius_km=1000.0) == 0


# ------------------------------------------------------- the memory boundary

def test_every_retrieval_is_marked_advisory_only(tmp_path):
    """
    Memory informs; it never decides. If this ever returns False, SMRITI has
    become an authority over current evidence, which it must not be.
    """
    s = _store(tmp_path)
    s.store_case(_mem("A", outcome="confirmed"))
    q = _mem("NEW")
    for retrieval in (s.retrieve_similar_cases(q),
                      s.retrieve_relevant_evidence(q),
                      s.retrieve_failure_patterns(q)):
        assert retrieval.advisory_only is True
        assert "never override current evidence" in retrieval.note


def test_retrieval_preserves_provenance_of_every_remembered_case(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("A", provenance_source="varuna.golden_case_engine",
                      run_id="CRID-abc123",
                      model_versions={"netra": "v0.2"}, outcome="confirmed"))
    hit = s.retrieve_similar_cases(_mem("NEW")).hits[0]
    assert hit.memory.provenance_source == "varuna.golden_case_engine"
    assert hit.memory.run_id == "CRID-abc123"
    assert hit.memory.model_versions == {"netra": "v0.2"}


def test_retrieval_does_not_mutate_the_query_or_the_store(tmp_path):
    s = _store(tmp_path)
    s.store_case(_mem("A", outcome="confirmed"))
    q = _mem("NEW")
    before = q.model_dump()
    s.retrieve_similar_cases(q)
    assert q.model_dump() == before
    assert s.get("NEW") is None      # querying must not enrol the query case
