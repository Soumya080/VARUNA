"""Measure where CASE-VALID's end-to-end time is actually spent.

Instruments the real path (GoldenCaseWorkflow -> build_product_case) plus
the live HTTP endpoint, so optimisation targets come from measurement
rather than guesswork.
"""
from __future__ import annotations

import time
import urllib.request

from apps.api.dependencies import get_golden_case_workflow, get_replay_smriti_store
from varuna_integration.product_case import build_product_case


def _t(label: str, fn):
    t0 = time.perf_counter()
    out = fn()
    dt = (time.perf_counter() - t0) * 1000
    print(f"  {label:<42} {dt:8.1f} ms")
    return out, dt


def main() -> None:
    print("=== in-process stages (CASE-VALID) ===")
    wf = get_golden_case_workflow()
    smriti = get_replay_smriti_store()

    result, t_run = _t("GoldenCaseWorkflow.run_replay_case(force=True)",
                       lambda: wf.run_replay_case("LAT-CASE-VALID", "CASE-VALID", force=True))
    _, t_compose = _t("build_product_case (intelligence compose)",
                      lambda: build_product_case(result, wf, smriti=smriti))

    # stage-level timings recorded by the pipeline itself
    stages = getattr(result.run, "stages", {}) or {}
    if stages:
        print("\n  per-stage runtime_seconds recorded by the run:")
        for name, r in stages.items():
            rt = getattr(r, "runtime_seconds", None)
            print(f"    {name:<24} {'-' if rt is None else f'{rt*1000:8.1f} ms'}"
                  f"   status={getattr(r,'status','?')}")

    print("\n=== live HTTP endpoint ===")
    for i in range(3):
        t0 = time.perf_counter()
        with urllib.request.urlopen("http://127.0.0.1:8000/v1/replay/CASE-VALID", timeout=60) as r:
            n = len(r.read())
        print(f"  GET /v1/replay/CASE-VALID  #{i+1}          "
              f"{(time.perf_counter()-t0)*1000:8.1f} ms  ({n} bytes)")

    print(f"\n  in-process total: {(t_run + t_compose):.1f} ms "
          f"(run {t_run:.1f} + compose {t_compose:.1f})")


if __name__ == "__main__":
    main()
