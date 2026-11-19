"""
Track 2 Phase 10 — EvidenceMode propagation through the ACTUAL service
methods (PrativartanService.reconstruct_origin -> NyayaService.attribute ->
ValidityService.evaluate), not just the pure EvidenceEnvelope.derive() math
already covered by tests/contract/test_evidence_mode.py.

Required matrix:
    REAL Phi + REAL AIS       -> REAL
    REAL Phi + SIMULATED AIS  -> SIMULATED
    SIMULATED Phi + REAL AIS  -> SIMULATED
    SIMULATED Phi (no AIS envelope) -> SIMULATED

Tiny particle/ensemble counts throughout, matching ADR-0007 Phase 9's
resource-safety guidance for anything that runs the real ensemble while
NETRA training may be sharing the machine.
"""
import numpy as np
import pytest

from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.schemas import AISPoint, VesselTrack, VesselType
from varuna_nyaya.services import NyayaService, PrativartanService, ValidityService
from datetime import datetime, timezone

pytestmark = pytest.mark.integration


def _env(mode: EvidenceMode, artifact_id: str = "env") -> EvidenceEnvelope:
    return EvidenceEnvelope(
        artifact_id=artifact_id, produced_by="test",
        provenance=Provenance(source_id="test"), mode=mode,
    )


def _tracks() -> list[VesselTrack]:
    return [VesselTrack(
        mmsi="123456789", vessel_type=VesselType.CARGO,
        points=[
            AISPoint(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), lon=70.05, lat=15.02, sog_knots=8.0),
            AISPoint(timestamp=datetime(2026, 1, 1, 1, tzinfo=timezone.utc), lon=70.06, lat=15.03, sog_knots=8.0),
        ],
    )]


def _build_phi(mode: EvidenceMode):
    rng = np.random.default_rng(11)
    n = 20
    lons = 70.0 + rng.uniform(-0.1, 0.1, n)
    lats = 15.0 + rng.uniform(-0.1, 0.1, n)
    svc = PrativartanService()
    return svc.reconstruct_origin(
        slick_lons=lons, slick_lats=lats, obs_time_hours=100.0,
        case_id="CASE-PROV", slick_id="slick-prov",
        age_prior_mean_hours=24.0, age_prior_std_hours=6.0,
        n_particles=20, n_ensemble=4, seed=5,
        input_envelope=_env(mode, artifact_id="phi-input-env"),
    )


@pytest.mark.parametrize("phi_mode,ais_mode,expected", [
    (EvidenceMode.REAL, EvidenceMode.REAL, EvidenceMode.REAL),
    (EvidenceMode.REAL, EvidenceMode.SIMULATED, EvidenceMode.SIMULATED),
    (EvidenceMode.SIMULATED, EvidenceMode.REAL, EvidenceMode.SIMULATED),
    (EvidenceMode.SIMULATED, None, EvidenceMode.SIMULATED),
])
def test_mode_propagates_through_real_service_calls(phi_mode, ais_mode, expected):
    phi = _build_phi(phi_mode)
    assert phi.envelope.mode is phi_mode  # sanity: reconstruct_origin didn't drop it

    tracks_envelope = _env(ais_mode, artifact_id="ais-env") if ais_mode is not None else None

    nyaya = NyayaService()
    attribution = nyaya.attribute(
        phi=phi, tracks=_tracks(), case_id="CASE-PROV",
        slick_lons=np.array([70.05]), slick_lats=np.array([15.02]),
        tracks_envelope=tracks_envelope,
    )
    assert attribution.envelope.mode is expected

    gate_result = ValidityService().evaluate(phi, attribution)
    assert gate_result.envelope.mode is expected
    # mode never upgrades between attribution and the gate's own derive().
    assert gate_result.envelope.mode.rank >= attribution.envelope.mode.rank


def test_unavailable_phi_never_becomes_real_through_the_chain():
    phi = _build_phi(EvidenceMode.UNAVAILABLE)
    nyaya = NyayaService()
    attribution = nyaya.attribute(
        phi=phi, tracks=_tracks(), case_id="CASE-PROV",
        slick_lons=np.array([70.05]), slick_lats=np.array([15.02]),
        tracks_envelope=_env(EvidenceMode.REAL, artifact_id="ais-env"),
    )
    # UNAVAILABLE Phi + REAL AIS must stay UNAVAILABLE (worst-of-inputs),
    # never upgraded by the "better" AIS input.
    assert attribution.envelope.mode is EvidenceMode.UNAVAILABLE

    gate_result = ValidityService().evaluate(phi, attribution)
    assert gate_result.envelope.mode is EvidenceMode.UNAVAILABLE
    assert gate_result.allows_operational_action is False
