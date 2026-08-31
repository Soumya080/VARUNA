"""
Phases 5-14 - the live MC20 case pipeline.

    Event Gold -> NETRA -> PRATIVARTAN -> Phi -> AIS -> NYAYA -> Validity
               -> PRAVAAH -> ABHIYAN -> Mission FSM -> Alerts -> OperatorCase

Every stage is a call into the subsystem that owns the computation. This module
decides only *ordering*, *what to do when a stage produces nothing*, and *how
provenance combines*. There is no science here: no probability, no centroid, no
ranking, no threshold is computed in this file.

Error propagation (Phase 13)
----------------------------
A stage that cannot produce its output does not raise and does not substitute a
value. It records BLOCKED or NOT_YET_PRODUCED with a named reason, and every
stage downstream of it records BLOCKED naming the upstream stage. A run always
terminates in a complete, honest set of stage records - `PipelineRun.blocked_at`
tells you where it stopped.

Evidence mode (Phase 14)
------------------------
Each stage's mode comes from the contract its producer returned. The run-level
mode is `worst_mode()` over every stage that produced something, so:

    REAL + REAL          -> REAL
    REAL + SIMULATED     -> SIMULATED
    UNAVAILABLE + any    -> UNAVAILABLE

Nothing in this module can raise a mode. The one place a SIMULATED input could
become REAL - the NETRA placeholder - is blocked by `NetraDetectionBoundary`'s
own constructor.
"""
from __future__ import annotations

# Schema imports first (netCDF4/Windows DLL interaction - see forcing.py).
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance  # isort: skip

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from varuna_integration.ais_source import AISJoinStatus, EventAISAdapter, load_event_tracks
from varuna_integration.forcing import EventForcing, load_event_forcing
from varuna_integration.netra_boundary import NetraDetectionBoundary
from varuna_integration.stage import StageResult, StageStatus, worst_mode


# Largest observation-time clamp a SCIENTIFIC run will tolerate. Sized to the
# ~1h forcing resolution: a sub-step nudge onto the grid is fine, a move
# across the diurnal current cycle is not.
MAX_SCIENTIFIC_CLAMP_HOURS = 2.0


@dataclass
class PipelineConfig:
    """Everything tunable, injected. No path or scale is hardcoded downstream."""

    gold_dir: Path
    n_particles: int = 20
    n_ensemble: int = 4
    backward_duration_hours: float = 24.0
    forecast_horizon_hours: float = 24.0
    seed: int = 42
    age_prior_mean_hours: float = 24.0
    age_prior_std_hours: float = 12.0
    latent_prior: float = 0.5
    corridor_width_km: float = 5.0
    max_ais_tracks: int = 5
    ais_status: AISJoinStatus = AISJoinStatus.TEMPORALLY_MATCHED
    max_netra_tiles: int = 9
    # Marks a run whose ensemble scale is too small to be a scientific result.
    # `INTEGRATION_SMOKE` is stamped onto the run record and every report.
    run_class: str = "INTEGRATION_SMOKE"

    @property
    def is_scientific(self) -> bool:
        return self.run_class == "SCIENTIFIC"


@dataclass
class PipelineRun:
    run_id: str
    case_id: str
    started_at: datetime
    config: PipelineConfig
    stages: dict[str, StageResult] = field(default_factory=dict)
    finished_at: datetime | None = None
    # The observation point cloud the reconstruction actually used. NYAYA must
    # score against the SAME points, not a re-derivation from Phi.
    slick_points: tuple = ()

    def record(self, result: StageResult) -> StageResult:
        self.stages[result.stage] = result
        return result

    def blocked_by(self, stage: str, upstream: str, upstream_reason: str) -> StageResult:
        """Propagate an upstream stage's own status, never a worse one.

        BLOCKED means a genuine integration break. If the upstream stage merely
        had nothing to produce - the model found no slick, which is a valid
        scientific outcome - then this stage did not break either, and calling it
        BLOCKED would make "nothing detected" indistinguishable from "the
        pipeline is broken". That is the same conflation this module refuses to
        make for the validity gate.
        """
        upstream_result = self.stages.get(upstream)
        status = (upstream_result.status
                  if upstream_result is not None
                  and upstream_result.status is StageStatus.NOT_YET_PRODUCED
                  else StageStatus.BLOCKED)
        return self.record(StageResult(
            stage=stage, status=status,
            reason=f"UPSTREAM_{upstream.upper()}_UNAVAILABLE: {upstream_reason}",
        ))

    @property
    def blocked_at(self) -> str | None:
        for name, s in self.stages.items():
            if s.status is StageStatus.BLOCKED:
                return name
        return None

    @property
    def evidence_mode(self) -> EvidenceMode | None:
        return worst_mode(*(s.evidence_mode for s in self.stages.values()))

    @property
    def total_seconds(self) -> float:
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "run_class": self.config.run_class,
            "scientific_result": self.config.is_scientific,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_seconds": self.total_seconds,
            "evidence_mode": self.evidence_mode.value if self.evidence_mode else None,
            "blocked_at": self.blocked_at,
            "config": {
                "gold_dir": str(self.config.gold_dir),
                "n_particles": self.config.n_particles,
                "n_ensemble": self.config.n_ensemble,
                "backward_duration_hours": self.config.backward_duration_hours,
                "forecast_horizon_hours": self.config.forecast_horizon_hours,
                "seed": self.config.seed,
                "ais_status": self.config.ais_status.value,
            },
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
        }


