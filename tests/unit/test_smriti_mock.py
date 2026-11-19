import pytest
from datetime import datetime, timezone
from varuna_contracts.schemas import BBox, EvidenceManifest
from varuna_contracts.evidence import TrustState
from varuna_smriti.mock import MockSmritiProvider
from varuna_smriti.service import SmritiService

def _make_dummy_manifest() -> EvidenceManifest:
    return EvidenceManifest(
        case_id="dummy",
        scene_ids=["scene-1"],
        model_versions={"netra": "mock-v1", "chhaya": "mock-v1"},
        forcing_versions={"cmems": "mock-v1"},
        parameters={},
        phi_checksum="abcdef",
        posterior_snapshot={"vessel_A": 0.8}
    )

def test_smriti_no_online_training():
    """Threat G-07: propose_training_batch never returns approved."""
    provider = MockSmritiProvider()
    provider.record_outcome("CASE-1", {"lon": 80.0, "lat": 15.0, "decision_state": "strong_lead"}, _make_dummy_manifest())
    proposal = provider.propose_training_batch()
    assert proposal.status == "pending"
    assert proposal.approved_by is None

def test_record_and_query_roundtrip():
    provider = MockSmritiProvider()
    provider.record_outcome("CASE-1", {"lon": 80.0, "lat": 15.0, "decision_state": "strong_lead"}, _make_dummy_manifest())
    results = provider.query_history(
        BBox(min_lon=79, min_lat=14, max_lon=81, max_lat=16),
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    assert len(results) == 1
    assert results[0].case_id == "CASE-1"
