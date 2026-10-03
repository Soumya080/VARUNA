"""
VARUNA GRID v2 — STEP 2: Populated Canonical Replay demo artifact builder.

Executes CASE-VALID through `GoldenCaseWorkflow.run_replay_case()` (the ONLY
orchestration call this script makes — it never directly constructs
`RealE2EPipeline` or the legacy `varuna_domain.case_workflow` orchestrator),
then derives two views from the SAME `CaseResult`:

    CaseResult.to_operator_case(workflow)   -> OperatorCase (canonical contract)
    CaseIntelligenceService.run(result.run) -> CaseIntelligence (CHHAYA/SMRITI/uncertainty)

and writes both, merged, to reports/demo/canonical_populated_replay.json.

Read-only with respect to all frozen data: writes only the one report file.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(REPO_ROOT))

from varuna_alerts.channels.mock_sms import MockSmsChannel  # noqa: E402
from varuna_alerts.service import AlertService  # noqa: E402
from varuna_domain.golden_case_engine import GoldenCaseWorkflow  # noqa: E402
from varuna_domain.repositories import (  # noqa: E402
    InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
)
from varuna_infra.inmemory_store import InMemoryObjectStore  # noqa: E402
from varuna_infra.observability import build_case_timeline  # noqa: E402
from varuna_integration.intelligence import CaseIntelligenceService  # noqa: E402
from varuna_missions.repository import InMemoryMissionRepository  # noqa: E402
from varuna_missions.service import MissionService  # noqa: E402
from varuna_smriti.memory import CaseMemory, SmritiStore  # noqa: E402

CASE_ID = "CASE-VALID-CANONICAL-REPLAY-DEMO"
FIXTURE_NAME = "CASE-VALID"
MEMORY_PATH = REPO_ROOT / "reports" / "demo" / "canonical_replay_smriti_memory.jsonl"
OUT_PATH = REPO_ROOT / "reports" / "demo" / "canonical_populated_replay.json"


def _seed_memory(store: SmritiStore) -> None:
    """Same seed data and rationale as scripts/varuna_demo.py::_seed_memory —
    explicitly SYNTHETIC historical records, labelled as such in their own
    provenance field, reused rather than re-invented for consistency across
    this repository's demos."""
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


def main() -> int:
    workflow = GoldenCaseWorkflow(
        InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
        object_store=InMemoryObjectStore(),
        mission_service=MissionService(InMemoryMissionRepository()),
        alert_service=AlertService([MockSmsChannel()]),
    )

    result = workflow.run_replay_case(CASE_ID, FIXTURE_NAME)
    operator_case = result.to_operator_case(workflow)

    store = SmritiStore(MEMORY_PATH)
    _seed_memory(store)
    intel = CaseIntelligenceService(smriti=store).run(result.run)

    praman_artifact_id = result.case.metadata.get("golden_case_run_artifact_id")
    praman_verified = (workflow.praman.verify(praman_artifact_id)
                       if praman_artifact_id else False)
    praman_artifact = workflow.artifacts.get(praman_artifact_id) if praman_artifact_id else None

    timeline = build_case_timeline(result.run)

    payload = {
        "demo": "CANONICAL_POPULATED_REPLAY",
        "fixture_id": FIXTURE_NAME,
        "case_id": CASE_ID,
        "run_id": result.reproducibility.run_id,
        "deterministic_run_id": result.reproducibility.deterministic_run_id,
        "engine_mode": result.reproducibility.engine_mode,
        "case_status": result.case.status.value,
        "executed_via": "GoldenCaseWorkflow.run_replay_case() only",
        "stage_timeline": timeline,
        "operator_case": json.loads(operator_case.model_dump_json()),
        "intelligence": intel.to_dict(),
        "praman": {
            "artifact_id": praman_artifact_id,
            "content_hash": praman_artifact.content_hash if praman_artifact else None,
            "verified": praman_verified,
        },
        "smriti": {
            "store_case_count": len(store.all_cases()),
            "memory_hits_for_this_case": intel.memory_hits,
        },
        "limitations": [
            "CASE-VALID is a hand-built replay fixture (see "
            "packages/varuna_domain/replay_fixtures.py::_build_valid); every "
            "value is SYNTHETIC, not measured. engine_mode='replay' records "
            "this; evidence_mode='real' on each section records what the "
            "fixture MODELS (a successful real run), not that this execution "
            "was live. Both facts are surfaced, never collapsed into one.",
            "ais section is legitimately NOT_YET_PRODUCED: the ais_ingest "
            "STAGE executed successfully (n_returned=0), but zero tracks "
            "means zero AIS evidence, not a failure.",
            "provenance.manifest_artifact_id is None: GoldenCaseWorkflow "
            "registers one summary PRAMAN artifact per run "
            "(artifact_type='golden_case_run'), not a full EvidenceManifest. "
            "See docs/product/CANONICAL_REPLAY_GAPS.md.",
            "CHHAYA/SMRITI/uncertainty content here comes from a SEPARATE "
            "read-only pass (CaseIntelligenceService.run(result.run)) over "
            "the same PipelineRun GoldenCaseWorkflow produced -- "
            "GoldenCaseWorkflow does not invoke this layer internally, and "
            "OperatorCase (the canonical contract) has no fields for its "
            "output. See docs/product/CANONICAL_REPLAY_GAPS.md.",
        ],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  case_status: {result.case.status.value}")
    print(f"  engine_mode: {result.reproducibility.engine_mode}")
    print(f"  operator_case.recommendation: {operator_case.recommendation.value}")
    print(f"  intelligence.terminal_action: {intel.trace.terminal_action.value if intel.trace.terminal_action else None}")
    print(f"  praman.verified: {praman_verified}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
