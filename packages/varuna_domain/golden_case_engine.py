"""
VARUNA GRID v2 — Golden Case Engine.

THE canonical case runner: case_id + config -> Observation -> Detection ->
PRATIVARTAN -> Phi -> AIS -> NYAYA -> Validity Gate -> PRAVAAH -> ABHIYAN ->
Mission -> Alerts -> OperatorCase. One entry point, `GoldenCaseWorkflow.run_case()`,
for REAL, REPLAY and SIMULATED alike -- there is no separate demo pipeline.

This module computes NO science and invents NO contract. It is glue over two
things that already existed and, until now, never met:

  - `varuna_integration.pipeline.RealE2EPipeline` -- the real ten-stage producer
    chain (forcing/detection/AIS/phi/attribution/validity/forecast/decision/
    mission/alerts), reused via its public `.run()` entry point, unmodified.
  - `varuna_domain.case_workflow`'s persistence pattern -- a `Case` entity,
    `CaseRepository`/`ArtifactRepository`/`EventRepository`, `PramanService`,
    `EventSpine` -- reused, not reimplemented.

What this module actually adds (the gap between those two, confirmed directly
with the session that built the pipeline half -- see
`reports/cases/GOLDEN_CASE_ENGINE_REPORT.md` for the coordination record):

  1. An explicit `CaseStatus` LIFECYCLE, walked for real as a run resolves
     (`derive_case_status()`), not just a per-stage `StageStatus`.
  2. A REPRODUCIBILITY record on every run: run_id, model_version,
     dataset_version, config_hash, code_version, evidence_mode, timestamps.
  3. IDEMPOTENCY: re-running the same case_id under the same config reuses the
     prior run rather than re-creating missions/alerts, unless `force=True`.
  4. ONE mode switch (`EngineMode.REAL` / `REPLAY` / `SIMULATED`) instead of a
     second code path.

Nothing here re-derives a probability, a threshold, or a gate verdict --
every number in a `CaseResult` was computed by the subsystem that owns it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from varuna_contracts.evidence import EvidenceMode
from varuna_domain.entities import Artifact, Case, CaseStatus, ScientificStatus
from varuna_domain.ports import ArtifactRepository, CaseRepository, EventRepository, ObjectStore
from varuna_integration.stage import StageStatus, worst_mode
from varuna_praman.praman import PramanService
from varuna_pravaah.event_spine import EventSpine

# ---------------------------------------------------------------------------
# Engine mode
# ---------------------------------------------------------------------------


class EngineMode(str):
    """Not a StrEnum on purpose -- kept as three plain string constants so a
    `mode == EngineMode.REAL` reads exactly like the `EvidenceMode` idiom the
    rest of the codebase already uses, with no risk of confusing the two
    (importing the wrong `Mode` enum silently is a real failure class this
    avoids by using an unmistakably different name)."""

    REAL = "real"
    REPLAY = "replay"
    SIMULATED = "simulated"


# ---------------------------------------------------------------------------
# Lifecycle mapping
# ---------------------------------------------------------------------------

# Order matters: this is the order `RealE2EPipeline.run()` actually calls
# stages in (packages/varuna_integration/pipeline.py::run). Kept as a literal
# tuple, not derived from the pipeline, so a change there is a visible diff
# here rather than a silent drift -- the two are independently testable
# against each other (see tests/unit/test_golden_case_engine.py).
STAGE_ORDER: tuple[str, ...] = (
    "forcing", "ais_ingest", "netra_detection", "phi_reconstruction",
    "attribution", "validity", "forecast", "decision", "mission", "alerts",
)

# The CaseStatus a case is considered to have "reached" once the named stage
# has resolved (produced, or honestly found nothing to produce). Used only for
# the deepest-stage-reached diagnostic, never for the terminal status itself --
# see derive_case_status()'s docstring for why those are different questions.
STAGE_TO_STATUS: dict[str, CaseStatus] = {
    "forcing": CaseStatus.INGESTED,
    "ais_ingest": CaseStatus.INGESTED,
    "netra_detection": CaseStatus.DETECTING,
    "phi_reconstruction": CaseStatus.RECONSTRUCTING,
    "attribution": CaseStatus.ATTRIBUTING,
    "validity": CaseStatus.VALIDATING,
    "forecast": CaseStatus.FORECASTING,
    "decision": CaseStatus.DECIDING,
    "mission": CaseStatus.MISSION,
    "alerts": CaseStatus.ALERTING,
}

# Stages whose own failure means "the observation layer had nothing to work
# with" (UNAVAILABLE) rather than "an integration break occurred downstream
# of good input" (BLOCKED). Both are named `StageStatus.BLOCKED` at the stage
# level -- this is the one place that distinguishes them at the CASE level,
# and it is a deliberate design decision, not a default: see
# docs section "BLOCKED vs UNAVAILABLE" in the golden case engine report.
INPUT_LAYER_STAGES: frozenset[str] = frozenset({"forcing", "ais_ingest"})


def deepest_stage_reached(run: Any) -> str | None:
    """The last stage in STAGE_ORDER this run actually recorded anything for.
    Diagnostic only -- never used to decide the terminal CaseStatus."""
    reached = None
    for name in STAGE_ORDER:
        if name in run.stages:
            reached = name
    return reached


def derive_case_status(run: Any) -> tuple[CaseStatus, str | None]:
    """The single place a `PipelineRun` becomes a terminal `CaseStatus`.

    Deliberately answers a *different* question from `StageStatus`: whether
    the CASE, as a whole, finished its intended traversal. A stage reporting
    `NOT_YET_PRODUCED` because a restrictive gate correctly withheld tasking
    is NOT a case failure -- `RealE2EPipeline` already treats that as the
    fail-closed contract working (see its own module docstring), and this
    function inherits that judgment rather than re-litigating it. COMPLETE
    therefore means "the run reached the end of the chain without breaking",
    not "every stage found a positive result" -- an operator reads *what* was
    found from the per-section status/evidence_mode in the OperatorCase view,
    not from case.status.

    BLOCKED vs UNAVAILABLE: both stem from `StageStatus.BLOCKED` somewhere in
    the run, but they answer different questions. If the very first stage
    that broke is `forcing` or `ais_ingest` (the observation-ingestion layer),
    the case never had usable input -- that is UNAVAILABLE, a data-availability
    fact, not a system defect. Anything blocked further downstream, on
    otherwise-good input, is a genuine integration break -- BLOCKED.
    """
    blocked_at = run.blocked_at
    if blocked_at is not None:
        r = run.stages[blocked_at]
        if blocked_at in INPUT_LAYER_STAGES:
            return CaseStatus.UNAVAILABLE, f"{blocked_at}: {r.reason}"
        return CaseStatus.BLOCKED, f"{blocked_at}: {r.reason}"

    # A producer may flag, in its own StageResult.detail, that the input was
    # recognisably outside its trained distribution (`detail["ood"] = True`).
    # No stage in the current NETRA boundary sets this today -- the MC20 null
    # result is documented as "detection unavailable", explicitly NOT a proven
    # OOD finding (see docs/e2e/MC20_REAL_E2E_INTEGRATION.md) -- so a real run
    # will not land here until a detector genuinely knows it is out of domain.
    # This is only exercised today by the CASE-OOD replay fixture.
    for name in STAGE_ORDER:
        r = run.stages.get(name)
        if r is not None and r.detail.get("ood") is True:
            return CaseStatus.OOD, r.reason

    forcing = run.stages.get("forcing")
    ais = run.stages.get("ais_ingest")
    forcing_ok = forcing is not None and forcing.produced
    ais_ok = ais is not None and ais.produced
    if not forcing_ok and not ais_ok:
        return CaseStatus.UNAVAILABLE, "no usable observation: forcing and AIS both unavailable"

    if run.finished_at is not None:
        return CaseStatus.COMPLETE, None

    # The run object was handed to us mid-flight (should not happen through
    # `GoldenCaseWorkflow.run_case()`, which always waits for finished_at, but
    # kept honest rather than assumed).
    stage = deepest_stage_reached(run)
    if stage is None:
        return CaseStatus.CASE_CREATED, "no stage has run yet"
    return STAGE_TO_STATUS[stage], "run has not finished"


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def code_version() -> str:
    """The exact git commit this run executed at. `"unknown"` (never a crash)
    outside a git checkout -- reproducibility metadata degrading gracefully
    is preferable to a run failing because it could not describe itself."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def config_hash(config: Any) -> str:
    """Stable hash of everything about a run that could change its scientific
    output. This is deliberately over `to_dict()`'s config block (already
    proven to serialize every tunable in `PipelineConfig`), not over the whole
    object graph -- gold_dir is a path, not a science parameter, but IS
    included because a different Gold version is a different input."""
    payload = {
        "gold_dir": str(getattr(config, "gold_dir", "")),
        "n_particles": config.n_particles,
        "n_ensemble": config.n_ensemble,
        "backward_duration_hours": config.backward_duration_hours,
        "forecast_horizon_hours": config.forecast_horizon_hours,
        "seed": config.seed,
        "age_prior_mean_hours": config.age_prior_mean_hours,
        "age_prior_std_hours": config.age_prior_std_hours,
        "latent_prior": config.latent_prior,
        "corridor_width_km": config.corridor_width_km,
        "max_ais_tracks": config.max_ais_tracks,
        "ais_status": getattr(config.ais_status, "value", str(config.ais_status)),
        "max_netra_tiles": config.max_netra_tiles,
        "run_class": config.run_class,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True)
