"""
VARUNA GRID — Data Reconciliation Report Builder.

READ-ONLY. Reads data/catalog/{dataset_inventory,master_dataset_catalog,
dataset_engine_matrix}.json (produced by build_data_catalog.py and
build_master_catalog.py — not re-walking the filesystem here) and writes:

  reports/data_reconciliation_report.json
  reports/data_reconciliation_report.txt

Per-dataset state uses the vocabulary requested for this report:
PRESENT, PRESENT BUT WRONG PRODUCT, PRESENT BUT INCOMPLETE, MISSING, READY,
INSUFFICIENT — distinct from (but derived from) the master catalog's
READY/PARTIAL/WRONG_PRODUCT/MISSING/INSUFFICIENT/UNKNOWN status vocabulary.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "data" / "catalog"
REPORTS_DIR = REPO_ROOT / "reports"

_STATUS_MAP = {
    "READY": "READY",
    "PARTIAL": "PRESENT BUT INCOMPLETE",
    "WRONG_PRODUCT": "PRESENT BUT WRONG PRODUCT",
    "MISSING": "MISSING",
    "INSUFFICIENT": "INSUFFICIENT",
    "UNKNOWN": "MISSING",  # oil_external: present as a dir, but zero files
}


def build() -> None:
    master = json.loads((CATALOG_DIR / "master_dataset_catalog.json").read_text())["datasets"]

    required_ids = [
        ("Zenodo Part I", "zenodo_part1"),
        ("Zenodo Part II", "zenodo_part2"),
        ("Zenodo Part III", None),   # not in catalog: never downloaded
        ("ESSD", "essd"),
        ("xView3", "xview3"),
        ("AIS", "ais"),
        ("ERA5", "era5"),
        ("CMEMS", "cmems"),
        ("Bhoonidhi", "bhoonidhi"),
        ("NISAR", "nisar"),
        ("RISAT", "risat"),
        ("Sentinel-1 GRD", None),    # not in catalog: only RAW (asf_sentinel1_raw) present
    ]

    report: dict[str, Any] = {}
    for display_name, dataset_id in required_ids:
        if dataset_id is None:
            report[display_name] = {
                "dataset_id": None,
                "state": "MISSING",
                "notes": (
                    "Never downloaded; no local path exists."
                    if display_name == "Zenodo Part III" else
                    "Only Level-0 RAW is present (dataset_id=asf_sentinel1_raw, "
                    "251 files, 387.9GB) — GRD (the product every downstream "
                    "consumer assumes) has not been acquired."
                ),
            }
            continue
        entry = master.get(dataset_id)
        if entry is None:
            report[display_name] = {"dataset_id": dataset_id, "state": "MISSING", "notes": "not in catalog"}
            continue
        report[display_name] = {
            "dataset_id": dataset_id,
            "state": _STATUS_MAP.get(entry["status"], "MISSING"),
            "size_bytes": entry["size_bytes"],
            "file_count": entry["file_count"],
            "physical_path": entry["physical_path"],
            "varuna_engine": entry["varuna_engine"],
            "notes": entry["notes"],
        }

    generated_at = datetime.now(UTC).isoformat()
    out = {"generated_at": generated_at, "required_datasets": report}

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "data_reconciliation_report.json").write_text(json.dumps(out, indent=2))

    lines = [
        "VARUNA GRID v2 — Data Reconciliation Report",
        f"Generated: {generated_at}",
        "=" * 60,
    ]
    for name, entry in report.items():
        lines.append(f"{name:20s} {entry['state']}")
        if entry.get("notes"):
            lines.append(f"  {entry['notes']}")
    (REPORTS_DIR / "data_reconciliation_report.txt").write_text("\n".join(lines) + "\n")

    print(f"Wrote reconciliation report to {REPORTS_DIR}")
    for name, entry in report.items():
        print(f"  {name:20s} {entry['state']}")


if __name__ == "__main__":
    build()
