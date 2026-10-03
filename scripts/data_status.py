"""
VARUNA GRID — Universal Data Status.

READ-ONLY. Reads data/catalog/master_dataset_catalog.json (produced by
build_master_catalog.py — not re-walking the filesystem here) and prints a
one-line-per-dataset human status report, plus the LOCKED_EVALUATION /
FUTURE_EVALUATION / NOT_REQUIRED_YET annotations that master_dataset_catalog
alone doesn't carry (those are acquisition-policy labels, not filesystem
facts, so they're layered on here rather than baked into the catalog).

Run any time: `python scripts/data_status.py`
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "data" / "catalog"

# Acquisition-policy annotations layered onto the master catalog's
# filesystem-derived status. Not every MISSING dataset is equally missing —
# some are locked-for-evaluation, some are deliberately deferred, some are
# genuinely just absent and wanted.
POLICY_LABEL: dict[str, str] = {
    "zenodo_part1": "TRAINING",
    "zenodo_part2": "TRAINING",
    "zenodo_downloads": "PROVENANCE_ARCHIVE",
    "era5": "OPERATIONAL",
    "cmems": "OPERATIONAL",
    "ais": "OPERATIONAL",
    "essd": "LOCKED_EVALUATION",
    "xview3": "NOT_REQUIRED_YET",
    "ossdd": "IDENTITY_VERIFIED_DEFERRED",
    "bhoonidhi": "FUTURE_EVALUATION",
    "nisar": "FUTURE_EVALUATION",
    "risat": "FUTURE_EVALUATION",
    "sentinel1_repo": "STAGING_EMPTY",
    "asf_sentinel1_raw": "FUTURE_EVALUATION",  # Indian-domain, needs GRD not RAW
    "oil_external": "UNKNOWN",
    "netra_gold_v0_1": "TRAINING_DERIVED",
}

# Datasets referenced in the spec that have no catalog entry at all today
# (never downloaded — not even an empty placeholder directory).
NOT_IN_CATALOG: dict[str, str] = {
    "Zenodo Part III": "LOCKED_EVALUATION / MISSING",
}


def build() -> None:
    master_path = CATALOG_DIR / "master_dataset_catalog.json"
    if not master_path.exists():
        raise FileNotFoundError(f"{master_path} not found — run scripts/build_master_catalog.py first.")
    master = json.loads(master_path.read_text())["datasets"]

    print("VARUNA GRID v2 — Data Status")
    print("=" * 72)
    print(f"{'Dataset':24s} {'Status':14s} {'Policy':20s} {'Engine'}")
    print("-" * 72)
    for dataset_id, entry in master.items():
        status = entry["status"]
        policy = POLICY_LABEL.get(dataset_id, "")
        engine = entry.get("varuna_engine") or "-"
        print(f"{dataset_id:24s} {status:14s} {policy:20s} {engine}")

    for name, label in NOT_IN_CATALOG.items():
        print(f"{name:24s} {'MISSING':14s} {label}")

    print("=" * 72)
    print(f"{'physical_path':<24s} see data/catalog/dataset_paths.json")


if __name__ == "__main__":
    build()
