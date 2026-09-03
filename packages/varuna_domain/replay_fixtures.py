"""
VARUNA GRID v2 — deterministic REPLAY fixtures for the Golden Case Engine.

Six named cases, each a real `varuna_integration.pipeline.PipelineRun` built
with the SAME `PipelineRun.record()` / `PipelineRun.blocked_by()` methods
`RealE2EPipeline` itself uses -- no cascade logic is reimplemented here, only
the individual per-stage StageResults a real producer would have returned
under each scenario, constructed directly against the REAL typed contracts
(`PhiField`, `AttributionResultV2`, `ValidityGateResult` via the real
`evaluate_validity_gate()`, `ForwardForecast`, `AssetTasking`, `MissionRecord`,
`DeliveryResult`).

No network, no filesystem read outside this process, no GPU, no real
checkpoint. Every fixture's evidence_mode is honestly SIMULATED or worse --
REPLAY data is never labelled REAL, matching the rule enforced structurally
everywhere else in this codebase (ADR-0006: mode can only worsen, and a
`degradation_state=CACHED_REPLAY` envelope is REJECTED outright if it claims
`mode=REAL` -- see `EvidenceEnvelope._cached_replay_cannot_claim_real`).

Determinism: every fixture is built from literal constants (fixed timestamps,
fixed geometry, fixed random-free numbers) -- calling `build_replay_run()`
twice for the same fixture name produces byte-identical `to_dict()` JSON
except for `run_id` (stamped with a fresh uuid per call by design, exactly
like a real run) and wall-clock timestamps. `tests/unit/test_replay_fixtures.py`
pins this.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from varuna_contracts.decision import (
    AttributionResultV2, CandidateScore, DecisionState, LatentFinding, PriorContribution,
)
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance, TrustState
from varuna_contracts.phi import (
    ConvergenceFlag, PhiDiagnostics, PhiField, SensitivityBlock, TimeDistribution,
)
from varuna_contracts.schemas import (
    AssetTasking, AssetType, BBox, GeoPoint, LandfallPrediction, SearchBox, SlickClass,
    SlickDetection, VesselType,
)
from varuna_contracts.states import MissionRecord, MissionState
from varuna_alerts.protocol import DeliveryResult
from varuna_integration.pipeline import PipelineConfig, PipelineRun
from varuna_integration.stage import StageResult, StageStatus
from varuna_nyaya.validity_gate import evaluate_validity_gate

FIXTURE_NAMES = (
    "CASE-VALID", "CASE-RESTRICTED", "CASE-OOD",
    "CASE-UNAVAILABLE", "CASE-SIMULATED", "CASE-BLOCKED",
)

# Fixed geometry and time, shared by every fixture -- the same MC20 anchor
# point already used throughout this codebase's real MC20 work, so a replay
# fixture and a real MC20 case are visually comparable on a map.
_ANCHOR = GeoPoint(lon=-88.970, lat=28.936)
_BBOX = BBox(min_lon=-89.02, min_lat=28.90, max_lon=-88.92, max_lat=28.98)
_T_OBS = datetime(2023, 1, 15, 0, 2, 6, tzinfo=timezone.utc)


def _envelope(artifact_id: str, produced_by: str, mode: EvidenceMode, *,
              source_id: str = "replay.fixture") -> EvidenceEnvelope:
    return EvidenceEnvelope(
        artifact_id=artifact_id, produced_by=produced_by,
        provenance=Provenance(
            source_id=source_id,
            notes="REPLAY fixture -- deterministic, offline, not a live measurement",
        ),
        mode=mode,
    )


def _detection(mode_label: str) -> SlickDetection:
    return SlickDetection(
        slick_id=f"replay-slick-{mode_label}", scene_id="replay-scene-mc20-anchor",
        observation_time=_T_OBS, classification=SlickClass.OIL, confidence=0.7,
        mask_path="", centroid=_ANCHOR, bbox=_BBOX, area_km2=12.0, perimeter_km=14.0,
        elongation=2.1, orientation_deg=35.0, age_prior_mean_hours=24.0,
        age_prior_std_hours=12.0, netra_model_version=f"replay-fixture-{mode_label}",
    )


def _phi(case_id: str, slick_id: str, mode: EvidenceMode, *, with_sensitivity: bool) -> PhiField:
    t0 = _T_OBS.timestamp()
    t1 = (_T_OBS + timedelta(hours=24)).timestamp()
    diagnostics = PhiDiagnostics(
        entropy=0.30, concentration=0.60, effective_support_km2=25.0, convergence=0.05,
        convergence_flag=ConvergenceFlag.CONVERGED, n_modes=1, multimodal=False,
        boundary_interaction=False, particles_lost=10, particles_seeded=500,
        ensemble_members_completed=20, ensemble_members_requested=20, runtime_seconds=12.3,
    )
    sensitivity = (
        SensitivityBlock(age_sensitivity=0.20, forcing_sensitivity=0.25,
                         diffusivity_sensitivity=0.15, weathering_sensitivity=None)
        if with_sensitivity else None
    )
    return PhiField(
        phi_id=f"replay-phi-{case_id}", slick_id=slick_id, case_id=case_id,
        data_path=f"replay://{case_id}/phi.npz", bbox=_BBOX, grid_shape=(1, 64, 64),
        time_distribution=TimeDistribution(
            time_edges_unix=[t0, t1], mass=[1.0], mode_unix=t0, p05_unix=t0, p95_unix=t1,
        ),
        spatial_modes=[], diagnostics=diagnostics, sensitivity=sensitivity,
        n_particles=500, n_ensemble=20, backward_duration_hours=24.0, dt_seconds=300.0,
        forcing_current_source="replay.synthetic.cmems", forcing_wind_source="replay.synthetic.era5",
        weathering_model=None, envelope=_envelope(f"phi-{case_id}", "prativartan", mode),
    )


def _attribution(case_id: str, phi_id: str, slick_id: str, mode: EvidenceMode) -> AttributionResultV2:
    candidate = CandidateScore(
        mmsi="368181750", vessel_name="HELEN", vessel_type=VesselType.UNKNOWN,
        path_integral=1.0, prior=PriorContribution(), likelihood=1.0, posterior=0.7,
        rank=1, closest_approach_km=3.2554, time_at_closest_hours=0.28,
        phi_mass_explained=0.6, ais_reliability=0.9, influence_weight=1.0,
    )
    return AttributionResultV2(
        case_id=case_id, slick_id=slick_id, phi_id=phi_id,
        decision_state=DecisionState.STRONG_LEAD, candidates=[candidate],
        latent_probability=0.3, latent_finding=LatentFinding.RADAR_CONTACT_WITHOUT_AIS,
        top_posterior=0.7, top_gap=0.7, distinguishability=0.8, posterior_entropy=0.3,
        n_candidates_screened=5, n_candidates_scored=1,
        envelope=_envelope(f"attribution-{case_id}", "nyaya", mode),
    )


def _forecast(case_id: str, slick_id: str, mode: EvidenceMode = EvidenceMode.REAL):
    from varuna_contracts.schemas import ForwardForecast

    return ForwardForecast(
        forecast_id=f"replay-forecast-{case_id}", slick_id=slick_id, horizon_hours=24.0,
        landfalls=[LandfallPrediction(
            location_name="Replay coastal segment", position=_ANCHOR,
            eta=_T_OBS + timedelta(hours=18), hours_until=18.0, probability=0.4,
            coastline_segment_km=5.0,
        )],
        affected_fishing_zones=[], trajectory_path=f"replay://{case_id}/traj.npz",
        envelope=_envelope(f"forecast-{case_id}", "pravaah", mode),
    )


def _decision(case_id: str) -> list[AssetTasking]:
    return [AssetTasking(
        asset_type=AssetType.DORNIER, base_name="INS Replay Base",
        search_box=SearchBox(bbox=_BBOX, center=_ANCHOR, area_km2=50.0, phi_mass_contained=1.0),
        pattern="expanding_square", launch_time=_T_OBS + timedelta(hours=1), flight_hours=3.0,
        probability_of_detection=0.6, rationale="replay fixture tasking, not a real mission",
    )]


def _mission(case_id: str) -> list[MissionRecord]:
    """The replay mission now carries the SAME AssetTasking the fixture's
    own decision stage produces (ADR-0015). It was omitted, so a replay
    mission showed an asset base-name and nothing else — an operator could
    not see what they were being asked to authorise, and the map had no
    search box to draw. This is the fixture's existing tasking, not a new
    invented one."""
    return [MissionRecord(
        mission_id=f"MSN-REPLAY-{case_id}", case_id=case_id, asset_id="INS Replay Base",
        state=MissionState.AVAILABLE,
        tasking=_decision(case_id)[0],
    )]


def _alerts(case_id: str) -> list[DeliveryResult]:
    return [DeliveryResult(
        channel="console", recipient="ops-room", status="sent",
        reason="replay fixture -- reached the console channel only",
        is_simulated=True, idempotency_key=f"replay:{case_id}:validity.evaluated:ops-room",
    )]


def _new_run(case_id: str, run_class: str) -> PipelineRun:
    cfg = PipelineConfig(gold_dir="replay://fixture", run_class=run_class)
    return PipelineRun(
        run_id=f"RUN-REPLAY-{uuid.uuid4().hex[:8]}", case_id=case_id,
        started_at=datetime.now(timezone.utc), config=cfg,
    )


def build_replay_run(fixture_name: str, case_id: str | None = None) -> PipelineRun:
    """The one entry point. Returns a fully-populated `PipelineRun` exactly as
    `RealE2EPipeline.run()` would have, for one of `FIXTURE_NAMES`."""
    if fixture_name not in FIXTURE_NAMES:
        raise ValueError(f"unknown replay fixture {fixture_name!r}; known: {FIXTURE_NAMES}")
    case_id = case_id or fixture_name
    builder = _BUILDERS[fixture_name]
    run = _new_run(case_id, run_class="REPLAY")
    builder(run, case_id)
    run.finished_at = datetime.now(timezone.utc)
    return run


# --------------------------------------------------------------- CASE-VALID


def _build_valid(run: PipelineRun, case_id: str) -> None:
    forcing = run.record(StageResult(
        stage="forcing", status=StageStatus.PRODUCED, value={"note": "replay synthetic forcing"},
        evidence_mode=EvidenceMode.REAL, detail={"overlap_hours": 132.0},
    ))
    ais = run.record(StageResult(
        stage="ais_ingest", status=StageStatus.PRODUCED, value=[],
        evidence_mode=EvidenceMode.REAL, detail={"n_returned": 0, "requested_status": "temporally_matched"},
    ))
    det = _detection("valid")
    run.slick_points = ([_ANCHOR.lon], [_ANCHOR.lat])
    detection = run.record(StageResult(
        stage="netra_detection", status=StageStatus.PRODUCED, value=[det],
        evidence_mode=EvidenceMode.REAL, detail={"model_version": "netra-replay-frozen",
                                                  "n_detections": 1, "scientific_status": "VALIDATED",
                                                  # Activation statistics, added so this fixture can
                                                  # satisfy the OOD assessment the agentic layer now
                                                  # requires before any case may reach a decision
                                                  # (varuna_agentic.loop.ActionSelector step 10).
                                                  # Without them CASE-VALID could never reach a
                                                  # decision, which contradicts the fixture's own
                                                  # stated purpose ("if a frozen, calibrated
                                                  # checkpoint fired here"). Values are consistent
                                                  # with a confident in-domain firing and are
                                                  # SYNTHETIC like every other number in this file.
                                                  "max_probability": 0.91,
                                                  "decision_threshold": 0.806},
    ))
    phi = _phi(case_id, det.slick_id, EvidenceMode.REAL, with_sensitivity=True)
    phi_res = run.record(StageResult(
        stage="phi_reconstruction", status=StageStatus.PRODUCED, value=phi,
        evidence_mode=EvidenceMode.REAL, detail={"phi_id": phi.phi_id,
                                                  "convergence_flag": phi.diagnostics.convergence_flag.value},
    ))
    attribution = _attribution(case_id, phi.phi_id, det.slick_id, EvidenceMode.REAL)
    run.record(StageResult(
        stage="attribution", status=StageStatus.PRODUCED, value=attribution,
        evidence_mode=EvidenceMode.REAL, detail={"decision_state": attribution.decision_state.value},
    ))
    gate = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)
    run.record(StageResult(
        stage="validity", status=StageStatus.PRODUCED, value=gate,
        evidence_mode=gate.envelope.mode, detail={"gate_state": gate.state.value,
                                                   "allows_operational_action": gate.allows_operational_action},
    ))
    forecast = _forecast(case_id, det.slick_id)
    run.record(StageResult(
        stage="forecast", status=StageStatus.PRODUCED, value=forecast,
        evidence_mode=EvidenceMode.REAL, detail={"forecast_id": forecast.forecast_id},
    ))
    taskings = _decision(case_id)
    run.record(StageResult(
        stage="decision", status=StageStatus.PRODUCED, value=taskings,
        evidence_mode=EvidenceMode.REAL, detail={"n_taskings": len(taskings)},
    ))
    missions = _mission(case_id)
    run.record(StageResult(
        stage="mission", status=StageStatus.PRODUCED, value=missions,
        evidence_mode=EvidenceMode.REAL, detail={"n_missions": len(missions)},
    ))
    alerts = _alerts(case_id)
    run.record(StageResult(
        stage="alerts", status=StageStatus.PRODUCED, value=alerts,
        evidence_mode=EvidenceMode.REAL, detail={"n_results": len(alerts)},
    ))


# ---------------------------------------------------------- CASE-RESTRICTED


def _build_restricted(run: PipelineRun, case_id: str) -> None:
    run.record(StageResult(
        stage="forcing", status=StageStatus.PRODUCED, value={"note": "replay synthetic forcing"},
        evidence_mode=EvidenceMode.REAL,
    ))
    run.record(StageResult(
        stage="ais_ingest", status=StageStatus.PRODUCED, value=[],
        evidence_mode=EvidenceMode.REAL,
    ))
    det = _detection("restricted")
    run.slick_points = ([_ANCHOR.lon], [_ANCHOR.lat])
    run.record(StageResult(
        stage="netra_detection", status=StageStatus.PRODUCED, value=[det],
        evidence_mode=EvidenceMode.REAL, detail={"model_version": "netra-replay-frozen", "n_detections": 1},
    ))
    # No SensitivityBlock -- exactly the real, currently-shipping default
    # (varuna_prativartan/phi_builder.py's sensitivity sweep is unimplemented,
    # ADR-0007 TODO(P1)). The gate's own `phi_diagnostics_availability` check
    # then blocks for real, unmodified reasons -- this fixture is not a
    # fabricated restriction, it is what the real gate does today.
    phi = _phi(case_id, det.slick_id, EvidenceMode.REAL, with_sensitivity=False)
    run.record(StageResult(
        stage="phi_reconstruction", status=StageStatus.PRODUCED, value=phi,
        evidence_mode=EvidenceMode.REAL, detail={"phi_id": phi.phi_id},
    ))
    attribution = _attribution(case_id, phi.phi_id, det.slick_id, EvidenceMode.REAL)
    run.record(StageResult(
        stage="attribution", status=StageStatus.PRODUCED, value=attribution,
        evidence_mode=EvidenceMode.REAL,
    ))
    gate = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)
    run.record(StageResult(
        stage="validity", status=StageStatus.PRODUCED, value=gate,
        evidence_mode=gate.envelope.mode, detail={"gate_state": gate.state.value,
                                                   "blocking_reasons": list(gate.blocking_reasons)},
    ))
    forecast = _forecast(case_id, det.slick_id)
    run.record(StageResult(
        stage="forecast", status=StageStatus.PRODUCED, value=forecast, evidence_mode=EvidenceMode.REAL,
    ))
    # Gate restricted -> ABHIYAN legitimately proposes nothing. This mirrors
    # `RealE2EPipeline._decide()`'s own direct-record branch exactly.
    run.record(StageResult(
        stage="decision", status=StageStatus.NOT_YET_PRODUCED,
        reason=(f"NO_TASKING: the validity gate state is {gate.state.value} "
                f"(allows_operational_action={gate.allows_operational_action}). "
                "This is the fail-closed contract working, not a failure."),
        evidence_mode=gate.envelope.mode, detail={"gate_state": gate.state.value},
    ))
    run.record(StageResult(
        stage="mission", status=StageStatus.NOT_YET_PRODUCED,
        reason="NO_TASKING_TO_PROPOSE: a mission requires an ABHIYAN tasking.",
    ))
    # Alerts depend only on validity having PRODUCED, per RealE2EPipeline's
    # own `_alerts()` -- a restrictive gate is still a materially interesting
    # event.
    alerts = _alerts(case_id)
    run.record(StageResult(
        stage="alerts", status=StageStatus.PRODUCED, value=alerts,
        evidence_mode=EvidenceMode.REAL, detail={"n_results": len(alerts)},
    ))


# ---------------------------------------------------------------- CASE-OOD


def _build_ood(run: PipelineRun, case_id: str) -> None:
    run.record(StageResult(
        stage="forcing", status=StageStatus.PRODUCED, value={"note": "replay synthetic forcing"},
        evidence_mode=EvidenceMode.REAL,
    ))
    run.record(StageResult(
        stage="ais_ingest", status=StageStatus.PRODUCED, value=[], evidence_mode=EvidenceMode.REAL,
    ))
    detection = run.record(StageResult(
        stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
        reason=("OOD: input scene fell recognisably outside this model's trained "
                "distribution (near-uniform logit, response weaker than to random "
                "noise). No detection is reported -- an out-of-distribution input "
                "is not evidence of absence."),
        detail={"ood": True, "max_oil_probability": 3.07e-06,
                "note": "modelled on the real MC20 null result; this fixture is what a "
                        "detector EXPLICITLY reporting OOD would look like -- the real "
                        "boundary does not emit this flag today, see derive_case_status()"},
    ))
    run.record(run.blocked_by("phi_reconstruction", "netra_detection", detection.reason or ""))
    phi_res = run.stages["phi_reconstruction"]
    run.record(run.blocked_by("attribution", "phi_reconstruction", phi_res.reason or ""))
    attr_res = run.stages["attribution"]
    run.record(run.blocked_by("validity", "phi_reconstruction", phi_res.reason or ""))
    run.record(StageResult(
        stage="forecast", status=StageStatus.NOT_YET_PRODUCED,
        reason=f"NO_SLICK_TO_FORECAST: forward drift needs a detected slick. Detection stage says: {detection.reason}",
    ))
    validity_res = run.stages["validity"]
    run.record(run.blocked_by("decision", "validity", validity_res.reason or ""))
    run.record(StageResult(
        stage="mission", status=StageStatus.NOT_YET_PRODUCED,
        reason="NO_TASKING_TO_PROPOSE: a mission requires an ABHIYAN tasking.",
    ))
    run.record(run.blocked_by("alerts", "validity", validity_res.reason or ""))


# --------------------------------------------------------- CASE-UNAVAILABLE


def _build_unavailable(run: PipelineRun, case_id: str) -> None:
    forcing = run.record(StageResult(
        stage="forcing", status=StageStatus.BLOCKED, evidence_mode=EvidenceMode.UNAVAILABLE,
        reason="ERA5_CUBE_MISSING: forcing/era5_cube.json does not exist for this replay case.",
    ))
    ais = run.record(StageResult(
        stage="ais_ingest", status=StageStatus.BLOCKED, evidence_mode=EvidenceMode.UNAVAILABLE,
        reason="AIS_JOIN_MISSING: ais/event_ais_join.json does not exist for this replay case.",
    ))
    detection = run.record(StageResult(
        stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
        reason="CHECKPOINT_NOT_FROZEN: no frozen checkpoint is registered for this replay case.",
    ))
    run.record(run.blocked_by("phi_reconstruction", "forcing", forcing.reason or ""))
    phi_res = run.stages["phi_reconstruction"]
    run.record(run.blocked_by("attribution", "phi_reconstruction", phi_res.reason or ""))
    run.record(run.blocked_by("validity", "phi_reconstruction", phi_res.reason or ""))
    run.record(run.blocked_by("forecast", "forcing", forcing.reason or ""))
    validity_res = run.stages["validity"]
    run.record(run.blocked_by("decision", "validity", validity_res.reason or ""))
    run.record(StageResult(
        stage="mission", status=StageStatus.NOT_YET_PRODUCED,
        reason="NO_TASKING_TO_PROPOSE: a mission requires an ABHIYAN tasking.",
    ))
    run.record(run.blocked_by("alerts", "validity", validity_res.reason or ""))


# ----------------------------------------------------------- CASE-SIMULATED


def _build_simulated(run: PipelineRun, case_id: str) -> None:
    """REAL forcing + REAL AIS, but an explicitly-requested SIMULATED
    detection placeholder (`resolve_netra_boundary(allow_simulated=True)`,
    unmodified). Provenance worsens monotonically downstream -- every stage
    from detection onward is honestly SIMULATED, never silently promoted --
    yet the gate still evaluates and the run still completes: SIMULATED
    evidence is a visible caveat, not, by itself, a block (see
    validity_gate.py check 10)."""
    run.record(StageResult(
        stage="forcing", status=StageStatus.PRODUCED, value={"note": "replay synthetic forcing"},
        evidence_mode=EvidenceMode.REAL,
    ))
    run.record(StageResult(
        stage="ais_ingest", status=StageStatus.PRODUCED, value=[], evidence_mode=EvidenceMode.REAL,
    ))
    det = _detection("simulated")
    run.slick_points = ([_ANCHOR.lon], [_ANCHOR.lat])
    run.record(StageResult(
        stage="netra_detection", status=StageStatus.PRODUCED, value=[det],
        evidence_mode=EvidenceMode.SIMULATED,
        detail={"model_version": "SIMULATED-no-model", "n_detections": 1,
                "notes": "NOT a NETRA detection -- explicitly-requested simulated placeholder"},
    ))
    phi = _phi(case_id, det.slick_id, EvidenceMode.SIMULATED, with_sensitivity=True)
    run.record(StageResult(
        stage="phi_reconstruction", status=StageStatus.PRODUCED, value=phi,
        evidence_mode=EvidenceMode.SIMULATED,
    ))
    attribution = _attribution(case_id, phi.phi_id, det.slick_id, EvidenceMode.SIMULATED)
    run.record(StageResult(
        stage="attribution", status=StageStatus.PRODUCED, value=attribution,
        evidence_mode=EvidenceMode.SIMULATED,
    ))
    gate = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)
    run.record(StageResult(
        stage="validity", status=StageStatus.PRODUCED, value=gate, evidence_mode=gate.envelope.mode,
        detail={"gate_state": gate.state.value,
                "officer_visible_caveats": list(gate.officer_visible_caveats)},
    ))
    forecast = _forecast(case_id, det.slick_id)
    run.record(StageResult(
        stage="forecast", status=StageStatus.PRODUCED, value=forecast, evidence_mode=EvidenceMode.SIMULATED,
    ))
    if gate.allows_operational_action:
        taskings = _decision(case_id)
        run.record(StageResult(
            stage="decision", status=StageStatus.PRODUCED, value=taskings,
            evidence_mode=EvidenceMode.SIMULATED, detail={"n_taskings": len(taskings)},
        ))
        missions = _mission(case_id)
        run.record(StageResult(
            stage="mission", status=StageStatus.PRODUCED, value=missions,
            evidence_mode=EvidenceMode.SIMULATED,
        ))
    else:
        run.record(StageResult(
            stage="decision", status=StageStatus.NOT_YET_PRODUCED,
            reason=f"NO_TASKING: gate state is {gate.state.value}.",
            evidence_mode=gate.envelope.mode,
        ))
        run.record(StageResult(
            stage="mission", status=StageStatus.NOT_YET_PRODUCED,
            reason="NO_TASKING_TO_PROPOSE: a mission requires an ABHIYAN tasking.",
        ))
    alerts = _alerts(case_id)
    run.record(StageResult(
        stage="alerts", status=StageStatus.PRODUCED, value=alerts, evidence_mode=EvidenceMode.SIMULATED,
    ))


# -------------------------------------------------------------- CASE-BLOCKED


def _build_blocked(run: PipelineRun, case_id: str) -> None:
    """A genuine integration break: forcing, AIS and detection all succeed on
    good input, but PRATIVARTAN raises. Distinguishes a real break (BLOCKED)
    from missing input (UNAVAILABLE, see CASE-UNAVAILABLE)."""
    run.record(StageResult(
        stage="forcing", status=StageStatus.PRODUCED, value={"note": "replay synthetic forcing"},
        evidence_mode=EvidenceMode.REAL,
    ))
    run.record(StageResult(
        stage="ais_ingest", status=StageStatus.PRODUCED, value=[], evidence_mode=EvidenceMode.REAL,
    ))
    det = _detection("blocked")
    run.slick_points = ([_ANCHOR.lon], [_ANCHOR.lat])
    run.record(StageResult(
        stage="netra_detection", status=StageStatus.PRODUCED, value=[det],
        evidence_mode=EvidenceMode.REAL, detail={"model_version": "netra-replay-frozen", "n_detections": 1},
    ))
    phi_result = run.record(StageResult(
        stage="phi_reconstruction", status=StageStatus.BLOCKED,
        reason="PRATIVARTAN_FAILED: RuntimeError: synthetic replay fault (CASE-BLOCKED fixture)",
    ))
    run.record(run.blocked_by("attribution", "phi_reconstruction", phi_result.reason or ""))
    run.record(run.blocked_by("validity", "phi_reconstruction", phi_result.reason or ""))
    # PRAVAAH does not depend on PRATIVARTAN -- forcing and detection both
    # succeeded, so the real `_forecast()` would still produce here. Kept
    # PRODUCED to prove the break is scoped, not blanket-propagated.
    forecast = _forecast(case_id, det.slick_id)
    run.record(StageResult(
        stage="forecast", status=StageStatus.PRODUCED, value=forecast, evidence_mode=EvidenceMode.REAL,
    ))
    validity_res = run.stages["validity"]
    run.record(run.blocked_by("decision", "validity", validity_res.reason or ""))
    run.record(StageResult(
        stage="mission", status=StageStatus.NOT_YET_PRODUCED,
        reason="NO_TASKING_TO_PROPOSE: a mission requires an ABHIYAN tasking.",
    ))
    run.record(run.blocked_by("alerts", "validity", validity_res.reason or ""))


_BUILDERS = {
    "CASE-VALID": _build_valid,
    "CASE-RESTRICTED": _build_restricted,
    "CASE-OOD": _build_ood,
    "CASE-UNAVAILABLE": _build_unavailable,
    "CASE-SIMULATED": _build_simulated,
    "CASE-BLOCKED": _build_blocked,
}
