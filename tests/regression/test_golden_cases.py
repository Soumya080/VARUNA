"""
VARUNA GRID — Golden Regression Cases.

SOFTWARE REGRESSION TESTS — NOT SCIENTIFIC BENCHMARKS.

These tests verify that the system produces deterministic, expected
outputs for known synthetic inputs. They are integration regression
fixtures. They do NOT constitute scientific validation.
M2.2 scientific validation is deferred.
"""
import pytest
from varuna_domain.repositories import (
    InMemoryCaseRepository, InMemoryArtifactRepository, InMemoryEventStore,
)
from varuna_domain.case_workflow import CaseWorkflow
from varuna_domain.entities import CaseStatus


def _make_workflow():
    """Create a workflow backed by in-memory repos (no Docker)."""
    return CaseWorkflow(
        case_repo=InMemoryCaseRepository(),
        artifact_repo=InMemoryArtifactRepository(),
        event_repo=InMemoryEventStore(),
    )


# ─────────── CASE-0001: Strong Lead ───────────

class TestCase0001:
    def test_strong_lead(self):
        from tests.fixtures.case_0001 import generate_case_0001
        fixture = generate_case_0001()
        wf = _make_workflow()
        result = wf.run_full(
            "CASE-0001",
            slick_lons=fixture["slick_lons"],
            slick_lats=fixture["slick_lats"],
            tracks=fixture["tracks"],
            obs_time_hours=fixture["obs_time_hours"],
            seed=fixture.get("seed", 42),
        )
        assert result["status"] == "completed"
        assert result["decision"] == "strong_lead"
        # As of the Tranche 1 provenance/honesty hardening, PhiField.sensitivity
        # is genuinely None (no sensitivity sweep is implemented yet — see
        # phi_builder.py TODO(P1)), and the validity gate correctly refuses to
        # fabricate a passing sensitivity check for it. The previous "valid"/
        # allows_action=True here was earned by hardcoded age_sensitivity=
        # forcing_sensitivity=0.1 literals that always passed; this is the
        # gate now failing closed on genuinely missing diagnostics, not a
        # regression in the attribution itself (decision_state is unchanged).
        assert result["gate_state"] == "restricted"
        assert result["allows_action"] is False
        assert result["scientific_status"] == "experimental"
        assert result["n_artifacts"] >= 4
        assert result["n_events"] >= 6


# ─────────── CASE-0002: Diffuse / Variant Geometry ───────────

class TestCase0002:
    def test_completes_without_error(self):
        from tests.fixtures.case_0002 import generate_case_0002
        fixture = generate_case_0002()
        wf = _make_workflow()
        config = fixture.get("config", {})
        kwargs = {k: v for k, v in config.items() if k in ["latent_prior", "age_prior_mean", "age_prior_std"]}
        
        result = wf.run_full(
            "CASE-0002",
            slick_lons=fixture["slick_lons"],
            slick_lats=fixture["slick_lats"],
            tracks=fixture["tracks"],
            obs_time_hours=fixture["obs_time_hours"],
            seed=fixture.get("seed", 42),
            **kwargs,
        )
        assert result["status"] == "completed"
        assert result["scientific_status"] == "experimental"
        assert result["n_artifacts"] >= 4


# ─────────── CASE-0003: Data Guard Quarantine (insufficient points) ───────────

class TestCase0003:
    def test_quarantined(self):
        from tests.fixtures.case_0003 import generate_case_0003
        fixture = generate_case_0003()
        wf = _make_workflow()
        result = wf.run_full(
            "CASE-0003",
            slick_lons=fixture["slick_lons"],
            slick_lats=fixture["slick_lats"],
            tracks=fixture["tracks"],
            obs_time_hours=fixture["obs_time_hours"],
        )
        assert result["status"] == "quarantined"
        assert result["error"] is not None


# ─────────── CASE-0004: Ambiguous / Inconclusive ───────────

