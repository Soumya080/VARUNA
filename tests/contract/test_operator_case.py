"""
Contract tests for OperatorCase (docs/api/OPERATOR_CASE_CONTRACT_V1.md).

These test the CONTRACT SHAPE and the adapter's honesty guarantees — not
Track 2's scientific calculations, which are covered by their own test
suites (tests/unit/test_sensitivity_normalization.py etc.) and are not
re-verified here.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.api.operator_case_view import build_operator_case
from tests.fixtures.case_0001 import generate_case_0001
from varuna_contracts.decision import GateCheck, ValidityGateResult
from varuna_contracts.evidence import (
    EvidenceEnvelope,
    EvidenceMode,
    Provenance,
    ValidityState,
)
from varuna_contracts.operator_case import (
    OperationalDecisionState,
    OperatorCase,
    ProducerStatus,
    ProvenanceView,
    SectionEnvelope,
    SystemStatusView,
)
from varuna_domain.case_workflow import CaseWorkflow
from varuna_domain.repositories import (
    InMemoryArtifactRepository,
    InMemoryCaseRepository,
    InMemoryEventStore,
)

pytestmark = pytest.mark.contract


def _real_case_workflow():
    return CaseWorkflow(
        case_repo=InMemoryCaseRepository(),
        artifact_repo=InMemoryArtifactRepository(),
        event_repo=InMemoryEventStore(),
    )


def _envelope(mode: EvidenceMode, artifact_id: str = "e1") -> EvidenceEnvelope:
    return EvidenceEnvelope(
        artifact_id=artifact_id, produced_by="test",
        provenance=Provenance(source_id="test"), mode=mode,
    )


def _minimal_system_status() -> SystemStatusView:
    return SystemStatusView(case_status="created", scientific_status="experimental")


def _not_produced() -> SectionEnvelope:
    return SectionEnvelope(status=ProducerStatus.NOT_YET_PRODUCED, reason="not run")


def _minimal_operator_case(**overrides) -> OperatorCase:
    base = dict(
        case_id="MIN-1",
        generated_at=datetime.now(timezone.utc),
        system_status=_minimal_system_status(),
        observation=_not_produced(),
        detection=_not_produced(),
        origin=_not_produced(),
        ais=_not_produced(),
        attribution=_not_produced(),
        validity=_not_produced(),
        forecast=_not_produced(),
        decision=_not_produced(),
        mission=_not_produced(),
        alerts=_not_produced(),
        recommendation=OperationalDecisionState.UNAVAILABLE,
        evidence={"components": []},
        provenance=ProvenanceView(case_id="MIN-1", generated_at=datetime.now(timezone.utc)),
    )
    base.update(overrides)
    return OperatorCase(**base)


# ───────────────────────── 1. Minimal case serializes ─────────────────────────

def test_empty_minimal_case_serializes():
    oc = _minimal_operator_case()
    payload = oc.model_dump(mode="json")
    assert payload["schema_version"] == "v1"
    assert payload["observation"]["status"] == "not_yet_produced"
    assert payload["observation"]["value"] is None


# ───────────────────────── 2. Fully populated case serializes ─────────────────

def test_fully_populated_real_case_serializes():
    wf = _real_case_workflow()
    case = wf.create_case("FULL-1")
    fixture = generate_case_0001()
    case, guard = wf.ingest(
        case, fixture["slick_lons"], fixture["slick_lats"],
        fixture["tracks"], fixture["obs_time_hours"],
    )
    wf.reconstruct(case, seed=42)
    wf.attribute(case, latent_prior=0.5)

    oc = build_operator_case(case, wf)
    payload = oc.model_dump(mode="json")

    assert payload["observation"]["status"] == "produced"
    assert payload["origin"]["status"] == "produced"
    assert payload["attribution"]["status"] == "produced"
    assert payload["validity"]["status"] in ("produced", "blocked")
    assert payload["ais"]["status"] == "produced"
    assert len(payload["ais"]["value"]) == len(fixture["tracks"])


# ───────────────────────── 3. Missing detection → UNAVAILABLE-equivalent ──────

def test_missing_detection_is_not_yet_produced_not_fabricated():
    wf = _real_case_workflow()
    case = wf.create_case("NODETECT-1")
    fixture = generate_case_0001()
    case, _ = wf.ingest(
        case, fixture["slick_lons"], fixture["slick_lats"],
        fixture["tracks"], fixture["obs_time_hours"],
    )
    oc = build_operator_case(case, wf)
    assert oc.detection.status == ProducerStatus.NOT_YET_PRODUCED
    assert oc.detection.value is None
    assert oc.detection.reason is not None


# ───────────────────────── 4. Blocked validity is represented as BLOCKED ──────

def test_blocked_validity_gate_reflected_honestly():
    gate = ValidityGateResult(
        case_id="C1", state=ValidityState.RESTRICTED,
        checks=[GateCheck(name="phi_not_converged", passed=False)],
        blocking_reasons=["phi_not_converged"],
        envelope=_envelope(EvidenceMode.SIMULATED),
    )
    section = SectionEnvelope(
        status=ProducerStatus.BLOCKED if not gate.allows_operational_action else ProducerStatus.PRODUCED,
        value=gate, evidence_mode=gate.envelope.mode,
    )
    oc = _minimal_operator_case(validity=section)
    assert oc.validity.status == ProducerStatus.BLOCKED
    assert oc.validity.value.state == ValidityState.RESTRICTED
    assert oc.validity.value.allows_operational_action is False


# ───────────────────────── 5. SIMULATED is never converted to REAL ────────────

def test_simulated_evidence_never_becomes_real_end_to_end():
    wf = _real_case_workflow()
    case = wf.create_case("SIM-1")
    fixture = generate_case_0001()
    case, _ = wf.ingest(
        case, fixture["slick_lons"], fixture["slick_lats"],
        fixture["tracks"], fixture["obs_time_hours"],
    )
    wf.reconstruct(case, seed=42)  # PrativartanService.reconstruct_origin() defaults to SIMULATED
    wf.attribute(case, latent_prior=0.5)

    oc = build_operator_case(case, wf)
    assert oc.origin.evidence_mode == EvidenceMode.SIMULATED
    assert oc.attribution.evidence_mode == EvidenceMode.SIMULATED
    assert oc.origin.evidence_mode != EvidenceMode.REAL
    assert oc.attribution.evidence_mode != EvidenceMode.REAL


@pytest.mark.parametrize("mode", [EvidenceMode.REAL, EvidenceMode.SIMULATED, EvidenceMode.UNAVAILABLE])
def test_simulated_evidence_never_converted_by_construction(mode):
    """Constructing a SectionEnvelope never mutates the mode it was given."""
    section = SectionEnvelope(status=ProducerStatus.PRODUCED, evidence_mode=mode, value=None)
    assert section.evidence_mode == mode


# ───────────────────────── 6. EvidenceMode survives serialization ─────────────

def test_evidence_mode_survives_json_roundtrip():
    oc = _minimal_operator_case(
        origin=SectionEnvelope(status=ProducerStatus.PRODUCED, evidence_mode=EvidenceMode.SIMULATED),
    )
    reloaded = OperatorCase.model_validate_json(oc.model_dump_json())
    assert reloaded.origin.evidence_mode == EvidenceMode.SIMULATED


# ───────────────────────── 7. Provenance survives serialization ───────────────

def test_provenance_survives_json_roundtrip():
    oc = _minimal_operator_case(
        provenance=ProvenanceView(
            case_id="MIN-1", artifact_ids=["a-1", "a-2"], source_ids=["prativartan"],
            generated_at=datetime.now(timezone.utc),
        ),
    )
    reloaded = OperatorCase.model_validate_json(oc.model_dump_json())
    assert reloaded.provenance.artifact_ids == ["a-1", "a-2"]
    assert reloaded.provenance.source_ids == ["prativartan"]


# ───────────────────────── 8. Null/optional fields ≠ fake zeros ───────────────

def test_missing_values_are_none_not_zero():
    oc = _minimal_operator_case()
    assert oc.attribution.value is None          # never 0.0 candidates / fake posterior
    assert oc.origin.value is None                # never origin_lat=0.0 / origin_lon=0.0
    assert oc.forecast.value is None               # never forecast_risk=0.0
    dumped = oc.model_dump(mode="json")
    assert dumped["attribution"]["value"] is None
    assert dumped["origin"]["value"] is None


def test_evidence_component_score_is_none_not_zero_when_unmeasured():
    from varuna_contracts.operator_case import EvidenceComponentView, EvidenceHealthView
    view = EvidenceHealthView(components=[
        EvidenceComponentView(component="model_consistency", status=ProducerStatus.NOT_YET_PRODUCED,
                               score=None, reason="no metric implemented"),
    ])
    assert view.components[0].score is None
    assert view.components[0].score != 0


# ───────────────────────── 9. Existing API conventions remain compatible ──────

def test_existing_case_endpoints_unaffected(tmp_path):
    from apps.api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.post("/v1/cases", json={"case_id": "COMPAT-CHECK-1"})
    assert r.status_code == 200
    r2 = client.get("/v1/cases/COMPAT-CHECK-1")
    assert r2.status_code == 200
    assert "case_id" in r2.json()


def test_operator_view_endpoint_is_read_only_and_additive():
    from apps.api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    client.post("/v1/cases", json={"case_id": "OPVIEW-EP-1"})
    r = client.get("/v1/cases/OPVIEW-EP-1/operator-view")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "v1"
    assert body["case_id"] == "OPVIEW-EP-1"


def test_operator_view_404_for_unknown_case():
    from apps.api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/v1/cases/DOES-NOT-EXIST-XYZ/operator-view")
    assert r.status_code == 404


# ───────────────────────── 10. Version field is present ───────────────────────

def test_schema_version_field_present_and_pinned():
    oc = _minimal_operator_case()
    assert oc.schema_version == "v1"
    assert oc.model_dump(mode="json")["schema_version"] == "v1"


# ───────────────────────── 11. Unknown future fields tolerated where appropriate ──

def test_unknown_extra_field_in_evidence_health_component_is_rejected_not_silently_dropped():
    """
    extra='forbid' is the codebase-wide convention (varuna_contracts._Base) —
    an unrecognised field is a loud construction error, not silently ignored,
    matching every other contract type in this repository.
    """
    from pydantic import ValidationError
    from varuna_contracts.operator_case import EvidenceComponentView
    with pytest.raises(ValidationError):
        EvidenceComponentView(component="sar", status=ProducerStatus.PRODUCED, unknown_future_field=1)


# ───────────────────────── 12. Locked evaluation data not referenced ──────────

def test_no_locked_evaluation_or_credential_fields_exist_on_contract():
    field_names = set(OperatorCase.model_fields.keys())
    forbidden_substrings = ("password", "secret", "credential", "api_key", "token", "locked_eval")
    for name in field_names:
        lowered = name.lower()
        assert not any(f in lowered for f in forbidden_substrings), name


# ───────────────────────── 13. No secrets in serialized output ────────────────

def test_no_secrets_in_serialized_output():
    wf = _real_case_workflow()
    case = wf.create_case("SECRET-CHECK-1")
    oc = build_operator_case(case, wf)
    dumped = oc.model_dump_json().lower()
    for forbidden in ("password", "secret_key", "api_key", "access_key", "-----begin"):
        assert forbidden not in dumped
