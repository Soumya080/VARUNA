"""
VARUNA GRID — Data Catalog Builder.

READ-ONLY. Never deletes, renames, moves, or overwrites a raw source file.

Walks the known dataset locations (both inside the repo's data/raw/ and the
sibling directories outside the repo that hold large external downloads —
ASF Sentinel-1 RAW archives, etc.) and writes three JSON files under
data/catalog/:

  dataset_inventory.json  — per-dataset summary: file count, total bytes,
                             a status flag (present / missing / insufficient),
                             and audit-relevant caveats (e.g. CMEMS single-
                             timestep, ERA5 multi-bbox split).
  dataset_paths.json      — dataset_id -> absolute path on this machine.
                             This is a POINTER file. Nothing under it is ever
                             moved to match it.
  checksums.json          — sha256 for files under a size threshold (fast to
                             hash); for larger files only size + mtime is
                             recorded, with checksum: null and a note, since
                             hashing hundreds of GB is not appropriate to do
                             as a side effect of building a catalog.

Re-run this script any time; it fully regenerates all three files from
what is currently on disk. It performs no writes outside data/catalog/.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS_ROOT = REPO_ROOT.parent  # D:\ROUTER(DATASETS)\

# Files at or under this size get a real sha256. Above it, only size+mtime
# is recorded. Kept small deliberately: the Zenodo raw scenes alone are
# ~16-33MB each across several thousand files, and a 50MB threshold was
# found in practice to turn this into a multi-hour full-corpus hash pass
# on a spinning disk. 2MB comfortably covers manifests/metadata/small
# masks while excluding every raw scene and archive.
HASH_SIZE_LIMIT_BYTES = 2 * 1024 * 1024  # 2 MB

CATALOG_DIR = REPO_ROOT / "data" / "catalog"


def _sha256_of(path: Path) -> str | None:
    try:
        if path.stat().st_size > HASH_SIZE_LIMIT_BYTES:
            return None
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _walk_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file()]


def _summarize(root: Path) -> dict[str, Any]:
    files = _walk_files(root)
    real_files = [f for f in files if f.name != ".gitkeep" and f.name != "desktop.ini"]
    total_bytes = sum(f.stat().st_size for f in real_files)
    return {
        "path": str(root),
        "exists": root.exists(),
        "n_files": len(real_files),
        "total_bytes": total_bytes,
    }


# Dataset definitions: id -> (path, known caveats). Paths are absolute so
# the catalog is a pointer, never a relocation.
DATASETS: dict[str, dict[str, Any]] = {
    "zenodo_part1": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "zenodo" / "extracted" / "part1",
        "expected_min_files": 1,
    },
    "zenodo_part2": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "zenodo" / "extracted" / "part2",
        "expected_min_files": 1,
    },
    "zenodo_downloads": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "zenodo" / "downloads",
        "expected_min_files": 1,
    },
    "era5": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "era5",
        "expected_min_files": 1,
        "caveats": [
            "3 GRIB1 files span 3 different spatial bboxes; treat as "
            "spatial_coverage_status=partial until reconciled to their "
            "intersection.",
            "cfgrib/eccodes not confirmed installed in the active "
            "environment at catalog-build time.",
        ],
    },
    "cmems": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "cmems",
        "expected_min_files": 1,
        "caveats": [
            "Both NetCDF files have time=1 (single timestep). "
            "time_series_status=insufficient — cannot drive advection.",
        ],
    },
    "ais": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "ais",
        "expected_min_files": 1,
    },
    "essd": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "essd",
        "expected_min_files": 1,
    },
    "xview3": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "xview3",
        "expected_min_files": 1,
    },
    "bhoonidhi": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "bhoonidhi",
        "expected_min_files": 1,
    },
    "nisar": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "nisar",
        "expected_min_files": 1,
    },
    "risat": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "risat",
        "expected_min_files": 1,
    },
    "sentinel1_repo": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "raw" / "sentinel1",
        "expected_min_files": 1,
    },
    "asf_sentinel1_raw": {
        "path": DATASETS_ROOT / "ASF",
        "expected_min_files": 1,
        "caveats": [
            "Sentinel-1 Level-0 RAW (unfocused). Requires SAR focusing "
            "(SNAP/IPF) before use as imagery — not GRD. Do not treat as "
            "ready NETRA input.",
        ],
    },
    "oil_external": {
        "path": DATASETS_ROOT / "Oil",
        "expected_min_files": 1,
    },
    "netra_gold_v0_1": {
        "path": DATASETS_ROOT / "VARUNA" / "data" / "gold" / "netra",
        "expected_min_files": 1,
    },
}


def _status(summary: dict[str, Any], expected_min_files: int) -> str:
    if not summary["exists"] or summary["n_files"] < expected_min_files:
        return "missing"
    return "present"


def build() -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    inventory: dict[str, Any] = {}
    paths: dict[str, str] = {}
    checksums: dict[str, Any] = {}

    for dataset_id, spec in DATASETS.items():
        root = Path(spec["path"])
        summary = _summarize(root)
        status = _status(summary, spec.get("expected_min_files", 1))
        caveats = spec.get("caveats", [])

        inventory[dataset_id] = {
            **summary,
            "status": status,
            "caveats": caveats,
        }
        paths[dataset_id] = str(root)

        file_entries = []
        for f in _walk_files(root):
            if f.name in (".gitkeep", "desktop.ini"):
                continue
            size = f.stat().st_size
            digest = _sha256_of(f)
            file_entries.append({
                "path": str(f),
                "size_bytes": size,
                "mtime": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "sha256": digest,
                "sha256_note": (
                    None if digest is not None
                    else f"not computed: file exceeds {HASH_SIZE_LIMIT_BYTES} byte threshold"
                ),
            })
        checksums[dataset_id] = file_entries

    generated_at = datetime.now(timezone.utc).isoformat()

    (CATALOG_DIR / "dataset_inventory.json").write_text(
        json.dumps({"generated_at": generated_at, "datasets": inventory}, indent=2)
    )
    (CATALOG_DIR / "dataset_paths.json").write_text(
        json.dumps({"generated_at": generated_at, "paths": paths}, indent=2)
    )
    (CATALOG_DIR / "checksums.json").write_text(
        json.dumps({"generated_at": generated_at, "hash_size_limit_bytes": HASH_SIZE_LIMIT_BYTES,
                    "files": checksums}, indent=2)
    )

    print(f"Wrote catalog to {CATALOG_DIR}")
    for dataset_id, inv in inventory.items():
        print(f"  {dataset_id:24s} {inv['status']:9s} "
              f"n_files={inv['n_files']:<6d} total_bytes={inv['total_bytes']}")


if __name__ == "__main__":
    build()
