"""
VARUNA GRID — Training Readiness Gate.

READ-ONLY. Never modifies a manifest, a Gold tile, or any source file.
Checks whether an engine's Gold dataset is structurally ready for training,
by re-deriving each required field from the manifest and (for GOLD_VALID) a
bounded, random sample of the actual tile files on disk — never trusting a
directory glob or filename ordering as authoritative.

Required checks per engine, per Phase 22:
  DATASET_VALID        source datasets recorded and locatable
  MANIFEST_VALID        manifest file exists, parses, has required keys
  SPLIT_VALID           split policy present; no scene appears in >1 split
  LEAKAGE_VALID          all applicable leakage checks report PASS; a
                          genuinely unmeasurable one (e.g. temporal, when
                          the source has no timestamps) must explicitly say
                          UNAVAILABLE, never be silently absent or PASS
  NORMALIZATION_VALID    normalization is frozen, computed from train only
  GOLD_VALID             a sample of manifest tile paths actually exist on
                          disk, are shaped as declared, and contain no NaN/Inf
  DATALOADER_VALID       a real Dataset class exists that reads the manifest
                          (not a bare glob) — verified by import + AST-level
                          check for `glob(` in the module source, not by
                          instantiating/loading anything

TRAINING_READY = TRUE only if every one of the above is TRUE for that engine.

This script does not train, does not build a Gold dataset, and does not
modify anything under packages/varuna_netra/ or data/gold/ — it only reads.

Usage: python scripts/check_training_readiness.py [--engine netra] [--sample-size 200]
"""
from __future__ import annotations

import argparse
import ast
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ReadinessReport:
    engine: str
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    training_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "checks": self.checks,
            "details": self.details,
            "training_ready": self.training_ready,
        }


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def check_netra(sample_size: int = 200, seed: int = 42) -> ReadinessReport:
    report = ReadinessReport(engine="netra")
    manifest_path = REPO_ROOT / "data" / "manifests" / "netra_gold_v0_2.json"
    manifest = _load_manifest(manifest_path)

    # MANIFEST_VALID
    required_top_keys = {
        "dataset_id", "dataset_version", "git_commit", "channels",
        "label_mapping", "counts", "dedup", "split", "leakage",
        "normalization", "tiles",
    }
    if manifest is None:
        report.checks["MANIFEST_VALID"] = False
        report.details["manifest_error"] = f"{manifest_path} missing or unparseable"
        report.training_ready = False
        return report
    missing_keys = required_top_keys - set(manifest.keys())
    report.checks["MANIFEST_VALID"] = not missing_keys
    if missing_keys:
        report.details["manifest_missing_keys"] = sorted(missing_keys)

    # DATASET_VALID — source datasets recorded and their raw location exists
    source_datasets = manifest.get("counts", {}).get("pool_by_source", {})
    dataset_paths = {
        "zenodo_part1": REPO_ROOT / "data" / "raw" / "zenodo" / "extracted" / "part1",
        "zenodo_part2_lookalike": REPO_ROOT / "data" / "raw" / "zenodo" / "extracted" / "part2",
        "zenodo_part2_no_oil": REPO_ROOT / "data" / "raw" / "zenodo" / "extracted" / "part2",
    }
    dataset_ok = bool(source_datasets)
    missing_sources = []
    for src in source_datasets:
        p = dataset_paths.get(src)
        if p is None or not p.exists():
            dataset_ok = False
            missing_sources.append(src)
    report.checks["DATASET_VALID"] = dataset_ok
    report.details["source_datasets"] = source_datasets
    if missing_sources:
        report.details["dataset_missing_sources"] = missing_sources

    # SPLIT_VALID — split policy present, no scene in more than one split
    split_block = manifest.get("split", {})
    scene_to_splits: dict[str, set[str]] = {}
    for tile in manifest.get("tiles", []):
        scene_to_splits.setdefault(tile["scene_id"], set()).add(tile["split"])
    cross_split_scenes = {s: splits for s, splits in scene_to_splits.items() if len(splits) > 1}
    split_valid = bool(split_block) and not cross_split_scenes
    report.checks["SPLIT_VALID"] = split_valid
    report.details["split_strategy"] = split_block.get("strategy")
    report.details["n_scenes_in_multiple_splits"] = len(cross_split_scenes)
    if cross_split_scenes:
        report.details["cross_split_scene_sample"] = dict(list(cross_split_scenes.items())[:5])

    # LEAKAGE_VALID — every reported check is PASS, except temporal, which
    # must be either PASS or the explicit UNAVAILABLE sentinel (never silent,
    # never fabricated as PASS).
    leakage = manifest.get("leakage", {})
    leakage_ok = bool(leakage) and not leakage.get("failures")
    for key in ("scene_identity", "content_duplication", "footprint_overlap"):
        if leakage.get(key) != "PASS":
            leakage_ok = False
    temporal = leakage.get("temporal")
    if temporal not in ("PASS", "UNAVAILABLE"):
        leakage_ok = False
    report.checks["LEAKAGE_VALID"] = leakage_ok
    report.details["leakage_temporal_status"] = temporal
    report.details["leakage_failures"] = leakage.get("failures", [])

    # NORMALIZATION_VALID — frozen record, computed from train only
    norm = manifest.get("normalization", {})
    norm_ok = (
        bool(norm.get("normalization_version"))
        and norm.get("computed_from_split") == "train"
        and bool(norm.get("method"))
    )
    report.checks["NORMALIZATION_VALID"] = norm_ok
    report.details["normalization_version"] = norm.get("normalization_version")

    # GOLD_VALID — bounded random sample of tiles actually exist, correct
    # shape, no NaN/Inf. Sampling, not a full 41k-tile scan, to stay light
    # on the shared disk while NETRA trains (Phase 29/30).
    tiles = manifest.get("tiles", [])
    rng = random.Random(seed)
    sample = rng.sample(tiles, min(sample_size, len(tiles))) if tiles else []
    gold_ok = bool(tiles)
    bad_tiles = []
    for t in sample:
        img_path = REPO_ROOT / t["img"]
        mask_path = REPO_ROOT / t["mask"]
        if not img_path.exists() or not mask_path.exists():
            gold_ok = False
            bad_tiles.append({"tile_id": t["tile_id"], "reason": "file_missing"})
            continue
        try:
            img = np.load(img_path)
            mask = np.load(mask_path)
        except (OSError, ValueError) as e:
            gold_ok = False
            bad_tiles.append({"tile_id": t["tile_id"], "reason": f"load_error: {e}"})
            continue
        if img.shape[0] != len(manifest.get("channels", [])):
            gold_ok = False
            bad_tiles.append({"tile_id": t["tile_id"], "reason": f"unexpected channel count {img.shape}"})
        if not np.isfinite(img).all():
            gold_ok = False
            bad_tiles.append({"tile_id": t["tile_id"], "reason": "non-finite values in image"})
        if not np.isfinite(mask).all():
            gold_ok = False
            bad_tiles.append({"tile_id": t["tile_id"], "reason": "non-finite values in mask"})
    report.checks["GOLD_VALID"] = gold_ok
    report.details["gold_sample_size"] = len(sample)
    report.details["gold_total_tiles"] = len(tiles)
    if bad_tiles:
        report.details["gold_bad_tiles_sample"] = bad_tiles[:10]

    # DATALOADER_VALID — a real Dataset class exists and does NOT construct
    # its file list via a bare directory glob (checked via AST, not by
    # instantiating/loading anything).
    dataset_module = REPO_ROOT / "packages" / "varuna_netra" / "dataset" / "gold.py"
    dataloader_ok = False
    if dataset_module.exists():
        src = dataset_module.read_text()
        tree = ast.parse(src)
        has_dataset_class = any(
            isinstance(node, ast.ClassDef)
            and any(
                (isinstance(base, ast.Attribute) and base.attr == "Dataset")
                or (isinstance(base, ast.Name) and base.id == "Dataset")
                for base in node.bases
            )
            for node in ast.walk(tree)
        )
        uses_glob = "glob(" in src or ".glob(" in src or "listdir(" in src
        references_manifest = "manifest" in src.lower()
        dataloader_ok = has_dataset_class and references_manifest and not uses_glob
        report.details["dataloader_module"] = str(dataset_module.relative_to(REPO_ROOT))
        report.details["dataloader_has_dataset_class"] = has_dataset_class
        report.details["dataloader_uses_glob"] = uses_glob
        report.details["dataloader_references_manifest"] = references_manifest
    else:
        report.details["dataloader_module"] = None
    report.checks["DATALOADER_VALID"] = dataloader_ok

    report.training_ready = all(report.checks.values())
    return report


