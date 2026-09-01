"""
VARUNA GRID — end-to-end product demonstrations.

    DEMO A (real)    : the actual MC20 case through the canonical pipeline.
    DEMO B (replay)  : a populated case exercising the whole chain.

Run:
    PYTHONPATH=packages python scripts/varuna_demo.py            # both
    PYTHONPATH=packages python scripts/varuna_demo.py --demo a   # one

DEMO A does NOT force a positive result. The current frozen NETRA v0.2
checkpoint finds nothing on MC20, and the point of that demo is that the whole
downstream chain handles a real null safely instead of inventing a spill.

Neither demo starts training, touches a checkpoint, or writes to any frozen
asset. Both write only to reports/demo/.
"""
from __future__ import annotations

# Schema imports before netCDF4 (Windows DLL interaction — see forcing.py).
from varuna_contracts.evidence import EvidenceMode  # isort: skip

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"
OUT_DIR = REPO_ROOT / "reports" / "demo"
MEMORY_PATH = OUT_DIR / "smriti_memory.jsonl"


def _hr(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def _seed_memory(store) -> None:
    """
    Seed SMRITI with prior cases so retrieval has something to find.

    These are explicitly SYNTHETIC historical records, labelled as such in
    their own provenance field. They are demonstration context for the memory
    subsystem, NOT real historical VARUNA cases, and nothing downstream may
    treat them as evidence about the real world.
    """
    from varuna_smriti.memory import CaseMemory
    if store.all_cases():
        return
    for i, (lon, lat, cls, outcome, tags) in enumerate([
        (-89.72, 28.94, "natural_seep", "unresolved", ["ood_detection"]),
        (-89.65, 29.05, "natural_seep", "confirmed", []),
        (-89.80, 28.88, "vessel_associated", "not_found", ["weak_ais_match"]),
    ]):
        store.store_case(CaseMemory(
            case_id=f"SYNTHETIC-HIST-{i+1}",
            centroid_lon=lon, centroid_lat=lat,
            wind_speed_ms=4.0 + i, area_km2=8.0 + i, elongation=1.5 + i * 0.5,
            observed_at=datetime(2022, 6, 1 + i, tzinfo=timezone.utc),
            top_source_class=cls, outcome=outcome, failure_tags=tags,
            provenance_source="SYNTHETIC-DEMO-SEED (not a real historical case)",
        ))


def _report(name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _print_intelligence(intel) -> None:
    print(f"\n  Evidence ledger: {len(intel.ledger.for_case(intel.case_id))} active item(s)")
    for item in intel.ledger.for_case(intel.case_id):
        conf = f" conf={item.confidence:.2f}" if item.confidence is not None else ""
        print(f"    - [{item.kind.value:18s}] {item.mode.value:10s}{conf}  {item.summary}")

    contradictions = intel.ledger.contradictions(intel.case_id)
    print(f"  Contradictions: {len(contradictions)}")
    for c in contradictions:
        print(f"    ! {c.left_summary}  <>  {c.right_summary}")

    u = intel.uncertainty
    print("\n  Uncertainty (component-level, never a single score):")
    print(f"    dominant concern : {u.dominant_concern}")
    print(f"    ood risk         : {u.ood_risk.value}")
    print(f"    conflicts        : {u.evidence_conflict_count}")
    for k, v in u.component_notes.items():
        print(f"    note[{k}]: {v}")

    if intel.detection_evidence is not None:
        d = intel.detection_evidence
        print("\n  DetectionEvidenceEnvelope:")
        print(f"    model            : {d.model_id} {d.model_version}")
        print(f"    tiles            : {d.n_tiles}")
        print(f"    has_detection    : {d.has_detection}")
        print(f"    ood_risk         : {d.ood_risk.value}")
        print(f"    rationale        : {(d.ood_rationale or '')[:100]}")
        for lim in d.limitations:
            print(f"    limitation       : {lim[:100]}")

    if intel.hypotheses is not None:
        h = intel.hypotheses
        print("\n  CHHAYA source hypotheses:")
        for hyp in h.hypotheses[:3]:
            print(f"    {hyp.source_class.value:22s} {hyp.posterior:.3f}")
        print(f"    method           : {h.method.value}")
        print(f"    insufficient     : {h.insufficient_evidence}")

    if intel.memory_hits:
        print("\n  SMRITI (advisory only):")
        for hit in intel.memory_hits:
            print(f"    {hit['case_id']:22s} score={hit['score']:.3f} "
                  f"outcome={hit['outcome']}")

    print(f"\n  Agentic loop: {intel.trace.iterations} iteration(s)")
    print(f"    TERMINAL: {intel.trace.terminal_action.value}")
    print(f"    reason  : {intel.trace.terminal_reason}")


# --------------------------------------------------------------------- DEMO A

def demo_a_real_mc20() -> dict:
    _hr("DEMO A — REAL MC20  (EvidenceMode: REAL inputs, real frozen checkpoint)")

    if not (GOLD / "manifest.json").exists():
        print("  SKIPPED: MC20 Event Gold corpus is not present in this checkout.")
        return {"demo": "A", "status": "skipped", "reason": "MC20 Gold absent"}

    from varuna_alerts.service import AlertService
    from varuna_integration.intelligence import CaseIntelligenceService
    from varuna_integration.netra_boundary import (
        NetraModelSpec, resolve_netra_boundary,
    )
    from varuna_integration.pipeline import PipelineConfig, RealE2EPipeline
    from varuna_missions.repository import InMemoryMissionRepository
    from varuna_missions.service import MissionService
    from varuna_smriti.memory import SmritiStore

    # The REAL, frozen v0.2 checkpoint. `allow_simulated` is deliberately NOT
    # passed: if the frozen checkpoint is unavailable or fails hash
    # verification, this demo must report that rather than quietly substituting
    # a synthetic slick and calling the run "real".
    ckpt = (REPO_ROOT / "artifacts" / "checkpoints" / "netra_v0_2"
            / "netra_baseline_v02_dac482fcd84a_best.pt")
    spec = (NetraModelSpec(checkpoint_path=ckpt, model_version="netra-v0.2-baseline")
            if ckpt.exists() else None)
    boundary, netra_reason = resolve_netra_boundary(spec)
    print(f"  NETRA boundary: {netra_reason}")

    cfg = PipelineConfig(gold_dir=GOLD, n_particles=20, n_ensemble=4,
                         max_ais_tracks=5, run_class="INTEGRATION_SMOKE")
    run = RealE2EPipeline(
        cfg, netra=boundary,
        mission_service=MissionService(InMemoryMissionRepository()),
        alert_service=AlertService([]),
    ).run(case_id="DEMO-A-MC20-REAL")

    print("\n  Canonical pipeline stages:")
    for name, stage in run.stages.items():
        mode = stage.evidence_mode.value if stage.evidence_mode else "-"
        print(f"    {name:20s} {stage.status.value:18s} mode={mode:11s}"
              f" {(stage.reason or '')[:60]}")

    store = SmritiStore(MEMORY_PATH)
    _seed_memory(store)
    intel = CaseIntelligenceService(smriti=store).run(run)
    _print_intelligence(intel)

    print("\n  HONESTY CHECK:")
    det = run.stages.get("netra_detection")
    if det is not None and det.status.value != "produced":
        print("    NETRA produced no detection on the real MC20 scene.")
        print("    This is the REAL, UNMODIFIED result. No slick was fabricated to")
        print("    make the demo look better, and every downstream stage reports")
        print("    an explicit reason rather than an empty success.")

    payload = {"demo": "A", "kind": "REAL", "status": "completed",
               "case_id": run.case_id, "run_id": run.run_id,
               "pipeline": run.to_dict(), "intelligence": intel.to_dict()}
    path = _report("demo_a_real_mc20", payload)
    print(f"\n  Report: {path.relative_to(REPO_ROOT)}")
    return payload


# --------------------------------------------------------------------- DEMO B

def demo_b_populated_replay() -> dict:
    _hr("DEMO B — POPULATED REPLAY  (EvidenceMode: REPLAY/SIMULATED, labelled)")

    from varuna_domain.replay_fixtures import build_replay_run
    from varuna_integration.intelligence import CaseIntelligenceService
    from varuna_infra.authorization import AuthorizationError, Principal
    from varuna_missions.repository import InMemoryMissionRepository
    from varuna_missions.service import MissionService
    from varuna_praman.praman import PramanService
    from varuna_domain.repositories import InMemoryArtifactRepository
    from varuna_smriti.memory import SmritiStore

    run = build_replay_run("CASE-VALID")
    print("\n  Replay pipeline stages:")
    for name, stage in run.stages.items():
        mode = stage.evidence_mode.value if stage.evidence_mode else "-"
        print(f"    {name:20s} {stage.status.value:18s} mode={mode}")

    store = SmritiStore(MEMORY_PATH)
    _seed_memory(store)
    intel = CaseIntelligenceService(smriti=store).run(run)
    _print_intelligence(intel)

    # ---- Mission authorization (RBAC actually enforced) ----
    print("\n  Mission authorization (RBAC enforced at the service layer):")
    missions = MissionService(InMemoryMissionRepository())
    mission = missions.create_mission(run.case_id, "asset-dornier-1", tasking=None)

    for principal, label in [
        (Principal(principal_id="analyst_7", role="analyst"), "analyst (should be DENIED)"),
        (Principal.system(), "system (should be DENIED — human approval required)"),
        (Principal(principal_id="officer_1", role="duty_officer"), "duty officer (should be ALLOWED)"),
    ]:
        try:
            m = missions.approve_and_assign(mission.mission_id,
                                            approved_by=principal.principal_id,
                                            principal=principal)
            print(f"    {label:52s} -> ALLOWED, state={m.state.value}")
        except AuthorizationError as exc:
            print(f"    {label:52s} -> DENIED ({exc.permission.value})")

    audit = missions.audit_log.for_subject(mission.mission_id)
    print(f"    audit entries: {len(audit)} "
          f"({sum(1 for e in audit if e.allowed)} allowed, "
          f"{sum(1 for e in audit if not e.allowed)} denied)")

    # ---- PRAMAN provenance record ----
    praman = PramanService(InMemoryArtifactRepository())
    artifact = praman.register_artifact(
        "case_intelligence", run.case_id, "varuna.demo", intel.to_dict())
    print("\n  PRAMAN:")
    print(f"    artifact_id  : {artifact.artifact_id}")
    print(f"    content_hash : {artifact.content_hash[:32]}...")
    print(f"    verifies     : {praman.verify(artifact.artifact_id)}")

    # ---- SMRITI: record this case for future retrieval ----
    from varuna_smriti.memory import CaseMemory
    centroid = intel.detection_evidence.centroid if intel.detection_evidence else None
    store.store_case(CaseMemory(
        case_id=run.case_id,
        centroid_lon=centroid.lon if centroid else None,
        centroid_lat=centroid.lat if centroid else None,
        top_source_class=(intel.hypotheses.top.source_class.value
                          if intel.hypotheses else None),
        validity_state=str(getattr(run.stages.get("validity"), "value", None)
                           and run.stages["validity"].value.state.value),
        evidence_mode=(intel.ledger.worst_mode(run.case_id).value
                       if intel.ledger.worst_mode(run.case_id) else None),
        provenance_source="varuna.demo_b_replay",
        run_id=run.run_id,
    ))
    print(f"\n  SMRITI: case persisted; store now holds {len(store.all_cases())} case(s)")

    payload = {"demo": "B", "kind": "REPLAY", "status": "completed",
               "case_id": run.case_id, "run_id": run.run_id,
               "pipeline": run.to_dict(), "intelligence": intel.to_dict(),
               "authorization_audit": [e.model_dump(mode="json") for e in audit],
               "praman": {"artifact_id": artifact.artifact_id,
                          "content_hash": artifact.content_hash,
                          "verified": praman.verify(artifact.artifact_id)}}
    path = _report("demo_b_populated_replay", payload)
    print(f"\n  Report: {path.relative_to(REPO_ROOT)}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", choices=["a", "b", "both"], default="both")
    args = ap.parse_args()

    results = []
    if args.demo in ("a", "both"):
        results.append(demo_a_real_mc20())
    if args.demo in ("b", "both"):
        results.append(demo_b_populated_replay())

    _hr("SUMMARY")
    for r in results:
        print(f"  DEMO {r['demo']} ({r.get('kind', '?')}): {r['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