class RealE2EPipeline:
    """Composes the real producers over one event.

    `netra` may be None: that is the honest state while no frozen checkpoint
    exists, and it makes the detection stage report NOT_YET_PRODUCED rather
    than inventing slick geometry.
    """

    def __init__(self, config: PipelineConfig, *, netra: NetraDetectionBoundary | None = None,
                 mission_service: Any = None, alert_service: Any = None):
        self.config = config
        self.netra = netra
        self.mission_service = mission_service
        self.alert_service = alert_service

    # ---------------------------------------------------------------- run

    def run(self, case_id: str | None = None) -> PipelineRun:
        cfg = self.config
        manifest = json.loads((cfg.gold_dir / "manifest.json").read_text(encoding="utf-8"))
        run = PipelineRun(
            run_id=f"RUN-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}",
            case_id=case_id or manifest["event_id"],
            started_at=datetime.now(timezone.utc),
            config=cfg,
        )

        forcing_res = run.record(load_event_forcing(cfg.gold_dir))
        detection_res = run.record(self._detect(manifest))
        _annotate_wind_context(detection_res, forcing_res)
        ais_res = run.record(self._ais())

        phi_res = self._reconstruct(run, manifest, forcing_res, detection_res)
        attribution_res = self._attribute(run, phi_res, ais_res)
        validity_res = self._validity(run, phi_res, attribution_res)
        forecast_res = self._forecast(run, forcing_res, detection_res, validity_res)
        decision_res = self._decide(run, phi_res, validity_res)
        mission_res = self._mission(run, decision_res, validity_res)
        self._alerts(run, validity_res, mission_res)

        run.finished_at = datetime.now(timezone.utc)
        return run

    # ------------------------------------------------------- Phase 2: NETRA

    def _detect(self, manifest: dict) -> StageResult:
        if self.netra is None:
            return StageResult(
                stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
                reason=(
                    "NETRA_NOT_AVAILABLE: no frozen checkpoint is registered and no "
                    "simulated stand-in was explicitly requested, so no slick "
                    "geometry exists for this case."
                ),
            )
        tiles = sorted((self.config.gold_dir / "sar" / "tiles").glob("*.npy"))
        return self.netra.detect_tiles(
            tiles[: self.config.max_netra_tiles], manifest["event_id"]
        )

    # --------------------------------------------------------- Phase 3: AIS

    def _ais(self) -> StageResult:
        join_path = self.config.gold_dir / "ais" / "event_ais_join.json"
        if not join_path.exists():
            return StageResult(
                stage="ais_ingest", status=StageStatus.BLOCKED,
                evidence_mode=EvidenceMode.UNAVAILABLE,
                reason=f"AIS_JOIN_MISSING: {join_path} does not exist.",
            )
        from varuna_source_adapters.protocol import SourceQuery

        adapter = EventAISAdapter(join_path)
        join = adapter.join()
        query = SourceQuery(
            bbox=join.sar_footprint,
            time_start=join.t_sar - timedelta(hours=join.window_before_hours),
            time_end=join.t_sar + timedelta(hours=join.window_after_hours),
            product_id="AIS_EVENT_GOLD",
        )
        return load_event_tracks(adapter, query, status=self.config.ais_status,
                                 limit=self.config.max_ais_tracks)

    # ------------------------------------------------- Phase 5: PRATIVARTAN

    def _reconstruct(self, run: PipelineRun, manifest: dict,
                     forcing_res: StageResult, detection_res: StageResult) -> StageResult:
        if not forcing_res.produced:
            return run.blocked_by("phi_reconstruction", "forcing", forcing_res.reason or "")
        if not detection_res.produced:
            return run.record(StageResult(
                stage="phi_reconstruction", status=StageStatus.NOT_YET_PRODUCED,
                reason=(
                    "NO_SLICK_GEOMETRY: backward reconstruction needs a detected "
                    f"slick. Detection stage says: {detection_res.reason}"
                ),
            ))

        from varuna_prativartan.config import PratiConfig
        from varuna_prativartan.ensemble import run_backward_ensemble
        from varuna_prativartan.phi_builder import build_phi_field

        cfg = self.config
        forcing: EventForcing = forcing_res.value
        detection = detection_res.value[0]

        slick_lons, slick_lats = _slick_points_from_detection(
            detection, cfg.seed, n=cfg.n_particles)
        run.slick_points = (slick_lons, slick_lats)
        from varuna_prativartan.cube_field import PHI_EPOCH

        obs_hours = (detection.observation_time - PHI_EPOCH).total_seconds() / 3600.0
        obs_clamped, was_clamped = forcing.clamp_time(obs_hours)
        # The boolean alone is not enough. A clamp of a few hours is a benign
        # edge adjustment; a clamp of days or years means the observation was
        # advected against a current regime unrelated to the event. Both set
        # the same flag, so record the MAGNITUDE and refuse the large case on a
        # scientific run. Measured on MC20: the same seed and duration loses 0%
        # of its particles at the window edge and 70% at the true acquisition
        # time, so a large clamp does not merely add error - it silently
        # selects a different physical answer.
        obs_clamp_delta_hours = obs_clamped - obs_hours
        if cfg.is_scientific and abs(obs_clamp_delta_hours) > MAX_SCIENTIFIC_CLAMP_HOURS:
            return run.record(StageResult(
                stage="phi_reconstruction", status=StageStatus.BLOCKED,
                reason=(
                    "OBS_TIME_OUTSIDE_FORCING_WINDOW: the detection's observation "
                    f"time sits {abs(obs_clamp_delta_hours):.1f}h outside the "
                    "ERA5/CMEMS overlap and would have to be moved there to run. "
                    f"A scientific run tolerates at most "
                    f"{MAX_SCIENTIFIC_CLAMP_HOURS:.1f}h. Advecting at a clamped "
                    "time answers a different question than the one asked."
                ),
            ))

        # Provenance: the reconstruction input inherits from BOTH the forcing
        # envelope and the detection envelope, so a simulated detection makes
        # the whole downstream lineage simulated (monotonic worsening).
        detection_env = EvidenceEnvelope(
            artifact_id=f"detection-{detection.slick_id}",
            produced_by="netra",
            provenance=Provenance(
                source_id="netra.detection",
                notes=f"model_version={detection.netra_model_version}",
            ),
            mode=detection_res.evidence_mode or EvidenceMode.UNAVAILABLE,
        )
        base_env = forcing.envelope.derive(
            artifact_id=f"reconstruction-input-{run.case_id}",
            produced_by="varuna_integration.pipeline",
            also_from=[detection_env],
        )

        # `run_backward_ensemble` subsamples with `min(n_particles, n_obs)` and
        # does so silently, so a requested particle count is only realised if at
        # least that many observation points exist. Compute what will actually
        # be advected and refuse to label an under-resolved run SCIENTIFIC —
        # reporting a requested 500 while advecting 12 would be a fabricated
        # scientific parameter.
        n_particles_advected = min(cfg.n_particles, len(slick_lons))
        if cfg.is_scientific and n_particles_advected < cfg.n_particles:
            return run.record(StageResult(
                stage="phi_reconstruction", status=StageStatus.BLOCKED,
                reason=(
                    "PARTICLE_COUNT_UNDER_RESOLVED: run_class=SCIENTIFIC requested "
                    f"{cfg.n_particles} particles but only {len(slick_lons)} "
                    "observation points exist, so the ensemble would silently "
                    f"advect {n_particles_advected}. Refusing to report a "
                    "requested count that was not achieved."
                ),
            ))

        t0 = time.perf_counter()
        try:
            config = PratiConfig(
                n_particles=cfg.n_particles, n_ensemble=cfg.n_ensemble,
                backward_duration_hours=cfg.backward_duration_hours, seed=cfg.seed,
            )
            ensemble = run_backward_ensemble(
                obs_lons=slick_lons, obs_lats=slick_lats, obs_time_hours=obs_clamped,
                current=forcing.current_field, wind=forcing.wind_field, config=config,
            )
            runtime = time.perf_counter() - t0
            phi = build_phi_field(
                ensemble_results=ensemble, case_id=run.case_id,
                slick_id=detection.slick_id, input_envelope=base_env,
                obs_time_hours=obs_clamped,
                age_prior_mean_hours=cfg.age_prior_mean_hours,
                age_prior_std_hours=cfg.age_prior_std_hours,
                config=config, runtime_seconds=runtime,
            )
        except Exception as exc:
            return run.record(StageResult(
                stage="phi_reconstruction", status=StageStatus.BLOCKED,
                reason=f"PRATIVARTAN_FAILED: {type(exc).__name__}: {exc}",
                runtime_seconds=time.perf_counter() - t0,
            ))

        return run.record(StageResult(
            stage="phi_reconstruction", status=StageStatus.PRODUCED, value=phi,
            evidence_mode=phi.envelope.mode,
            runtime_seconds=time.perf_counter() - t0,
            detail={
                "phi_id": phi.phi_id,
                "convergence_flag": phi.diagnostics.convergence_flag.value,
                "ensemble_completeness": phi.diagnostics.ensemble_completeness,
                # Surfaced because >20% loss degrades the field (see
                # PhiDiagnostics), and the dominant cause on a coastal event is
                # the CMEMS land mask: backward-advected particles that enter a
                # masked cell go NaN and never return. Reporting the degraded
                # flag without the count would show the symptom and hide the
                # cause.
                "particles_seeded": phi.diagnostics.particles_seeded,
                "particles_lost": phi.diagnostics.particles_lost,
                "particle_loss_fraction": (
                    phi.diagnostics.particles_lost / phi.diagnostics.particles_seeded
                    if phi.diagnostics.particles_seeded else None),
                "sensitivity": (phi.sensitivity.model_dump(mode="json")
                                if phi.sensitivity is not None else None),
                "n_ensemble_completed": len(ensemble),
                "n_ensemble_requested": cfg.n_ensemble,
                "n_particles_advected": n_particles_advected,
                "n_particles_requested": cfg.n_particles,
                "obs_time_hours": obs_clamped,
                "obs_time_clamped_into_forcing_window": was_clamped,
                "obs_time_clamp_delta_hours": obs_clamp_delta_hours,
                "run_class": cfg.run_class,
            },
        ))

    # ------------------------------------------------------- Phase 6: NYAYA

    def _attribute(self, run: PipelineRun, phi_res: StageResult,
                   ais_res: StageResult) -> StageResult:
        if not phi_res.produced:
            return run.blocked_by("attribution", "phi_reconstruction", phi_res.reason or "")
        if not ais_res.produced:
            return run.record(StageResult(
                stage="attribution", status=StageStatus.BLOCKED,
                reason=(
                    "AIS_UNAVAILABLE_FOR_ATTRIBUTION: NYAYA cannot rank vessels "
                    f"without tracks. AIS stage says: {ais_res.reason}"
                ),
            ))

        from varuna_nyaya.services import NyayaService

        phi = phi_res.value
        tracks = ais_res.value
        slick_lons, slick_lats = run.slick_points

        tracks_env = EvidenceEnvelope(
            artifact_id=f"ais-{run.case_id}",
            produced_by="varuna_integration.ais_source",
            provenance=Provenance(
                source_id=ais_res.detail.get("source_id", "ais.event_gold"),
                notes=(
                    f"{ais_res.detail.get('n_returned')} tracks with status "
                    f"{ais_res.detail.get('requested_status')}; spatial candidacy "
                    "is not temporal evidence"
                ),
            ),
            mode=ais_res.evidence_mode or EvidenceMode.UNAVAILABLE,
        )

        t0 = time.perf_counter()
        try:
            attribution = NyayaService().attribute(
                phi=phi, tracks=tracks, case_id=run.case_id,
                slick_lons=slick_lons, slick_lats=slick_lats,
                corridor_width_km=self.config.corridor_width_km,
                latent_prior=self.config.latent_prior,
                tracks_envelope=tracks_env,
            )
        except Exception as exc:
            return run.record(StageResult(
                stage="attribution", status=StageStatus.BLOCKED,
                reason=f"NYAYA_FAILED: {type(exc).__name__}: {exc}",
                runtime_seconds=time.perf_counter() - t0,
            ))

        return run.record(StageResult(
            stage="attribution", status=StageStatus.PRODUCED, value=attribution,
            evidence_mode=attribution.envelope.mode,
            runtime_seconds=time.perf_counter() - t0,
            detail={
                "decision_state": attribution.decision_state.value,
                "n_candidates": len(attribution.candidates),
                "latent_probability": attribution.latent_probability,
            },
        ))

    # ---------------------------------------------------- Phase 7: VALIDITY

    def _validity(self, run: PipelineRun, phi_res: StageResult,
                  attribution_res: StageResult) -> StageResult:
        if not phi_res.produced:
            return run.blocked_by("validity", "phi_reconstruction", phi_res.reason or "")
        if not attribution_res.produced:
            return run.blocked_by("validity", "attribution", attribution_res.reason or "")

        from varuna_nyaya.services import ValidityService

        t0 = time.perf_counter()
        try:
            gate = ValidityService().evaluate(phi_res.value, attribution_res.value)
        except Exception as exc:
            return run.record(StageResult(
                stage="validity", status=StageStatus.BLOCKED,
                reason=f"VALIDITY_GATE_FAILED: {type(exc).__name__}: {exc}",
                runtime_seconds=time.perf_counter() - t0,
            ))

        # A gate that denies operational action is a SUCCESSFUL evaluation with
        # a restrictive answer - PRODUCED, not BLOCKED. Collapsing the two
        # would make "the gate said no" indistinguishable from "the gate
        # crashed", and would tempt someone to "fix" the former.
        return run.record(StageResult(
            stage="validity", status=StageStatus.PRODUCED, value=gate,
            evidence_mode=gate.envelope.mode,
            runtime_seconds=time.perf_counter() - t0,
            detail={
                "gate_state": gate.state.value,
                "allows_operational_action": gate.allows_operational_action,
                "failing_checks": [c.name for c in gate.checks if not c.passed],
                "blocking_reasons": list(gate.blocking_reasons),
                "officer_visible_caveats": list(gate.officer_visible_caveats),
                "source_trust": gate.source_trust.value,
            },
        ))

    # ----------------------------------------------------- Phase 8: PRAVAAH

    def _forecast(self, run: PipelineRun, forcing_res: StageResult,
                  detection_res: StageResult, validity_res: StageResult) -> StageResult:
        if not forcing_res.produced:
            return run.blocked_by("forecast", "forcing", forcing_res.reason or "")
        if not detection_res.produced:
            return run.record(StageResult(
                stage="forecast", status=StageStatus.NOT_YET_PRODUCED,
                reason=(
                    "NO_SLICK_TO_FORECAST: forward drift needs a detected slick. "
                    f"Detection stage says: {detection_res.reason}"
                ),
            ))
        if not detection_res.value:
            # `detection_res.produced` is True but the value list is empty --
            # unreachable through NetraDetectionBoundary.detect_tiles() today
            # (it returns NOT_YET_PRODUCED rather than PRODUCED with an empty
            # list), but that is an implicit invariant of one caller, not
            # something this stage should trust blindly. Fail closed with a
            # named reason instead of an uncaught IndexError on
            # `detection_res.value[0]` crashing the whole pipeline run.
            return run.record(StageResult(
                stage="forecast", status=StageStatus.BLOCKED,
                reason=(
                    "MALFORMED_DETECTION_RESULT: detection stage reported PRODUCED "
                    "but carries no detections to forecast from."
                ),
            ))

        from varuna_pravaah.cube_provider import CubeBackedPravaahProvider

        forcing: EventForcing = forcing_res.value
        detection = detection_res.value[0]
        t0 = time.perf_counter()
        try:
            u, v = forcing.current_field._u_grid, forcing.current_field._v_grid
            provider = CubeBackedPravaahProvider(forcing.cmems_cube, u, v)
            # `forcing.envelope.case_id` is None -- load_event_forcing() builds
            # it from gold_dir alone, before any case_id is in scope, and
            # EvidenceEnvelope.derive() always inherits case_id from `self`
            # (there is no override parameter, by ADR-0006 design: mode/lineage
            # fields are derived, not asserted by a caller). Left as-is, every
            # envelope in this run would carry case_id=None, including the one
            # attached to ForwardForecast, even though the real case_id (run.
            # case_id) is right here in scope. This is scoped to the forecast
            # stage only -- _reconstruct()/_attribute() derive from the same
            # forcing.envelope and share this gap, but fixing it there would
            # touch PRATIVARTAN/NYAYA's stage code, which is out of this task's
            # PRAVAAH-integration mandate (Track 2 is frozen). Use a local copy
            # so this does not mutate the shared EventForcing.envelope object
            # those other stages also read.
            forcing_env_with_case = forcing.envelope.model_copy(update={"case_id": run.case_id})
            # The forecast's own envelope must worsen with the DETECTION's
            # evidence mode too, not just forcing's -- a SIMULATED detection
            # (e.g. SimulatedSlickProvider on a real MC20 corpus) drifted
            # through a real current field must still report SIMULATED
            # overall (ADR-0006 monotonic worsening), matching what this same
            # stage already computes separately for StageResult.evidence_mode
            # below (`worst_mode(forcing_res.evidence_mode,
            # detection_res.evidence_mode)`). Deriving from forcing alone, as
            # this previously did, let a SIMULATED detection's forecast claim
            # REAL on the artifact itself even while the stage-level record
            # correctly said SIMULATED -- two disagreeing answers to "how
            # real is this artifact," found by this task's own test.
            detection_env = EvidenceEnvelope(
                artifact_id=f"detection-{detection.slick_id}",
                produced_by="netra",
                provenance=Provenance(
                    source_id="netra.detection",
                    notes=f"model_version={detection.netra_model_version}",
                ),
                mode=detection_res.evidence_mode or EvidenceMode.UNAVAILABLE,
            )
            parent = forcing_env_with_case.derive(
                artifact_id=f"forecast-input-{run.case_id}",
                produced_by="varuna_integration.pipeline",
                also_from=[detection_env],
            )
            forecast = provider.forecast_drift(
                slick=detection, forcing_path=None,
                horizon_hours=self.config.forecast_horizon_hours, envelope=parent,
            )
        except Exception as exc:
            return run.record(StageResult(
                stage="forecast", status=StageStatus.BLOCKED,
                reason=f"PRAVAAH_FAILED: {type(exc).__name__}: {exc}",
                runtime_seconds=time.perf_counter() - t0,
            ))

        mode = worst_mode(forcing_res.evidence_mode, detection_res.evidence_mode)
        return run.record(StageResult(
            stage="forecast", status=StageStatus.PRODUCED, value=forecast,
            evidence_mode=mode, runtime_seconds=time.perf_counter() - t0,
            detail={
                "forecast_id": forecast.forecast_id,
                "horizon_hours": forecast.horizon_hours,
                "n_landfalls": len(forecast.landfalls),
                "provider_version": provider.get_model_version(),
            },
        ))

    # ----------------------------------------------------- Phase 9: ABHIYAN

    def _decide(self, run: PipelineRun, phi_res: StageResult,
                validity_res: StageResult) -> StageResult:
        if not validity_res.produced:
            return run.blocked_by("decision", "validity", validity_res.reason or "")

        from varuna_abhiyan.mock import MockAbhiyanProvider
        from varuna_abhiyan.service import AbhiyanService
        from varuna_contracts.schemas import AssetType

        gate = validity_res.value
        phi = phi_res.value if phi_res.produced else None
        search_boxes = _search_boxes_from_phi(phi) if phi is not None else []

        t0 = time.perf_counter()
        try:
            taskings, env = AbhiyanService(MockAbhiyanProvider()).plan_mission(
                search_boxes=search_boxes,
                available_assets=[AssetType.DORNIER, AssetType.OPV],
                gate_state=gate.state,
                parent_envelope=gate.envelope,
                case_id=run.case_id,
            )
        except Exception as exc:
            return run.record(StageResult(
                stage="decision", status=StageStatus.BLOCKED,
                reason=f"ABHIYAN_FAILED: {type(exc).__name__}: {exc}",
                runtime_seconds=time.perf_counter() - t0,
            ))

        if not taskings:
            return run.record(StageResult(
                stage="decision", status=StageStatus.NOT_YET_PRODUCED,
                reason=(
                    "NO_TASKING: ABHIYAN produced no tasking because the validity "
                    f"gate state is {gate.state.value} "
                    f"(allows_operational_action={gate.allows_operational_action}). "
                    "This is the fail-closed contract working, not a failure."
                ),
                evidence_mode=env.mode,
                runtime_seconds=time.perf_counter() - t0,
                detail={"gate_state": gate.state.value, "n_search_boxes": len(search_boxes)},
            ))

        return run.record(StageResult(
            stage="decision", status=StageStatus.PRODUCED, value=taskings,
            evidence_mode=env.mode, runtime_seconds=time.perf_counter() - t0,
            detail={
                "n_taskings": len(taskings),
                "asset_types": [t.asset_type.value for t in taskings],
                "gate_state": gate.state.value,
            },
        ))

    # ---------------------------------------------------- Phase 10: MISSION

    def _mission(self, run: PipelineRun, decision_res: StageResult,
                 validity_res: StageResult) -> StageResult:
        if self.mission_service is None:
            return run.record(StageResult(
                stage="mission", status=StageStatus.NOT_YET_PRODUCED,
                reason="NO_MISSION_RUNTIME: no MissionService was injected into the pipeline.",
            ))
        if not decision_res.produced:
            return run.record(StageResult(
                stage="mission", status=StageStatus.NOT_YET_PRODUCED,
                reason=(
                    "NO_TASKING_TO_PROPOSE: a mission requires an ABHIYAN tasking. "
                    f"Decision stage says: {decision_res.reason}"
                ),
            ))

        t0 = time.perf_counter()
        missions = []
        try:
            for tasking in decision_res.value:
                # PROPOSED only. No asset is dispatched and no state is advanced
                # to ASSIGNED here: `approve_and_assign()` requires a named human
                # approver, and this pipeline has none. That authorization step is
                # deliberately left to an operator.
                missions.append(self.mission_service.create_mission(
                    case_id=run.case_id, asset_id=tasking.base_name, tasking=tasking,
                ))
        except Exception as exc:
            return run.record(StageResult(
                stage="mission", status=StageStatus.BLOCKED,
                reason=f"MISSION_FSM_FAILED: {type(exc).__name__}: {exc}",
                runtime_seconds=time.perf_counter() - t0,
            ))

        return run.record(StageResult(
            stage="mission", status=StageStatus.PRODUCED, value=missions,
            evidence_mode=decision_res.evidence_mode,
            runtime_seconds=time.perf_counter() - t0,
            detail={
                "n_missions": len(missions),
                "states": [m.state.value for m in missions],
                "human_approved": [m.human_approved_by for m in missions],
                "authorization_note": (
                    "Missions are created un-approved. Advancing to ASSIGNED "
                    "requires MissionService.approve_and_assign(approved_by=...) "
                    "with a named human."
                ),
            },
        ))

    # ----------------------------------------------------- Phase 11: ALERTS

    def _alerts(self, run: PipelineRun, validity_res: StageResult,
                mission_res: StageResult) -> StageResult:
        if self.alert_service is None:
            return run.record(StageResult(
                stage="alerts", status=StageStatus.NOT_YET_PRODUCED,
                reason="NO_ALERT_SERVICE: no AlertService was injected into the pipeline.",
            ))
        if not validity_res.produced:
            return run.blocked_by("alerts", "validity", validity_res.reason or "")

        gate = validity_res.value
        event_type = "validity.evaluated"
        t0 = time.perf_counter()
        try:
            results = self.alert_service.route_and_send(
                event_type=event_type, case_id=run.case_id,
                event_timestamp=datetime.now(timezone.utc),
                gate_state=gate.state,
                subject=f"[{run.case_id}] validity={gate.state.value}",
                body=(
                    f"run_id={run.run_id} class={self.config.run_class} "
                    f"gate={gate.state.value} "
                    f"allows_action={gate.allows_operational_action}"
                ),
            )
        except Exception as exc:
            return run.record(StageResult(
                stage="alerts", status=StageStatus.BLOCKED,
                reason=f"ALERT_ROUTING_FAILED: {type(exc).__name__}: {exc}",
                runtime_seconds=time.perf_counter() - t0,
            ))

        # "sent" on a simulated channel is not a delivery. Count only results
        # that both claim to have been sent AND were not flagged simulated.
        delivered = [r for r in results if r.status == "sent" and not r.is_simulated]
        simulated = [r for r in results if r.is_simulated]
        suppressed = [r for r in results if r.status in ("suppressed", "expired")]
        return run.record(StageResult(
            stage="alerts", status=StageStatus.PRODUCED, value=results,
            # An alert that only reached a simulated channel is not evidence of
            # delivery. Report SIMULATED unless something genuinely went out.
            evidence_mode=EvidenceMode.REAL if delivered and not simulated
            else EvidenceMode.SIMULATED,
            runtime_seconds=time.perf_counter() - t0,
            detail={
                "event_type": event_type,
                "n_results": len(results),
                "n_actually_delivered": len(delivered),
                "n_simulated": len(simulated),
                "n_suppressed": len(suppressed),
                "statuses": [r.status for r in results],
                "channels": sorted({r.channel for r in results}),
                "delivery_claim": _delivery_claim(results, delivered, simulated, suppressed),
            },
        ))