class TestCase0004:
    def test_completes_without_error(self):
        from tests.fixtures.case_0004 import generate_case_0004
        fixture = generate_case_0004()
        wf = _make_workflow()
        config = fixture.get("config", {})
        kwargs = {k: v for k, v in config.items() if k in ["latent_prior", "age_prior_mean", "age_prior_std"]}
        
        result = wf.run_full(
            "CASE-0004",
            slick_lons=fixture["slick_lons"],
            slick_lats=fixture["slick_lats"],
            tracks=fixture["tracks"],
            obs_time_hours=fixture["obs_time_hours"],
            seed=fixture.get("seed", 42),
            **kwargs,
        )
        assert result["status"] == "completed"
        assert result["scientific_status"] == "experimental"


# ─────────── CASE-0005: Edge Case (no nearby candidates) ───────────

class TestCase0005:
    def test_completes_without_error(self):
        from tests.fixtures.case_0005 import generate_case_0005
        fixture = generate_case_0005()
        wf = _make_workflow()
        config = fixture.get("config", {})
        kwargs = {k: v for k, v in config.items() if k in ["latent_prior", "age_prior_mean", "age_prior_std"]}
        
        result = wf.run_full(
            "CASE-0005",
            slick_lons=fixture["slick_lons"],
            slick_lats=fixture["slick_lats"],
            tracks=fixture["tracks"],
            obs_time_hours=fixture["obs_time_hours"],
            seed=fixture.get("seed", 42),
            **kwargs,
        )
        assert result["status"] in ("completed", "quarantined")
        assert result.get("scientific_status", "experimental") == "experimental"


# ─────────── In-Memory Concurrency & Idempotency ───────────

class TestInMemoryEventSafety:
    """Verify correction #3 (concurrency-safe sequences) and #4
    (per-case idempotency) in the in-memory implementation."""

    def test_sequence_monotonic(self):
        import threading
        from varuna_domain.repositories import InMemoryEventStore
        from varuna_domain.entities import DomainEvent

        store = InMemoryEventStore()

        def insert(i):
            e = DomainEvent(f"event.{i}", "CASE-SEQ", "test", "CASE-SEQ", {"i": i})
            store.append(e)

        threads = [threading.Thread(target=insert, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = store.list_by_case("CASE-SEQ")
        assert len(events) == 20
        seqs = [e.sequence for e in events]
        assert len(set(seqs)) == 20, "Duplicate sequence numbers found"
        assert seqs == sorted(seqs), "Sequences not monotonically ordered"

    def test_idempotency_dedup(self):
        from varuna_domain.repositories import InMemoryEventStore
        from varuna_domain.entities import DomainEvent

        store = InMemoryEventStore()
        e1 = DomainEvent("test.event", "CASE-IDEM", "actor", "CASE-IDEM")
        e1.idempotency_key = "same-key"
        e2 = DomainEvent("test.event", "CASE-IDEM", "actor", "CASE-IDEM")
        e2.idempotency_key = "same-key"

        store.append(e1)
        store.append(e2)

        events = store.list_by_case("CASE-IDEM")
        assert len(events) == 1, "Duplicate event not deduplicated"

    def test_idempotency_key_scoped_per_case(self):
        """Same idempotency_key in different cases should both be accepted."""
        from varuna_domain.repositories import InMemoryEventStore
        from varuna_domain.entities import DomainEvent

        store = InMemoryEventStore()
        e1 = DomainEvent("test.event", "CASE-A", "actor", "CASE-A")
        e1.idempotency_key = "shared-key"
        e2 = DomainEvent("test.event", "CASE-B", "actor", "CASE-B")
        e2.idempotency_key = "shared-key"

        store.append(e1)
        store.append(e2)

        assert len(store.list_by_case("CASE-A")) == 1
        assert len(store.list_by_case("CASE-B")) == 1
        assert store.count() == 2
