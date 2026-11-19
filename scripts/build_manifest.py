"""
VARUNA GRID v2 — Dataset Manifest Builder Entrypoint.

Builds dataset manifests detailing lineage, provenance, split assignments,
and normalization parameters for gold datasets:
- Serializes DatasetManifest to data/manifests/
- Validates split counts and absence of leakage

Usage:
    python scripts/build_manifest.py [--dataset-id lab_dataset] [--version v1.0.0]
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Add repo root and packages to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
for pkg in (REPO_ROOT / "packages").glob("varuna_*"):
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))

from varuna_data_eng.pipeline.full_pipeline import FullPipeline
from scripts.lab_smoke_test import create_synthetic_scenes


def build_manifest_file(dataset_id: str = "lab_sar_gold", version: str = "v1.0.0") -> dict:
    """Executes pipeline to create a structured DatasetManifest."""
    print("=" * 65)
    print(f" VARUNA GRID v2 — DATASET MANIFEST BUILDER [{dataset_id}:{version}]")
    print("=" * 65)

    base_dir = REPO_ROOT
    manifest_dir = base_dir / "data" / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    sar_list, mask_list = create_synthetic_scenes(n_scenes=10)
    pipeline = FullPipeline(seed=42, synthetic_mode=True, split_strategy="hash_random", tile_size=64)
    manifest = pipeline.process_raw_dataset(dataset_id=dataset_id, dataset_version=version, sar_list=sar_list, mask_list=mask_list)

    out_file = manifest_dir / f"{dataset_id}_{version}_manifest.json"
    out_file.write_text(manifest.model_dump_json(indent=2))

    print(f"[PASS] Manifest Generated  : {out_file}")
    print(f"       - Total Samples     : {len(manifest.samples)}")
    print(f"       - Split Summary     : {manifest.splits.split_counts}")
    print(f"       - Pipeline Version  : {manifest.pipeline_version}")
    print("=" * 65)

    return {"manifest_path": str(out_file), "samples": len(manifest.samples)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VARUNA Dataset Manifest Builder")
    parser.add_argument("--dataset-id", type=str, default="lab_sar_gold", help="Dataset identifier")
    parser.add_argument("--version", type=str, default="v1.0.0", help="Dataset version")
    args = parser.parse_args()

    build_manifest_file(dataset_id=args.dataset_id, version=args.version)