# ------------------------------- helpers -------------------------------

# Below this 10m wind speed, surface roughness collapses and low-wind areas
# darken in SAR the same way oil does. It is the classic look-alike condition.
# `NetraService` already uses the same 3.0 m/s figure to raise
# PHYSICALLY_IMPLAUSIBLE; this constant mirrors it rather than inventing a
# second threshold.
LOW_WIND_MS = 3.0


def _annotate_wind_context(detection_res: StageResult, forcing_res: StageResult) -> None:
    """Record the REAL 10m wind speed at each detection, as a diagnostic.

    `NetraService.detect_slicks()` raises an `AnomalyFlag.PHYSICALLY_IMPLAUSIBLE`
    low-wind flag, but only from a wind `.npz` path that nothing in this pipeline
    produces - so that flag has never fired on a real case. Rather than fabricate
    an `.npz` to satisfy it, this samples the real ERA5 field the case already
    loaded and records what the wind actually was.

    This is an observation, not a classification: it does NOT downgrade,
    reclassify or suppress any detection. Deciding that a dark patch is a
    wind-shadow look-alike is NETRA's job, and NETRA has not been given this
    input yet - the gap is recorded here so an operator can see the condition
    rather than being told a verdict this pipeline is not entitled to reach.
    """
    if not detection_res.produced or not forcing_res.produced:
        return
    forcing: EventForcing = forcing_res.value
    from varuna_prativartan.cube_field import PHI_EPOCH

    observations: list[dict[str, Any]] = []
    for det in detection_res.value:
        t_hours = (det.observation_time - PHI_EPOCH).total_seconds() / 3600.0
        t_clamped, clamped = forcing.clamp_time(t_hours)
        try:
            u, v = forcing.wind_field.velocity_at(
                np.array([det.centroid.lon]), np.array([det.centroid.lat]), t_clamped)
            speed = float(np.hypot(u[0], v[0]))
            observations.append({
                "slick_id": det.slick_id,
                "wind_speed_ms": speed,
                "below_low_wind_threshold": speed < LOW_WIND_MS,
                "sampled_time_clamped": clamped,
            })
        except Exception as exc:  # out-of-domain is a real answer, not a crash
            observations.append({
                "slick_id": det.slick_id,
                "wind_speed_ms": None,
                "reason": f"{type(exc).__name__}: {exc}",
            })

    measured = [o["wind_speed_ms"] for o in observations if o.get("wind_speed_ms") is not None]
    detection_res.detail["wind_context"] = {
        "source": "real ERA5 field loaded for this case",
        "low_wind_threshold_ms": LOW_WIND_MS,
        "n_sampled": len(measured),
        "n_below_threshold": sum(1 for o in observations if o.get("below_low_wind_threshold")),
        "min_wind_speed_ms": min(measured) if measured else None,
        "max_wind_speed_ms": max(measured) if measured else None,
        "per_detection": observations,
        "note": (
            "Diagnostic only. No detection was reclassified or suppressed on this "
            "basis - look-alike discrimination belongs to NETRA, which does not "
            "currently receive a wind input."
        ),
    }


