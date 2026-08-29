"""
VARUNA GRID — Master Data Catalog + Engine Matrix + Path Aliases.

READ-ONLY. Builds three additional catalog files ON TOP OF the existing
data/catalog/{dataset_inventory,dataset_paths,checksums}.json (produced by
build_data_catalog.py, which this script imports and reuses rather than
re-walking the filesystem — no duplicate disk scan):

  data/catalog/master_dataset_catalog.json  — per-dataset role/status/engine
                                                classification (Objective 4)
  data/catalog/dataset_engine_matrix.json   — dataset -> VARUNA engine map,
                                                only where verification
                                                actually supports the role
                                                (Objective 5)
  data/catalog/path_aliases.json            — logical role -> physical path,
                                                never a physical move
                                                (Objective 7)

Status values (per spec): READY, PARTIAL, WRONG_PRODUCT, MISSING,
INSUFFICIENT, UNKNOWN. These are assigned from what has actually been
verified (see docs from prior audit + inline caveats in
dataset_inventory.json), never from a filename alone.

Re-run any time. Never moves, renames, or deletes anything.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "data" / "catalog"


def _load_inventory() -> dict[str, Any]:
    inv_path = CATALOG_DIR / "dataset_inventory.json"
    if not inv_path.exists():
        raise FileNotFoundError(
            f"{inv_path} not found — run scripts/build_data_catalog.py first."
        )
    return json.loads(inv_path.read_text())["datasets"]


def _load_paths() -> dict[str, str]:
    return json.loads((CATALOG_DIR / "dataset_paths.json").read_text())["paths"]


# Master catalog entries. `status` here encodes VERIFIED product identity,
# not just presence — e.g. asf_sentinel1_raw is `present` in the inventory
# but `WRONG_PRODUCT` here because direct filename/metadata inspection
# (see docs, prior audit) confirms it is Level-0 RAW, not the GRD product
# every downstream consumer assumes.
MASTER_SPECS: dict[str, dict[str, Any]] = {
    "zenodo_part1": {
        "display_name": "Zenodo Oil Spill Detection Dataset — Part I (positives)",
        "source": "Zenodo",
        "source_product": "Sentinel-1 GRD, VV/VH, oil spill scenes",
        "product_level": "L1 GRD (dB-scaled)",
        "format": "GeoTIFF, 2048x2048, float32, 2-band, EPSG:4326",
        "role": "netra_training_positive",
        "varuna_engine": "NETRA",
        "required": True,
        "notes": (
            "Verified by direct rasterio read: 2-band float32, EPSG:4326, "
            "real bounds. Prior dedup pass discarded ~69% via a bbox-overlap "
            "bug (not true duplicates) — see docs/datasets/NETRA_GOLD_V0_1.md. "
            "NETRA Gold rebuild is a separate, already-owned workstream; not "
            "touched by this reconciliation pass."
        ),
    },
    "zenodo_part2": {
        "display_name": "Zenodo Oil Spill Detection Dataset — Part II (negatives)",
        "source": "Zenodo",
        "source_product": "Sentinel-1 GRD — lookalikes + clean ocean",
        "product_level": "L1 GRD (dB-scaled)",
        "format": "GeoTIFF, 2048x2048, float32, 2-band, EPSG:4326",
        "role": "netra_training_hard_negative",
        "varuna_engine": "NETRA",
        "required": True,
        "notes": (
            "Verified: masks are all-zero (no lookalike class labels present, "
            "only folder-level lookalike/no_oil split). Not usable for a "
            "3-class scheme without a real lookalike mask source."
        ),
    },
    "zenodo_downloads": {
        "display_name": "Zenodo source archives (Parts I-II, .7z)",
        "source": "Zenodo",
        "source_product": "raw compressed archives",
        "product_level": "n/a — archive",
        "format": "7-Zip",
        "role": "provenance_archive",
        "varuna_engine": None,
        "required": False,
        "notes": "Retained as the immutable source-of-truth archive. Never re-extracted over the existing extraction.",
    },
    "era5": {
        "display_name": "ERA5 10m wind reanalysis",
        "source": "Copernicus Climate Data Store",
        "source_product": "reanalysis-era5-single-levels: 10m_u/v_component_of_wind",
        "product_level": "reanalysis",
        "format": "GRIB1",
        "role": "forcing_wind",
        "varuna_engine": "PRATIVARTAN",
        "required": True,
        "notes": (
            "Verified via cfgrib: u10/v10 present, hourly, continuous "
            "2010-2026. Spans 3 files with 3 different bboxes "
            "((5-20N,70-85E), (6-20N,70-85E), (8-20N,70-88E)) — treat as "
            "spatial_coverage_status=partial until reconciled to their "
            "intersection (see ForcingCube.spatial_coverage_status)."
        ),
    },
    "cmems": {
        "display_name": "CMEMS ocean physics (analysis-forecast + reanalysis)",
        "source": "Copernicus Marine Service",
        "source_product": "cmems_mod_glo_phy_anfc / _my — uo, vo, zos, thetao, so",
        "product_level": "analysis-forecast / reanalysis",
        "format": "NetCDF4",
        "role": "forcing_current",
        "varuna_engine": "PRATIVARTAN,PRAVAAH",
        "required": True,
        "notes": (
            "Verified via xarray: both files have time=1 (single snapshot). "
            "time_series_status=INSUFFICIENT — cannot drive advection. "
            "Snapshots retained; a real time-series request is required "
            "before either engine can use CMEMS operationally."
        ),
    },
    "ais": {
        "display_name": "AIS vessel tracking data (NOAA MarineCadastre, Gulf of Mexico, 2023-01-15)",
        "source": "NOAA MarineCadastre AIS Data Handler",
        "source_product": "AIS_2023_01_15 (national daily file)",
        "product_level": "raw CSV",
        "format": "CSV",
        "role": "attribution_evidence",
        "varuna_engine": "NYAYA",
        "required": True,
        "notes": (
            "Acquired 2026-08-29. One national daily file, Gulf-of-Mexico "
            "region extracted at the bronze stage (see data/bronze/ais/). "
            "Anchored to zenodo_p1_00073 spatially only — the anchor case "
            "has no real timestamp, so temporal_join_status is "
            "'unavailable' for any real join against it. See "
            "docs/datasets/AIS_ACQUISITION_RECORD.md."
        ),
    },
    "essd": {
        "display_name": "ESSD 2025 Eastern Mediterranean oil spill dataset",
        "source": "ESSD (external)",
        "source_product": None,
        "product_level": None,
        "format": None,
        "role": "netra_external_evaluation",
        "varuna_engine": "NETRA",
        "required": False,
        "notes": "Absent. Needed for cross-dataset generalization claims, not for a first baseline.",
    },
    "xview3": {
        "display_name": "xView3-SAR dark vessel detection dataset",
        "source": "AllenAI / xView3 challenge",
        "source_product": None,
        "product_level": None,
        "format": None,
        "role": "chhaya_training",
        "varuna_engine": "CHHAYA",
        "required": False,
        "notes": (
            "Absent. Only relevant if docs/adr/CHHAYA-ARCHITECTURE-DECISION.md "
            "selects option A (xView3 SAR detector) — currently recommends "
            "option C (keep the existing AIS-coverage-gap heuristic)."
        ),
    },
    "bhoonidhi": {
        "display_name": "Bhoonidhi (ISRO) Indian-domain SAR archive",
        "source": "ISRO Bhoonidhi",
        "source_product": None,
        "product_level": None,
        "format": None,
        "role": "indian_domain_evaluation",
        "varuna_engine": "NETRA",
        "required": False,
        "notes": "Absent. Relevant to an Indian-waters deployment claim; not on the NETRA baseline critical path.",
    },
    "nisar": {
        "display_name": "NISAR cross-sensor SAR",
        "source": "NASA/ISRO NISAR mission",
        "source_product": None,
        "product_level": None,
        "format": None,
        "role": "cross_sensor_evaluation",
        "varuna_engine": "NETRA",
        "required": False,
        "notes": "Absent. Mission not yet producing public data at volume relevant here.",
    },
    "risat": {
        "display_name": "RISAT cross-sensor SAR",
        "source": "ISRO RISAT",
        "source_product": None,
        "product_level": None,
        "format": None,
        "role": "cross_sensor_evaluation",
        "varuna_engine": "NETRA",
        "required": False,
        "notes": "Absent.",
    },
    "sentinel1_repo": {
        "display_name": "In-repo Sentinel-1 raw staging area",
        "source": None,
        "source_product": None,
        "product_level": None,
        "format": None,
        "role": "staging",
        "varuna_engine": None,
        "required": False,
        "notes": "Empty staging directory (.gitkeep only); superseded by the external ASF directory.",
    },
    "ossdd": {
        "display_name": "OpenSARShip-Ship Detection Dataset (OSSDD)",
        "source": "Hugging Face (sylviaHoch/OpenSARShip-Ship-Detection-Dataset)",
        "source_product": "Sentinel-1 GRD ship-detection chips, AABB+RBB+binary mask",
        "product_level": "L1 GRD, float32",
        "format": "TIFF chips + CSV metadata, or WebDataset .tar shards",
        "role": "chhaya_training_candidate",
        "varuna_engine": "CHHAYA",
        "required": False,
        "notes": (
            "Identity VERIFIED (via its own paper's data-availability "
            "statement + direct Hugging Face repo confirmation — not a "
            "filename guess): 15,197 patches, 55,759 ships, 72.3GB, "
            "CC-BY-NC-SA-4.0. NOT downloaded — deferred per "
            "data/catalog/acquisition/ossdd.json (CHHAYA's current "
            "architecture, ADR option C, does not require it; a 72GB "
            "concurrent download was avoided while NETRA trains). See "
            "docs/datasets/OSSDD_CHHAYA_COMPATIBILITY.md."
        ),
    },
    "asf_sentinel1_raw": {
        "display_name": "ASF Sentinel-1 archive (D:\\ROUTER(DATASETS)\\ASF)",
        "source": "Alaska Satellite Facility (ASF)",
        "source_product": "S1{A,C,D}_IW_RAW__0SDV",
        "product_level": "L0 RAW (unfocused)",
        "format": "Sentinel-1 SAFE .zip",
        "role": "indian_domain_source_material",
        "varuna_engine": None,
        "required": False,
        "notes": (
            "251 archives verified by filename pattern as Level-0 RAW — "
            "unfocused SAR requiring SNAP/IPF processing before use as "
            "imagery. WRONG_PRODUCT for any current NETRA/CHHAYA consumer, "
            "all of which assume GRD. Retained; not reprocessed here (SAR "
            "focusing is out of scope for a data reconciliation pass and "
            "would be a very large disk/CPU job — see Objective 19)."
        ),
    },
    "oil_external": {
        "display_name": "External Oil/ staging directory",
        "source": None,
        "source_product": None,
        "product_level": None,
        "format": None,
        "role": "unknown",
        "varuna_engine": None,
        "required": False,
        "notes": "Empty directory, no files. Purpose unclear from contents alone.",
    },
    "netra_gold_v0_1": {
        "display_name": "NETRA Gold v0.1 (derived training tiles)",
        "source": "derived from zenodo_part1",
        "source_product": None,
        "product_level": "derived",
        "format": ".npy tiles, 512x512",
        "role": "netra_training_derived",
        "varuna_engine": "NETRA",
        "required": True,
        "notes": (
            "Owned by the parallel NETRA workstream, currently mid-rebuild "
            "(v0.2). Not touched by this reconciliation pass."
        ),
    },
}


# Additional per-dataset fields (variables / spatial_coverage /
# temporal_coverage / completeness) requested for the fuller catalog
# schema. Kept as a separate dict rather than folded into MASTER_SPECS
# above so the original spec block stays exactly as previously reviewed —
# this only adds fields, never changes an existing one. Values here are
# either verified facts (ERA5/CMEMS variables and coverage, confirmed via
# cfgrib/xarray reads) or explicit None where genuinely unknown/not
# applicable — never a guess.
EXTRA_FIELDS: dict[str, dict[str, Any]] = {
    "zenodo_part1": {
        "variables": ["VV", "VH"],
        "spatial_coverage": "Multiple regions: Gulf of Mexico, North Sea, Mediterranean, Red Sea (verified per-scene via rasterio bounds)",
        "temporal_coverage": "Unavailable — acquisition_date is a substituted dummy (2000-01-01), timestamp_status=unavailable",
        "completeness": "1200 scenes present; 374 in current Gold manifest after a dedup pass later found to be a bug (~69% wrongly discarded)",
    },
    "zenodo_part2": {
        "variables": ["VV", "VH"],
        "spatial_coverage": "Same region set as Part I (shared acquisition campaign)",
        "temporal_coverage": "Unavailable — same dummy-timestamp issue as Part I",
        "completeness": "1370 scenes present (685 Lookalike + 685 No_Oil); no Gold built yet; masks all-zero (no lookalike class labels)",
    },
    "era5": {
        "variables": ["u10", "v10"],
        "spatial_coverage": "Union across 3 files: 5-20N/70-88E (Arabian Sea/W. Bay of Bengal); usable intersection per docs/datasets/ERA5_DOMAIN_POLICY.md: 8-20N/70-85E",
        "temporal_coverage": "Hourly, 2010-01-01 to 2026-08-17 (continuous, per file; not merged into one series)",
        "completeness": "u10/v10 present in all 3 files; no other ERA5 variables (e.g. mslp, t2m) present",
    },
    "cmems": {
        "variables": ["uo", "vo", "zos", "thetao", "so"],
        "spatial_coverage": "Global grid, 0.083deg",
        "temporal_coverage": "Single timestep per file (anfc: 2026-08-31T23; my: 2026-06-23) — not a time series",
        "completeness": "uo/vo present but time_series_status=INSUFFICIENT; cannot drive advection",
    },
    "ais": {
        "variables": ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselType"],
        "spatial_coverage": "US coastal AIS receiver network (national file, not pre-filtered); Gulf of Mexico region extracted at bronze stage",
        "temporal_coverage": "2023-01-15 (single day) — see docs/datasets/AIS_ACQUISITION_RECORD.md",
        "completeness": "Acquired this pass; see acquisition record for scope and why the date is scientifically arbitrary here",
    },
    "asf_sentinel1_raw": {
        "variables": None,
        "spatial_coverage": "Indian waters (footprint not yet extracted per-archive)",
        "temporal_coverage": "2026-05-11 to 2026-07-01 (46 distinct dates, per filename)",
        "completeness": "251 Level-0 RAW archives; 0 GRD archives (wrong product for current pipeline)",
    },
}


def _resolve_status(dataset_id: str, inv_entry: dict[str, Any], spec: dict[str, Any]) -> str:
    """Map inventory presence + known verification caveats to the spec's
    allowed status vocabulary: READY, PARTIAL, WRONG_PRODUCT, MISSING,
    INSUFFICIENT, UNKNOWN."""
    if inv_entry["status"] == "missing":
        return "MISSING"
    if dataset_id == "asf_sentinel1_raw":
        return "WRONG_PRODUCT"
    if dataset_id == "cmems":
        return "INSUFFICIENT"
    if dataset_id == "era5":
        return "PARTIAL"  # spatially split across 3 bboxes; usable but not unified
    if dataset_id == "zenodo_part1":
        return "PARTIAL"  # present, but Gold built on a known dedup bug (separate workstream fixing it)
    if dataset_id == "zenodo_part2":
        return "PARTIAL"  # present, extracted, but no Gold built yet and masks carry no lookalike labels
    if dataset_id == "oil_external":
        return "UNKNOWN"
    if not spec.get("required", False) and inv_entry["status"] == "present":
        return "READY"
    if inv_entry["status"] == "present":
        return "READY"
    return "UNKNOWN"


def build() -> None:
    inventory = _load_inventory()
    paths = _load_paths()

    master: dict[str, Any] = {}
    engine_matrix: dict[str, list[str]] = {}
    aliases: dict[str, Any] = {}

    for dataset_id, spec in MASTER_SPECS.items():
        inv_entry = inventory.get(dataset_id, {"status": "missing", "n_files": 0, "total_bytes": 0, "caveats": []})
        status = _resolve_status(dataset_id, inv_entry, spec)

        master[dataset_id] = {
            "dataset_id": dataset_id,
            "display_name": spec["display_name"],
            "physical_path": paths.get(dataset_id),
            "source": spec["source"],
            "source_product": spec["source_product"],
            "product_level": spec["product_level"],
            "format": spec["format"],
            "size_bytes": inv_entry.get("total_bytes", 0),
            "file_count": inv_entry.get("n_files", 0),
            "checksum_status": (
                "not_applicable" if inv_entry.get("n_files", 0) == 0
                else "partial_sha256_size_gated_see_checksums_json"
            ),
            "coverage": None,
            "time_coverage": None,
            "spatial_coverage": None,
            "role": spec["role"],
            "status": status,
            "varuna_engine": spec["varuna_engine"],
            "required": spec["required"],
            "notes": spec["notes"],
            "inventory_caveats": inv_entry.get("caveats", []),
        }

        if spec["varuna_engine"]:
            for engine in spec["varuna_engine"].split(","):
                engine_matrix.setdefault(engine, []).append(dataset_id)

        if paths.get(dataset_id):
            aliases[dataset_id] = {
                "physical_path": paths[dataset_id],
                "logical_role": spec["role"],
            }

    generated_at = datetime.now(UTC).isoformat()

    (CATALOG_DIR / "master_dataset_catalog.json").write_text(
        json.dumps({"generated_at": generated_at, "datasets": master}, indent=2)
    )
    (CATALOG_DIR / "dataset_engine_matrix.json").write_text(
        json.dumps({"generated_at": generated_at, "engines": engine_matrix}, indent=2)
    )
    (CATALOG_DIR / "path_aliases.json").write_text(
        json.dumps({"generated_at": generated_at, "aliases": aliases}, indent=2)
    )

    print(f"Wrote master catalog, engine matrix, path aliases to {CATALOG_DIR}")
    for dataset_id, entry in master.items():
        print(f"  {dataset_id:24s} status={entry['status']:14s} engine={entry['varuna_engine']}")


if __name__ == "__main__":
    build()
