"""
VARUNA GRID — targeted checksum update for newly acquired AIS files.

READ-ONLY. Appends/updates just the `ais` entry in data/catalog/checksums.json
and data/catalog/dataset_inventory.json without re-walking every other
dataset (those are large and unchanged; re-hashing them here would be
exactly the kind of disk contention Phase 25 asks to avoid).

Uses the same size threshold and hashing logic as build_data_catalog.py so
the two stay consistent if re-run together later.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "data" / "catalog"
AIS_RAW_DIR = REPO_ROOT / "data" / "raw" / "ais"

HASH_SIZE_LIMIT_BYTES = 2 * 1024 * 1024  # matches build_data_catalog.py


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


def update() -> None:
    files = [p for p in AIS_RAW_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep"]
    total_bytes = sum(f.stat().st_size for f in files)

    file_entries = []
    for f in files:
        size = f.stat().st_size
        digest = _sha256_of(f)
        file_entries.append({
            "path": str(f),
            "size_bytes": size,
            "mtime": datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
            "sha256": digest,
            "sha256_note": None if digest is not None else f"not computed: file exceeds {HASH_SIZE_LIMIT_BYTES} byte threshold; see data/catalog/acquisition/ais.json for the archive's sha256",
        })

    checksums_path = CATALOG_DIR / "checksums.json"
    checksums = json.loads(checksums_path.read_text())
    checksums["files"]["ais"] = file_entries
    checksums["generated_at"] = datetime.now(UTC).isoformat()
    checksums_path.write_text(json.dumps(checksums, indent=2))

    inventory_path = CATALOG_DIR / "dataset_inventory.json"
    inventory = json.loads(inventory_path.read_text())
    inventory["datasets"]["ais"] = {
        "path": str(AIS_RAW_DIR),
        "exists": True,
        "n_files": len(files),
        "total_bytes": total_bytes,
        "status": "present",
        "caveats": [
            "Single day (2023-01-15), Gulf of Mexico region within a national "
            "file. Anchor case (zenodo_p1_00073) has no real timestamp, so "
            "temporal_join_status will be 'unavailable' for any real join "
            "against it — see docs/datasets/AIS_ACQUISITION_RECORD.md.",
        ],
    }
    inventory["generated_at"] = datetime.now(UTC).isoformat()
    inventory_path.write_text(json.dumps(inventory, indent=2))

    print(f"Updated checksums.json and dataset_inventory.json: ais -> {len(files)} files, {total_bytes:,} bytes")


if __name__ == "__main__":
    update()
