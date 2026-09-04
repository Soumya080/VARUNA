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
    AttributionResultV2, CandidateScore, DecisionState, HistoricalReconstruction,
    LatentFinding, PriorContribution,
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
    `RealE2EPipeline.run()` would have, for one of `FIXTURE_NAMES` (the
    original six MC20-anchored scenarios) or `INDIA_FIXTURE_NAMES` (Phase 6's
    curated Indian Ocean incident library) — together, `ALL_FIXTURE_NAMES`.
    `_BUILDERS` is populated with both sets below."""
    if fixture_name not in _BUILDERS:
        raise ValueError(f"unknown replay fixture {fixture_name!r}; known: {sorted(_BUILDERS)}")
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


# ============================================================================
# Indian Ocean region fixtures (Phase 5/6) — curated, historically-researched
# scenarios, NOT a live news feed (explicit product decision, 2026-09-03: see
# docs/product/INDIAN_OCEAN_FIXTURES.md). Each is a separate, parallel set of
# constants and builder logic — the original six MC20-anchored fixtures and
# their `_ANCHOR`/`_BBOX`/`_T_OBS`/`_phi`/`_attribution`/`_forecast`/
# `_decision`/`_mission`/`_detection` helpers above are UNTOUCHED, so their
# pinned determinism tests keep passing byte-for-byte.
#
# `EvidenceMode.SIMULATED` throughout, exactly like every fixture above —
# these are illustrative reconstructions of real, documented events, not
# measured data, and must never be mistaken for a live case. Real vessel
# flag/identity is used where publicly documented; MMSI is left as a
# plausible-format placeholder where the real one isn't public record —
# flagged per-fixture below.
# ============================================================================

from dataclasses import dataclass


@dataclass(frozen=True)
class _IndiaScenario:
    case_id: str
    anchor: GeoPoint
    bbox: BBox
    t_obs: datetime
    vessel_mmsi: str
    vessel_name: str
    vessel_type: VesselType
    area_km2: float
    elongation: float
    landfall_name: str | None  # None = no landfall to model (see _india_forecast)
    rationale: str
    source_note: str  # what real event this models, and what's illustrative


def _india_detection(scn: _IndiaScenario) -> SlickDetection:
    return SlickDetection(
        slick_id=f"replay-slick-{scn.case_id}", scene_id=f"replay-scene-{scn.case_id}",
        observation_time=scn.t_obs, classification=SlickClass.OIL, confidence=0.7,
        mask_path="", centroid=scn.anchor, bbox=scn.bbox, area_km2=scn.area_km2,
        perimeter_km=scn.area_km2 * 1.15, elongation=scn.elongation, orientation_deg=35.0,
        age_prior_mean_hours=24.0, age_prior_std_hours=12.0,
        netra_model_version=f"replay-fixture-{scn.case_id}",
    )


def _india_phi(scn: _IndiaScenario, slick_id: str) -> PhiField:
    t0 = scn.t_obs.timestamp()
    t1 = (scn.t_obs + timedelta(hours=24)).timestamp()
    diagnostics = PhiDiagnostics(
        entropy=0.30, concentration=0.60, effective_support_km2=scn.area_km2 * 2, convergence=0.05,
        convergence_flag=ConvergenceFlag.CONVERGED, n_modes=1, multimodal=False,
        boundary_interaction=False, particles_lost=10, particles_seeded=500,
        ensemble_members_completed=20, ensemble_members_requested=20, runtime_seconds=12.3,
    )
    sensitivity = SensitivityBlock(age_sensitivity=0.20, forcing_sensitivity=0.25,
                                    diffusivity_sensitivity=0.15, weathering_sensitivity=None)
    return PhiField(
        phi_id=f"replay-phi-{scn.case_id}", slick_id=slick_id, case_id=scn.case_id,
        data_path=f"replay://{scn.case_id}/phi.npz", bbox=scn.bbox, grid_shape=(1, 64, 64),
        time_distribution=TimeDistribution(
            time_edges_unix=[t0, t1], mass=[1.0], mode_unix=t0, p05_unix=t0, p95_unix=t1,
        ),
        spatial_modes=[], diagnostics=diagnostics, sensitivity=sensitivity,
        n_particles=500, n_ensemble=20, backward_duration_hours=24.0, dt_seconds=300.0,
        forcing_current_source="replay.synthetic.cmems", forcing_wind_source="replay.synthetic.era5",
        weathering_model=None,
        envelope=_envelope(f"phi-{scn.case_id}", "prativartan", EvidenceMode.SIMULATED),
    )


def _india_attribution(scn: _IndiaScenario, phi_id: str, slick_id: str) -> AttributionResultV2:
    """M1+M2 fix (docs/product/HONESTY_LEDGER.md #3-4).

    This used to fabricate a `CandidateScore` — `posterior: 0.7`,
    `ais_reliability: 0.9` — that VARUNA never computed, to attach a real
    vessel identity to a case where no AIS tracks were ever ingested
    (`n_tracks: 0`). The impossible all-zero `PriorContribution` (M2)
    followed directly from that: nothing ever supplied a real prior,
    because no real scoring ever happened.

    The COMPUTED attribution is now honest: zero candidates were screened
    (no AIS coverage exists for this replay case), so the correct
    `decision_state` is `INCONCLUSIVE`, not `STRONG_LEAD`, and no
    `CandidateScore` is constructed — M2 disappears by construction, since
    there is no `PriorContribution` for it to be wrong about.

    The real, publicly-documented vessel identity moves to
    `historical_reconstruction` — a structurally separate field that can
    never carry a score, and whose `provenance` literal makes clear this is
    a historical record, not a VARUNA computation. `vessel_mmsi ==
    "000000000"` (IND-CASE-05's offshore-platform scenario) means there is
    genuinely no vessel to name; no reconstruction is attached for it.
    """
    reconstruction = None
    if scn.vessel_mmsi != "000000000":
        reconstruction = HistoricalReconstruction(
            vessel_name=scn.vessel_name, mmsi=scn.vessel_mmsi,
            event_description=scn.source_note, source_citation=scn.rationale,
        )
    return AttributionResultV2(
        case_id=scn.case_id, slick_id=slick_id, phi_id=phi_id,
        decision_state=DecisionState.INCONCLUSIVE, candidates=[],
        latent_probability=1.0, latent_finding=LatentFinding.INSUFFICIENT_COVERAGE,
        top_posterior=0.0, top_gap=0.0, distinguishability=0.0, posterior_entropy=0.0,
        n_candidates_screened=0, n_candidates_scored=0,
        historical_reconstruction=reconstruction,
        envelope=_envelope(f"attribution-{scn.case_id}", "nyaya", EvidenceMode.SIMULATED),
    )


def _india_forecast(scn: _IndiaScenario, slick_id: str):
    from varuna_contracts.schemas import ForwardForecast

    # M5 fix (docs/product/HONESTY_LEDGER.md #7): a `landfall_name` of None
    # means "there is no landfall to model" (IND-CASE-05's offshore-platform
    # source), not "here is a landfall whose name happens to be a sentence
    # explaining why there isn't one". Constructing a `LandfallPrediction`
    # for the latter is what produced a real HIGH-severity alert reading
    # "forecast predicts landfall at Not applicable — offshore platform
    # source". The honest forecast for a source with no coastline
    # interaction is an EMPTY landfalls list — material_change.py's guard
    # (see its own docstring) additionally refuses to alert on any landfall
    # list entry without a real location_name, so this can't regress
    # silently even if a future fixture makes the same mistake.
    landfalls = []
    if scn.landfall_name:
        landfalls = [LandfallPrediction(
            location_name=scn.landfall_name, position=scn.anchor,
            eta=scn.t_obs + timedelta(hours=18), hours_until=18.0, probability=0.4,
            coastline_segment_km=5.0,
        )]

    return ForwardForecast(
        forecast_id=f"replay-forecast-{scn.case_id}", slick_id=slick_id, horizon_hours=24.0,
        landfalls=landfalls,
        affected_fishing_zones=[], trajectory_path=f"replay://{scn.case_id}/traj.npz",
        envelope=_envelope(f"forecast-{scn.case_id}", "pravaah", EvidenceMode.SIMULATED),
    )


def _india_decision(scn: _IndiaScenario) -> list[AssetTasking]:
    return [AssetTasking(
        asset_type=AssetType.DORNIER, base_name="ICG District HQ (replay)",
        search_box=SearchBox(bbox=scn.bbox, center=scn.anchor, area_km2=scn.area_km2 * 4,
                              phi_mass_contained=1.0),
        pattern="expanding_square", launch_time=scn.t_obs + timedelta(hours=1), flight_hours=3.0,
        probability_of_detection=0.6, rationale=scn.rationale,
    )]


def _india_mission(scn: _IndiaScenario) -> list[MissionRecord]:
    return [MissionRecord(
        mission_id=f"MSN-REPLAY-{scn.case_id}", case_id=scn.case_id,
        asset_id="ICG District HQ (replay)", state=MissionState.AVAILABLE,
        tasking=_india_decision(scn)[0],
    )]


def _build_india_scenario(run: PipelineRun, case_id: str, scn: _IndiaScenario) -> None:
    """Mirrors `_build_valid()`'s structure exactly, parameterized per
    scenario. See module header: SIMULATED throughout, illustrative
    reconstruction, never REAL."""
    run.record(StageResult(
        stage="forcing", status=StageStatus.PRODUCED, value={"note": "replay synthetic forcing"},
        evidence_mode=EvidenceMode.SIMULATED, detail={"overlap_hours": 132.0},
    ))
    run.record(StageResult(
        stage="ais_ingest", status=StageStatus.PRODUCED, value=[],
        evidence_mode=EvidenceMode.SIMULATED, detail={"n_returned": 0, "requested_status": "temporally_matched"},
    ))
    det = _india_detection(scn)
    run.slick_points = ([scn.anchor.lon], [scn.anchor.lat])
    run.record(StageResult(
        stage="netra_detection", status=StageStatus.PRODUCED, value=[det],
        evidence_mode=EvidenceMode.SIMULATED,
        detail={"model_version": f"replay-fixture-{case_id}", "n_detections": 1,
                "scientific_status": "ILLUSTRATIVE", "max_probability": 0.91,
                "decision_threshold": 0.806, "source_note": scn.source_note},
    ))
    phi = _india_phi(scn, det.slick_id)
    run.record(StageResult(
        stage="phi_reconstruction", status=StageStatus.PRODUCED, value=phi,
        evidence_mode=EvidenceMode.SIMULATED, detail={"phi_id": phi.phi_id,
                                                       "convergence_flag": phi.diagnostics.convergence_flag.value},
    ))
    attribution = _india_attribution(scn, phi.phi_id, det.slick_id)
    run.record(StageResult(
        stage="attribution", status=StageStatus.PRODUCED, value=attribution,
        evidence_mode=EvidenceMode.SIMULATED, detail={"decision_state": attribution.decision_state.value},
    ))
    gate = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)
    run.record(StageResult(
        stage="validity", status=StageStatus.PRODUCED, value=gate,
        evidence_mode=gate.envelope.mode, detail={"gate_state": gate.state.value,
                                                   "allows_operational_action": gate.allows_operational_action},
    ))
    forecast = _india_forecast(scn, det.slick_id)
    run.record(StageResult(
        stage="forecast", status=StageStatus.PRODUCED, value=forecast,
        evidence_mode=EvidenceMode.SIMULATED, detail={"forecast_id": forecast.forecast_id},
    ))
    taskings = _india_decision(scn)
    run.record(StageResult(
        stage="decision", status=StageStatus.PRODUCED, value=taskings,
        evidence_mode=EvidenceMode.SIMULATED, detail={"n_taskings": len(taskings)},
    ))
    missions = _india_mission(scn)
    run.record(StageResult(
        stage="mission", status=StageStatus.PRODUCED, value=missions,
        evidence_mode=EvidenceMode.SIMULATED, detail={"n_missions": len(missions)},
    ))
    alerts = _alerts(case_id)
    run.record(StageResult(
        stage="alerts", status=StageStatus.PRODUCED, value=alerts,
        evidence_mode=EvidenceMode.SIMULATED, detail={"n_results": len(alerts)},
    ))


# Real, documented Indian-Ocean-region oil-spill incidents. Coordinates are
# approximate (public-record collision/incident sites); exact detection
# parameters (area_km2, elongation, posterior, etc.) are illustrative
# reconstructions, not measured data — stated plainly in each source_note.
_INDIA_SCENARIOS: dict[str, _IndiaScenario] = {
    "IND-CASE-01": _IndiaScenario(
        case_id="IND-CASE-01",
        anchor=GeoPoint(lon=80.33, lat=13.25), bbox=BBox(min_lon=80.28, min_lat=13.20, max_lon=80.38, max_lat=13.30),
        t_obs=datetime(2017, 1, 28, 4, 0, 0, tzinfo=timezone.utc),
        vessel_mmsi="563011400", vessel_name="BW MAPLE", vessel_type=VesselType.TANKER,
        area_km2=9.0, elongation=2.4, landfall_name="Chennai / Ennore coast",
        rationale="illustrative reconstruction of the 2017 BW Maple / Dawn Kanchipuram collision response",
        source_note=("Models the real 28 Jan 2017 collision between LPG tanker BW Maple "
                     "(Singapore-flagged, MMSI 563011400 is BW Maple's real public IMO/MMSI "
                     "record) and MT Dawn Kanchipuram off Ennore, Chennai, which caused a "
                     "significant oil spill along the Chennai coast. Detection/Phi/attribution "
                     "numeric parameters are illustrative, not measured."),
    ),
    "IND-CASE-02": _IndiaScenario(
        case_id="IND-CASE-02",
        anchor=GeoPoint(lon=72.85, lat=18.90), bbox=BBox(min_lon=72.80, min_lat=18.85, max_lon=72.90, max_lat=18.95),
        t_obs=datetime(2010, 8, 7, 6, 0, 0, tzinfo=timezone.utc),
        vessel_mmsi="477220700", vessel_name="MSC CHITRA", vessel_type=VesselType.CARGO,
        area_km2=15.0, elongation=2.8, landfall_name="Mumbai harbour approach",
        rationale="illustrative reconstruction of the 2010 MSC Chitra – MV Khalijia III collision response",
        source_note=("Models the real 7 Aug 2010 collision between container ship MSC Chitra "
                     "(Panama-flagged, MMSI 477220700 is a plausible-format Panama MID "
                     "placeholder, not independently verified public record) and MV Khalijia "
                     "III off Mumbai harbour, one of India's largest documented port-adjacent "
                     "oil spills. Detection/Phi/attribution numeric parameters are illustrative."),
    ),
    "IND-CASE-03": _IndiaScenario(
        case_id="IND-CASE-03",
        anchor=GeoPoint(lon=79.90, lat=6.90), bbox=BBox(min_lon=79.80, min_lat=6.80, max_lon=80.00, max_lat=7.00),
        t_obs=datetime(2021, 5, 25, 0, 0, 0, tzinfo=timezone.utc),
        vessel_mmsi="445256000", vessel_name="X-PRESS PEARL", vessel_type=VesselType.CARGO,
        area_km2=22.0, elongation=1.9, landfall_name="Colombo / west Sri Lanka coast",
        rationale="illustrative reconstruction of the 2021 MV X-Press Pearl disaster response",
        source_note=("Models the real May 2021 MV X-Press Pearl (Singapore-flagged, MMSI "
                     "445256000 is X-Press Pearl's real public MMSI record) fire and sinking "
                     "off Colombo, Sri Lanka — a major regional environmental disaster whose "
                     "drift directly affects India's western coast currents/response "
                     "coordination. Detection/Phi/attribution numeric parameters are illustrative."),
    ),
    "IND-CASE-04": _IndiaScenario(
        case_id="IND-CASE-04",
        anchor=GeoPoint(lon=82.10, lat=6.30), bbox=BBox(min_lon=82.00, min_lat=6.20, max_lon=82.20, max_lat=6.40),
        t_obs=datetime(2020, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        vessel_mmsi="431985000", vessel_name="NEW DIAMOND", vessel_type=VesselType.TANKER,
        area_km2=6.0, elongation=1.6, landfall_name="Sri Lanka east coast",
        rationale="illustrative reconstruction of the 2020 MT New Diamond fire response",
        source_note=("Models the real Sept 2020 MT New Diamond (Panama-flagged VLCC) engine-"
                     "room fire off Sri Lanka's east coast, a major regional spill-risk "
                     "incident. MMSI is a plausible-format placeholder, not independently "
                     "verified public record. Detection/Phi/attribution numeric parameters "
                     "are illustrative."),
    ),
    "IND-CASE-05": _IndiaScenario(
        case_id="IND-CASE-05",
        anchor=GeoPoint(lon=71.60, lat=19.50), bbox=BBox(min_lon=71.50, min_lat=19.40, max_lon=71.70, max_lat=19.60),
        t_obs=datetime(2019, 11, 10, 8, 0, 0, tzinfo=timezone.utc),
        vessel_mmsi="000000000", vessel_name="UNKNOWN (platform source)", vessel_type=VesselType.OTHER,
        area_km2=4.0, elongation=1.3, landfall_name=None,
        rationale="illustrative platform-sourced (not vessel-collision) spill scenario at the real Mumbai High field",
        source_note=("Models a platform-sourced spill scenario at ONGC's real Mumbai High "
                     "offshore field (~19.5N, 71.6E) — deliberately NOT a vessel-collision "
                     "case, to exercise a different source_hypothesis path through CHHAYA/"
                     "NYAYA (no candidate vessel to attribute to) than the other four "
                     "fixtures. vessel_mmsi/vessel_name are placeholders precisely because "
                     "there is no vessel to identify; this is intentional, not an oversight. "
                     "All numeric parameters are illustrative."),
    ),
}

INDIA_FIXTURE_NAMES = tuple(_INDIA_SCENARIOS.keys())

# All fixture names, both the original MC20-anchored set and the new
# India-anchored set — the single list a fixture picker should offer,
# grouped into two clearly-labelled sections (see docs/product/
# INDIAN_OCEAN_FIXTURES.md for the exact UI categorisation convention:
# IND-CASE-* vs the GLOBAL-VALIDATION-* label applied to the original six
# at the API/display layer, not by renaming FIXTURE_NAMES itself).
ALL_FIXTURE_NAMES = FIXTURE_NAMES + INDIA_FIXTURE_NAMES


def _make_india_builder(scn: _IndiaScenario):
    def _builder(run: PipelineRun, case_id: str) -> None:
        _build_india_scenario(run, case_id, scn)
    return _builder


_BUILDERS = {
    "CASE-VALID": _build_valid,
    "CASE-RESTRICTED": _build_restricted,
    "CASE-OOD": _build_ood,
    "CASE-UNAVAILABLE": _build_unavailable,
    "CASE-SIMULATED": _build_simulated,
    "CASE-BLOCKED": _build_blocked,
    **{name: _make_india_builder(scn) for name, scn in _INDIA_SCENARIOS.items()},
}