class ReproducibilityRecord:
    """Everything needed to reproduce or audit one run, independent of any
    one contract object -- this is deliberately NOT folded into
    `EvidenceEnvelope` (a locked, per-artifact contract); it describes the
    RUN, not a single artifact."""

    case_id: str
    run_id: str
    engine_mode: str
    model_id: str | None
    model_version: str | None
    checkpoint_hash: str | None
    preprocessing_version: str | None
    dataset_version: str | None
    config_hash: str
    code_version: str
    evidence_mode: str | None
    started_at: str
    finished_at: str | None
    deepest_stage_reached: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id, "run_id": self.run_id, "engine_mode": self.engine_mode,
            "model_id": self.model_id, "model_version": self.model_version,
            "checkpoint_hash": self.checkpoint_hash,
            "preprocessing_version": self.preprocessing_version,
            "dataset_version": self.dataset_version, "config_hash": self.config_hash,
            "code_version": self.code_version, "evidence_mode": self.evidence_mode,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "deepest_stage_reached": self.deepest_stage_reached,
        }


# The Gold v0.2 normalization contract every real NETRA detection in this
# pipeline is preprocessed under (see docs/datasets/MC20_EVENT_GOLD_V0_1.md,
# "SAR preprocessing"). `netra_boundary.py` assumes this but does not version
# or assert it on the provider itself -- flagged as a real, open gap by the
# session that built that boundary (see the report). Recorded here as the one
# value the golden engine actually knows, not silently invented as if it were
# tracked upstream.
ASSUMED_NETRA_PREPROCESSING_VERSION = "netra-norm-v0.2-nodata-excluded"


