"""
VARUNA GRID — CASE-0001 Demo Script.

Runs the full end-to-end vertical slice locally.
No GPU, Docker, Postgres, Redis, or MinIO required.

Usage:
    PYTHONPATH=packages;.;tests python scripts/demo_case_0001.py
"""
import datetime as _dt
if not hasattr(_dt, "UTC"):
    _dt.UTC = _dt.timezone.utc
import enum as _enum
if not hasattr(_enum, "StrEnum"):
    class _StrEnum(str, _enum.Enum): pass
    _enum.StrEnum = _StrEnum

import sys
import time

from tests.fixtures.case_0001 import generate_case_0001
from varuna_domain.case_workflow import CaseWorkflow


def main():
    print("=" * 60)
    print("VARUNA GRID v2 — CASE-0001 End-to-End Demo")
    print("=" * 60)
    print()
    print("SCIENTIFIC STATUS: EXPERIMENTAL (M2.2 validation deferred)")
    print()

    fixture = generate_case_0001()
    workflow = CaseWorkflow()

    t0 = time.time()
    result = workflow.run_full(
        case_id="CASE-0001",
        slick_lons=fixture["slick_lons"],
        slick_lats=fixture["slick_lats"],
        tracks=fixture["tracks"],
        obs_time_hours=fixture["obs_time_hours"],
        seed=fixture["seed"],
        latent_prior=fixture["config"]["latent_prior"],
        age_prior_mean=fixture["config"]["age_prior_mean"],
        age_prior_std=fixture["config"]["age_prior_std"],
    )
    runtime = time.time() - t0

    print(f"  Case ID:             {result['case_id']}")
    print(f"  Status:              {result['status']}")
    print(f"  Scientific Status:   {result['scientific_status']}")
    print(f"  Data Guard:          {result.get('guard_verdict', 'N/A')}")
    print(f"  Phi ID:              {result.get('phi_id', 'N/A')}")
    print(f"  Decision:            {result['decision']}")
    print(f"  Latent Prob:         {result['latent_probability']:.4f}")
    print(f"  Gate State:          {result['gate_state']}")
    print(f"  Allows Action:       {result['allows_action']}")
    print(f"  Artifacts:           {result['n_artifacts']}")
    print(f"  Events:              {result['n_events']}")
    print(f"  Runtime:             {runtime:.2f}s")
    print()

    # Print event log
    events = workflow.event_spine.list_by_case("CASE-0001")
    print("Event Log:")
    for e in events:
        print(f"  [{e.timestamp.strftime('%H:%M:%S')}] {e.event_type}")
    print()

    # Print artifacts
    artifacts = workflow.praman.list_by_case("CASE-0001")
    print("Artifacts:")
    for a in artifacts:
        print(f"  {a.artifact_id} ({a.artifact_type})")
    print()
    print("=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
