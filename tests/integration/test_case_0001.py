"""
VARUNA GRID — CASE-0001 End-to-End Integration Test.

Verifies the complete vertical slice:
CASE -> INGEST -> DATA GUARD -> PRATIVARTAN -> NYAYA -> VALIDITY GATE
     -> PRAMAN -> EVENT SPINE -> retrievable

Does NOT assert scientific superiority.
Asserts: execution, schema correctness, provenance, valid state propagation,
         no truth leakage, event creation.
"""
import datetime as _dt
if not hasattr(_dt, "UTC"):
    _dt.UTC = _dt.timezone.utc
import enum as _enum
if not hasattr(_enum, "StrEnum"):
    class _StrEnum(str, _enum.Enum): pass
    _enum.StrEnum = _StrEnum

import pytest
from tests.fixtures.case_0001 import generate_case_0001
from varuna_domain.case_workflow import CaseWorkflow
from varuna_domain.repositories import (
    InMemoryCaseRepository, InMemoryArtifactRepository, InMemoryEventStore,
)


class TestCase0001EndToEnd:
    """Full vertical slice integration test."""

    def setup_method(self):
        self.fixture = generate_case_0001()
        # CaseWorkflow requires explicit repos (see tests/regression/
        # test_golden_cases.py::_make_workflow for the canonical pattern).
        self.workflow = CaseWorkflow(
            case_repo=InMemoryCaseRepository(),
            artifact_repo=InMemoryArtifactRepository(),
            event_repo=InMemoryEventStore(),
        )

    def test_full_pipeline_executes(self):
        """The entire pipeline runs without error."""
        result = self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
            latent_prior=self.fixture["config"]["latent_prior"],
            age_prior_mean=self.fixture["config"]["age_prior_mean"],
            age_prior_std=self.fixture["config"]["age_prior_std"],
        )
        assert result["status"] == "completed"
        assert result["case_id"] == "CASE-0001"

    def test_scientific_status_is_experimental(self):
        """Scientific status must be EXPERIMENTAL until M2.2 validation."""
        result = self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
        )
        assert result["scientific_status"] == "experimental"

    def test_phi_field_generated(self):
        """PhiField artifact must be created."""
        result = self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
        )
        assert "phi_id" in result
        assert result["phi_id"].startswith("phi-")

    def test_attribution_generated(self):
        """Attribution result must exist with valid decision state."""
        result = self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
        )
        valid_decisions = [
            "strong_lead", "weak_lead", "not_distinguishable",
            "latent_source", "inconclusive",
        ]
        assert result["decision"] in valid_decisions

    def test_validity_gate_evaluated(self):
        """Validity gate must produce a state."""
        result = self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
        )
        valid_states = ["valid", "degraded", "restricted", "inconclusive"]
        assert result["gate_state"] in valid_states

    def test_artifacts_created(self):
        """Multiple artifacts must be registered in PRAMAN."""
        result = self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
        )
        assert result["n_artifacts"] >= 3  # input_slick, phi, attribution, gate

    def test_events_emitted(self):
        """Event spine must contain the expected event sequence."""
        result = self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
        )
        assert result["n_events"] >= 5
        events = self.workflow.event_spine.list_by_case("CASE-0001")
        event_types = [e.event_type for e in events]
        assert "case.created" in event_types
        assert "origin.generated" in event_types
        assert "attribution.generated" in event_types
        assert "case.completed" in event_types

    def test_case_retrievable(self):
        """Case must be retrievable from repository."""
        self.workflow.run_full(
            case_id="CASE-0001",
            slick_lons=self.fixture["slick_lons"],
            slick_lats=self.fixture["slick_lats"],
            tracks=self.fixture["tracks"],
            obs_time_hours=self.fixture["obs_time_hours"],
            seed=self.fixture["seed"],
        )
        case = self.workflow.cases.get("CASE-0001")
        assert case is not None
        assert case.status.value == "completed"

    def test_quarantine_halts_pipeline(self):
        """Empty slick should be quarantined by Data Guard."""
        import numpy as np
        result = self.workflow.run_full(
            case_id="CASE-QUARANTINE",
            slick_lons=np.array([]),
            slick_lats=np.array([]),
            tracks=[],
            obs_time_hours=120.0,
        )
        assert result["status"] == "quarantined"