def _delivery_claim(results, delivered, simulated, suppressed) -> str:
    """State plainly what did and did not go out. Never claim delivery.

    Suppression by the materiality/freshness rules is a deliberate decision,
    not a failure and not a delivery - it gets its own sentence so an operator
    is never left inferring which happened.
    """
    if not results:
        return "No alert was routed."
    if suppressed and not delivered and not simulated:
        reasons = sorted({r.reason for r in suppressed if r.reason})
        return ("No alert was dispatched: routing suppressed it before any channel "
                f"was attempted ({'; '.join(reasons) or 'no reason recorded'}).")
    if delivered and not simulated:
        return f"{len(delivered)} alert(s) actually delivered."
    if delivered and simulated:
        return (f"{len(delivered)} delivered, {len(simulated)} reached simulated "
                "channels only and must not be counted as delivered.")
    return "No real delivery occurred; every channel that ran reported simulated."

def _slick_points_from_detection(detection, seed: int, *, n: int
                                 ) -> tuple[np.ndarray, np.ndarray]:
    """Sample observation points inside the detection's own bbox.

    PRATIVARTAN takes a point cloud; `SlickDetection` carries a mask path and a
    bbox. Until a mask-to-points extractor exists in NETRA, points are drawn
    inside the REAL detected bbox around the REAL centroid - the geometry comes
    from the detection, only the within-bbox scatter is seeded. This is
    resampling of a real footprint, not an invented location.

    `n` is the caller's particle count and has no default on purpose. The
    ensemble subsamples with `min(n_particles, n_obs)`, so drawing fewer points
    than the requested particle count silently caps the run. Note what a larger
    `n` does and does not buy: these are Monte-Carlo samples of one real
    footprint, so more of them refine the sampling of that footprint - they are
    not additional independent observations.
    """
    rng = np.random.default_rng(seed)
    bb = detection.bbox
    lon_sd = (bb.max_lon - bb.min_lon) / 6.0
    lat_sd = (bb.max_lat - bb.min_lat) / 6.0
    lons = np.clip(rng.normal(detection.centroid.lon, lon_sd, n), bb.min_lon, bb.max_lon)
    lats = np.clip(rng.normal(detection.centroid.lat, lat_sd, n), bb.min_lat, bb.max_lat)
    return lons, lats


def _search_boxes_from_phi(phi) -> list:
    """Build the ABHIYAN search box from Phi's own support.

    Geometry passthrough only. `phi.bbox` is the extent of the Phi grid, so by
    construction it contains the entire distribution - `phi_mass_contained=1.0`
    is a statement of that fact, not an estimate. Narrowing this box to a
    tighter credible region is a real capability, but it belongs in
    PRATIVARTAN (which owns the distribution), not in orchestration code, so it
    is deliberately not attempted here.
    """
    from varuna_contracts.schemas import GeoPoint, SearchBox

    box = phi.bbox
    center = GeoPoint(lon=(box.min_lon + box.max_lon) / 2,
                      lat=(box.min_lat + box.max_lat) / 2)
    dlon = (box.max_lon - box.min_lon) * 111.32 * float(np.cos(np.radians(center.lat)))
    dlat = (box.max_lat - box.min_lat) * 110.57
    area = abs(dlon * dlat)
    if area <= 0:
        return []
    return [SearchBox(bbox=box, center=center, area_km2=area, phi_mass_contained=1.0)]
