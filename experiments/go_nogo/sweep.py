"""Run fair go/no-go sweeps and write JSON/CSV artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from experiments.go_nogo.config import ExperimentConfig, QUICK_CONFIG, config_from_dict
from experiments.go_nogo.runner import run_trial


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _summary(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {"n_trials": 0}
    n = len(rows)
    return {
        "n_trials": n,
        "top1_accuracy": sum(bool(r["top1_correct"]) for r in rows) / n,
        "top3_accuracy": sum(bool(r["top3_correct"]) for r in rows) / n,
        "mrr": sum(float(r["mrr"]) for r in rows) / n,
        "nearest_top1_accuracy": sum(r["nearest_rank"] == 1 for r in rows) / n,
        "deterministic_top1_accuracy": sum(r["deterministic_rank"] == 1 for r in rows) / n,
        "mean_posterior_entropy": sum(float(r["posterior_entropy"]) for r in rows) / n,
    }


def run_sweep(config: ExperimentConfig, output_dir: Path | None = None) -> dict[str, object]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = output_dir or Path(config.output_root) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    trial_id = 0
    for age in config.slick_ages_hours:
        for density in config.traffic_densities:
            for forcing in config.forcing_perturbations:
                for ais in config.ais_uncertainties:
                    for _ in range(config.trials_per_cell):
                        result = run_trial(
                            slick_age_hours=float(age),
                            traffic_density=int(density),
                            forcing_perturbation=str(forcing),
                            ais_uncertainty=str(ais),
                            trial_id=trial_id,
                            config=config,
                            output_dir=out_dir,
                        )
                        row = result.to_row()
                        row["forcing_perturbation"] = forcing
                        row["ais_uncertainty"] = ais
                        rows.append(row)
                        trial_id += 1

    _write_csv(out_dir / "results.csv", rows)
    manifest = {
        "timestamp": timestamp,
        "git_commit": _git_commit(),
        "config": config.to_dict(),
        "summary": _summary(rows),
        "rows": rows,
    }
    (out_dir / "results.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(render_markdown_summary(manifest), encoding="utf-8")
    return manifest


def render_markdown_summary(manifest: dict[str, object]) -> str:
    summary = manifest["summary"]
    assert isinstance(summary, dict)
    return "\n".join(
        [
            "# VARUNA Go/No-Go Fair Sweep",
            "",
            "Synthetic evaluation only. Do not treat these numbers as field validation.",
            "",
            f"- trials: {summary.get('n_trials')}",
            f"- VARUNA top-1: {float(summary.get('top1_accuracy', 0.0)):.3f}",
            f"- VARUNA top-3: {float(summary.get('top3_accuracy', 0.0)):.3f}",
            f"- MRR: {float(summary.get('mrr', 0.0)):.3f}",
            f"- nearest baseline top-1: {float(summary.get('nearest_top1_accuracy', 0.0)):.3f}",
            "- deterministic backtrack top-1: "
            f"{float(summary.get('deterministic_top1_accuracy', 0.0)):.3f}",
            f"- mean posterior entropy: {float(summary.get('mean_posterior_entropy', 0.0)):.3f}",
            "",
            "Limitations: OpenDrift is not used in this synthetic harness; production physics remains blocked until the dependency is installed.",
            "",
        ]
    )


def _load_config(path: Path | None, quick: bool) -> ExperimentConfig:
    if path is None:
        return QUICK_CONFIG if quick else ExperimentConfig()
    return config_from_dict(json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fair VARUNA go/no-go sweep")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    config = _load_config(args.config, args.quick)
    manifest = run_sweep(config, args.output_dir)
    print(json.dumps(manifest["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