def check_chhaya() -> ReadinessReport:
    report = ReadinessReport(engine="chhaya")
    # Per docs/adr/CHHAYA-ARCHITECTURE-DECISION.md (option C, the wired
    # AIS-coverage-gap heuristic), CHHAYA does not currently require a
    # trained model or a Gold dataset. All checks are N/A, not FALSE — this
    # engine is not blocked, it is simply not on a training path right now.
    for key in ("DATASET_VALID", "MANIFEST_VALID", "SPLIT_VALID", "LEAKAGE_VALID",
                "NORMALIZATION_VALID", "GOLD_VALID", "DATALOADER_VALID"):
        report.checks[key] = None  # type: ignore[assignment]
    report.details["reason"] = (
        "CHHAYA's current architecture (docs/adr/CHHAYA-ARCHITECTURE-DECISION.md, "
        "option C) is the AIS-coverage-gap heuristic, which requires no "
        "trained model and no Gold dataset. Not applicable, not blocked."
    )
    report.training_ready = False  # explicit: no training path exists to be "ready"
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["netra", "chhaya", "all"], default="all")
    parser.add_argument("--sample-size", type=int, default=200)
    args = parser.parse_args()

    reports: list[ReadinessReport] = []
    if args.engine in ("netra", "all"):
        reports.append(check_netra(sample_size=args.sample_size))
    if args.engine in ("chhaya", "all"):
        reports.append(check_chhaya())

    print("VARUNA GRID v2 — Training Readiness Gate")
    print("=" * 60)
    for r in reports:
        print(f"\n[{r.engine.upper()}]")
        for check, val in r.checks.items():
            status = "N/A" if val is None else ("PASS" if val else "FAIL")
            print(f"  {check:22s} {status}")
        print(f"  {'TRAINING_READY':22s} {r.training_ready}")

    out = {"generated_at": __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(),
        "reports": [r.to_dict() for r in reports]}
    out_path = REPO_ROOT / "reports" / "training_readiness.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