def detector_provider_info(run: Any) -> dict[str, Any]:
    """Read the DetectorProvider identity off whatever the detection stage
    actually recorded -- model_id, model_version, checkpoint_hash,
    preprocessing_version, detection state, evidence mode, provenance. Every
    field the boundary itself carries is read verbatim; `preprocessing_version`
    is the one field `NetraDetectionBoundary` does not track today (see
    module docstring) and is reported as an ASSUMED constant, explicitly
    labelled, rather than presented as if it were measured."""
    det = run.stages.get("netra_detection")
    if det is None:
        return {
            "model_id": None, "model_version": None, "checkpoint_hash": None,
            "preprocessing_version": None, "detection_state": None,
            "evidence_mode": None, "provenance_notes": None,
        }
    model_version = det.detail.get("model_version")
    checkpoint_hash = None
    notes = det.detail.get("notes")
    if isinstance(notes, str) and "sha256=" in notes:
        checkpoint_hash = notes.split("sha256=", 1)[1].split(";", 1)[0].strip()
    return {
        "model_id": model_version.split("-")[0] if model_version else None,
        "model_version": model_version,
        "checkpoint_hash": checkpoint_hash,
        "preprocessing_version": (
            ASSUMED_NETRA_PREPROCESSING_VERSION if model_version else None
        ),
        "detection_state": det.status.value,
        "evidence_mode": det.evidence_mode.value if det.evidence_mode else None,
        "provenance_notes": (
            f"scientific_status={det.detail.get('scientific_status')}"
            if det.detail.get("scientific_status") else None
        ),
    }


# ---------------------------------------------------------------------------
# CaseResult -- the canonical output, serializable into OperatorCase v1
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """What one call to `run_case()` produces. Everything an OperatorCase v1
    needs is reachable from here: `case` + `workflow` is exactly the
    signature `apps.api.operator_case_view.build_operator_case()` already
    takes, so `.to_operator_case()` calls it unmodified rather than
    reimplementing the projection."""

    case: Case
    run: Any                      # varuna_integration.pipeline.PipelineRun
    reproducibility: ReproducibilityRecord
    idempotent_replay: bool       # True if this result was reused, not freshly run

    def to_operator_case(self, workflow: "GoldenCaseWorkflow"):
        from apps.api.operator_case_view import build_operator_case

        return build_operator_case(self.case, workflow)


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


