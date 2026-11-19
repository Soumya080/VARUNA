"""
VARUNA GRID v2 - Track 4 real E2E backend integration run.

Drives one MC20 case through every wired producer and emits the OperatorCase v1
projection the API serves:

    MC20 Event Gold -> NETRA -> PRATIVARTAN -> Phi -> AIS -> NYAYA -> Validity
                    -> PRAVAAH -> ABHIYAN -> Mission FSM -> Alerts -> OperatorCase

Run (from the repo root):

    PYTHONPATH=packages .venv/Scripts/python.exe scripts/mc20_track4_e2e.py

Options:

    --gold DIR         event Gold directory (default data/gold/events/mc20_v0_1)
    --allow-simulated  permit an explicitly-labelled simulated slick placeholder
                       when no frozen NETRA checkpoint exists. Without this the
                       run honestly reports detection=NOT_YET_PRODUCED and every
                       downstream stage says why. It NEVER makes output REAL.
    --checkpoint PATH  NETRA checkpoint to use if it has been frozen
    --particles / --ensemble
                       reconstruction scale. The defaults are deliberately tiny
                       and stamp the run INTEGRATION_SMOKE.
    --scientific       assert this run is at a scientific scale. Refuses to run
                       below a real ensemble size rather than mislabel a toy run.
    --out DIR          where to write run + operator-case JSON (default reports/)

Read-only with respect to all data: nothing under data/raw, data/bronze or
data/gold is written, moved, renamed or deleted. Only the two report files under
--out are created.
"""
from __future__ import annotations

# Schema imports before anything that may pull in netCDF4 (Windows DLL issue).
from varuna_contracts.evidence import EvidenceMode  # isort: skip

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MIN_SCIENTIFIC_PARTICLES = 500
MIN_SCIENTIFIC_ENSEMBLE = 20


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", type=Path, default=REPO_ROOT / "data/gold/events/mc20_v0_1")
    ap.add_argument("--allow-simulated", action="store_true")
    ap.add_argument("--checkpoint", type=Path,
                    default=REPO_ROOT / "artifacts/checkpoints/netra_v0_2"
                                        "/netra_baseline_v02_dac482fcd84a_best.pt")
    ap.add_argument("--model-version", default="netra-v0.2-baseline")
    ap.add_argument("--particles", type=int, default=20)
    ap.add_argument("--ensemble", type=int, default=4)
    ap.add_argument("--horizon-hours", type=float, default=24.0)
    ap.add_argument("--max-ais-tracks", type=int, default=5)
    ap.add_argument("--scientific", action="store_true")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "reports")
    args = ap.parse_args()

    from varuna_alerts.channels.console import ConsoleChannel
    from varuna_alerts.service import AlertService
    from varuna_contracts.schemas import BBox, GeoPoint
    from varuna_integration.netra_boundary import (
        NetraModelSpec, SimulatedSlickProvider, resolve_netra_boundary,
    )
    from varuna_integration.pipeline import PipelineConfig, RealE2EPipeline
    from varuna_missions.repository import InMemoryMissionRepository
    from varuna_missions.service import MissionService

    if not (args.gold / "manifest.json").exists():
        print(f"[FATAL] no event manifest at {args.gold / 'manifest.json'}")
        return 2

    run_class = "INTEGRATION_SMOKE"
    if args.scientific:
        if args.particles < MIN_SCIENTIFIC_PARTICLES or args.ensemble < MIN_SCIENTIFIC_ENSEMBLE:
            print(f"[FATAL] --scientific requires at least "
                  f"{MIN_SCIENTIFIC_PARTICLES} particles and "
                  f"{MIN_SCIENTIFIC_ENSEMBLE} ensemble members; got "
                  f"{args.particles}/{args.ensemble}. Refusing to label a toy run "
                  f"as a scientific result.")
            return 2
        run_class = "SCIENTIFIC"

    manifest = json.loads((args.gold / "manifest.json").read_text(encoding="utf-8"))

    # ---- NETRA boundary: real if frozen, otherwise honestly absent ----
    spec = NetraModelSpec(checkpoint_path=args.checkpoint, model_version=args.model_version)
    sim_provider = None
    if args.allow_simulated:
        bb = manifest["modalities"]["sar"]["bbox"]
        clon = (bb["min_lon"] + bb["max_lon"]) / 2
        clat = (bb["min_lat"] + bb["max_lat"]) / 2
        sim_provider = SimulatedSlickProvider(
            centroid=GeoPoint(lon=clon, lat=clat),
            bbox=BBox(min_lon=clon - 0.05, min_lat=clat - 0.05,
                      max_lon=clon + 0.05, max_lat=clat + 0.05),
            scene_id=manifest["event_id"],
        )
    netra, netra_reason = resolve_netra_boundary(
        spec, allow_simulated=args.allow_simulated, simulated_provider=sim_provider)
    print(f"[NETRA] {netra_reason}")

    pipeline = RealE2EPipeline(
        PipelineConfig(
            gold_dir=args.gold, n_particles=args.particles, n_ensemble=args.ensemble,
            forecast_horizon_hours=args.horizon_hours,
            max_ais_tracks=args.max_ais_tracks, run_class=run_class,
        ),
        netra=netra,
        mission_service=MissionService(InMemoryMissionRepository()),
        alert_service=AlertService([ConsoleChannel()]),
    )
    run = pipeline.run()

    # ---- project onto a Case and build the OperatorCase the API serves ----
    operator_case, projection_error = _build_operator_case(run)

    args.out.mkdir(parents=True, exist_ok=True)
    run_path = args.out / "mc20_track4_e2e_run.json"
    run_path.write_text(json.dumps(run.to_dict(), indent=2, default=str), encoding="utf-8")
    oc_path = None
    if operator_case is not None:
        oc_path = args.out / "mc20_track4_operator_case.json"
        oc_path.write_text(operator_case.model_dump_json(indent=2), encoding="utf-8")

    _print_report(run, operator_case, projection_error, netra_reason)
    print(f"\nwrote {_display(run_path)}")
    if oc_path:
        print(f"wrote {_display(oc_path)}")

    # Exit 0 whenever the pipeline completed honestly. A RESTRICTED gate or a
    # NOT_YET_PRODUCED stage is a valid scientific outcome, not a run failure.
    # Only a genuine integration break (a BLOCKED stage) is non-zero.
    return 1 if run.blocked_at else 0