class GoldenCaseWorkflow:
    """ONE canonical case runner. `mode` selects REAL / REPLAY / SIMULATED at
    the single entry point `run_case()` -- there is no second pipeline class
    for "demo mode"."""

    def __init__(self, case_repo: CaseRepository, artifact_repo: ArtifactRepository,
                 event_repo: EventRepository, *, object_store: Optional[ObjectStore] = None,
                 mission_service: Any = None, alert_service: Any = None,
                 netra: Any = None):
        self.cases = case_repo
        self.artifacts = artifact_repo
        self.events_store = event_repo
        self.praman = PramanService(self.artifacts, object_store)
        self.event_spine = EventSpine(self.events_store)
        self.mission_service = mission_service
        self.alert_service = alert_service
        self.netra = netra

    # -------------------------------------------------------------- create

    def create_case(self, case_id: str | None = None) -> Case:
        case_id = case_id or f"CASE-{uuid.uuid4().hex[:8].upper()}"
        case = Case(case_id)
        case.transition(CaseStatus.CASE_CREATED, "golden_case_engine")
        self.cases.save(case)
        self.event_spine.emit("case.created", case_id, actor="golden_case_engine")
        return case

    # ----------------------------------------------------------- run_case

    def run_case(self, case_id: str, *, gold_dir: Path, mode: str = EngineMode.REAL,
                 pipeline_config: Any = None, allow_simulated: bool = False,
                 force: bool = False) -> CaseResult:
        """The single entry point for REAL and SIMULATED runs. `mode` is
        recorded, not branched on: what differs between them is only which
        `NetraDetectionBoundary`/config the caller constructed, exactly as
        `resolve_netra_boundary()` already requires `allow_simulated` to be
        explicit in code (never in config), so a demo cannot silently become
        a real run and vice versa. See `run_replay_case()` for the REPLAY
        variant, which sources a canned `PipelineRun` instead of invoking
        `RealE2EPipeline` -- same idempotency, lifecycle and reproducibility
        machinery either way, via `_finalize()`.

        Idempotent: a second call with the same case_id and an
        equal-by-content `pipeline_config` reuses the prior run's CaseResult
        (including its missions/alerts) instead of re-executing the pipeline,
        unless `force=True`.
        """
        from varuna_integration.pipeline import PipelineConfig, RealE2EPipeline

        case = self.cases.get(case_id) or self.create_case(case_id)
        cfg = pipeline_config or PipelineConfig(gold_dir=gold_dir)
        cfg_hash = config_hash(cfg)

        cached = self._cached_result(case, cfg_hash, force)
        if cached is not None:
            return cached

        pipeline = RealE2EPipeline(
            cfg, netra=self.netra, mission_service=self.mission_service,
            alert_service=self.alert_service,
        )
        try:
            run = pipeline.run(case_id)
        except Exception as exc:  # a crash IN the engine itself, not a stage
            case.transition(CaseStatus.FAILED, "golden_case_engine")
            case.error = f"{type(exc).__name__}: {exc}"
            self.cases.save(case)
            self.event_spine.emit("case.failed", case_id, payload={"reason": case.error})
            raise

        return self._finalize(case, run, mode, cfg_hash, dataset_version=_dataset_version(gold_dir))

    # ----------------------------------------------------- run_replay_case

    def run_replay_case(self, case_id: str, fixture_name: str, *, force: bool = False) -> CaseResult:
        """The REPLAY variant of `run_case()`. Sources a fully-built,
        deterministic `PipelineRun` from `varuna_domain.replay_fixtures`
        (no network, no filesystem, no GPU) instead of invoking
        `RealE2EPipeline`, then runs through the exact same idempotency,
        lifecycle-transition and reproducibility path as a real run via
        `_finalize()` -- this is the "no separate demo pipeline" guarantee:
        REPLAY differs only in where the `PipelineRun` came from, not in how
        the case engine treats it afterward."""
        from varuna_domain.replay_fixtures import build_replay_run

        case = self.cases.get(case_id) or self.create_case(case_id)
        cfg_hash = f"replay:{fixture_name}"

        cached = self._cached_result(case, cfg_hash, force)
        if cached is not None:
            return cached

        run = build_replay_run(fixture_name, case_id=case_id)
        return self._finalize(case, run, EngineMode.REPLAY, cfg_hash, dataset_version=None)

    # ----------------------------------------------------------- internals

    def _cached_result(self, case: Case, cfg_hash: str, force: bool) -> CaseResult | None:
        if force:
            return None
        runs_index: dict[str, Any] = case.metadata.setdefault("golden_engine_runs", {})
        cached = runs_index.get(cfg_hash)
        if cached is None:
            return None
        repro = ReproducibilityRecord(**cached["reproducibility"])
        # A cached CaseResult carries the persisted repro record and the
        # case's current (already-transitioned) status; it deliberately does
        # NOT reconstruct a live `PipelineRun` object (that would be
        # re-running the pipeline, defeating the point of idempotency).
        return CaseResult(case=case, run=_ReplayedRunView(cached), reproducibility=repro,
                          idempotent_replay=True)

    def _finalize(self, case: Case, run: Any, mode: str, cfg_hash: str,
                  *, dataset_version: str | None) -> CaseResult:
        self._apply_run(case, run, mode)

        info = detector_provider_info(run)
        repro = ReproducibilityRecord(
            case_id=case.case_id, run_id=run.run_id, engine_mode=mode,
            model_id=info["model_id"], model_version=info["model_version"],
            checkpoint_hash=info["checkpoint_hash"],
            preprocessing_version=info["preprocessing_version"],
            dataset_version=dataset_version,
            config_hash=cfg_hash, code_version=code_version(),
            evidence_mode=run.evidence_mode.value if run.evidence_mode else None,
            started_at=run.started_at.isoformat(),
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            deepest_stage_reached=deepest_stage_reached(run),
        )
        runs_index: dict[str, Any] = case.metadata.setdefault("golden_engine_runs", {})
        runs_index[cfg_hash] = {
            "reproducibility": repro.to_dict(),
            "case_status": case.status.value,
        }
        self.cases.save(case)
        return CaseResult(case=case, run=run, reproducibility=repro, idempotent_replay=False)

    def _apply_run(self, case: Case, run: Any, mode: str) -> None:
        """Bridge the PipelineRun onto Case.metadata (reused, unmodified) and
        walk the explicit CaseStatus lifecycle to its terminal state."""
        from varuna_integration.case_bridge import apply_run_to_case

        apply_run_to_case(case, run)

        for name in STAGE_ORDER:
            r = run.stages.get(name)
            if r is None:
                continue
            status = STAGE_TO_STATUS[name]
            case.transition(status, f"golden_case_engine:{name}")
            self.event_spine.emit(f"case.stage.{name}", case.case_id, payload={
                "stage_status": r.status.value,
                "evidence_mode": r.evidence_mode.value if r.evidence_mode else None,
            })

        terminal, reason = derive_case_status(run)
        case.transition(terminal, "golden_case_engine")
        if terminal in (CaseStatus.BLOCKED, CaseStatus.UNAVAILABLE, CaseStatus.OOD):
            case.error = reason
        self.event_spine.emit("case.terminal", case.case_id, payload={
            "status": terminal.value, "reason": reason, "mode": mode,
        })

        artifact = self.praman.register_artifact(
            artifact_type="golden_case_run", case_id=case.case_id,
            produced_by="golden_case_engine", data={
                "run_id": run.run_id, "terminal_status": terminal.value,
                "blocked_at": run.blocked_at,
                "evidence_mode": run.evidence_mode.value if run.evidence_mode else None,
            },
        )
        case.metadata["golden_case_run_artifact_id"] = artifact.artifact_id
        case.scientific_status = ScientificStatus.EXPERIMENTAL


def _dataset_version(gold_dir: Path) -> str | None:
    manifest_path = Path(gold_dir) / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return manifest.get("dataset_version")


@dataclass
class _ReplayedRunView:
    """Minimal stand-in returned for an idempotent (cached) `run_case()` call.
    Carries only what the cached reproducibility record already had -- it is
    NOT a `PipelineRun` and does not pretend to re-expose `.stages`; callers
    that need the full stage detail of the ORIGINAL run should read
    `case.metadata` (already written by `apply_run_to_case()` on the first,
    non-idempotent call and never overwritten by a cached replay)."""

    cached: dict[str, Any]

    @property
    def run_id(self) -> str:
        return self.cached["reproducibility"]["run_id"]