def _display(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise. `--out` may point
    anywhere, including outside the repo, so `relative_to()` must not be
    assumed to succeed."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _build_operator_case(run):
    """Case -> OperatorCase, exactly as GET /v1/cases/{id}/operator-view does."""
    try:
        from apps.api.operator_case_view import build_operator_case
        from varuna_domain.case_workflow import CaseWorkflow
        from varuna_domain.entities import Case
        from varuna_domain.repositories import (
            InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
        )
        from varuna_integration.case_bridge import apply_run_to_case

        workflow = CaseWorkflow(
            InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore())
        case = Case(run.case_id)
        apply_run_to_case(case, run)
        workflow.cases.save(case)
        return build_operator_case(case, workflow), None
    except Exception as exc:  # noqa: BLE001 - reported, never hidden
        import traceback
        return None, f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"


def _print_report(run, operator_case, projection_error, netra_reason) -> None:
    print("\n" + "=" * 78)
    print(f"RUN {run.run_id}")
    print(f"case={run.case_id}  class={run.config.run_class}  "
          f"scientific={run.config.is_scientific}")
    print(f"total={run.total_seconds:.2f}s  "
          f"evidence_mode={run.evidence_mode.value if run.evidence_mode else None}  "
          f"blocked_at={run.blocked_at}")
    print("=" * 78)
    print(f"{'STAGE':<20} {'STATUS':<18} {'MODE':<11} {'TIME':>8}")
    print("-" * 78)
    for name, s in run.stages.items():
        t = f"{s.runtime_seconds:.2f}s" if s.runtime_seconds is not None else "-"
        mode = s.evidence_mode.value if s.evidence_mode else "-"
        print(f"{name:<20} {s.status.value:<18} {mode:<11} {t:>8}")
        if s.reason:
            print(f"{'':>21}why: {s.reason[:120]}")
    print("-" * 78)

    if projection_error:
        print(f"\n[OperatorCase] PROJECTION FAILED: {projection_error}")
        return
    if operator_case is None:
        return
    print("\nOperatorCase v1 sections (what GET /v1/cases/{id}/operator-view returns):")
    for field in ("observation", "detection", "origin", "ais", "attribution",
                  "validity", "forecast", "decision", "mission", "alerts"):
        sec = getattr(operator_case, field)
        mode = sec.evidence_mode.value if sec.evidence_mode else "-"
        print(f"  {field:<13} {sec.status.value:<18} mode={mode}")
        if sec.value is None and sec.reason:
            print(f"                why: {sec.reason[:110]}")


if __name__ == "__main__":
    raise SystemExit(main())
