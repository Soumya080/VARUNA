"""
VARUNA GRID — Real AIS ingestion, validation, and canonicalization.

READ-ONLY on the raw CSV (data/raw/ais/2023-01-15/AIS_2023_01_15.csv).
Streams it in chunks (868MB, national daily file — not loaded whole into
memory), filters to a Gulf-of-Mexico bbox (the anchor case's region,
generously padded), runs it through the existing AISCleaner, and writes:

  data/bronze/ais/gulf_2023-01-15_raw_points.json   — validation summary
                                                        + per-point records
                                                        before cleaning
  data/bronze/ais/gulf_2023-01-15_tracks.json        — RawAISTrack list
                                                        after AISCleaner,
                                                        full provenance
                                                        retained

Never modifies data/raw/ais/2023-01-15/AIS_2023_01_15.csv.

Usage: python scripts/ingest_real_ais.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from varuna_data_eng.preprocessing.ais_cleaner import AISCleaner
from varuna_data_eng.schemas.ais import RawAISPoint
from varuna_data_eng.schemas.provenance import DataProvenance

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = REPO_ROOT / "data" / "raw" / "ais" / "2023-01-15" / "AIS_2023_01_15.csv"
BRONZE_DIR = REPO_ROOT / "data" / "bronze" / "ais"

# Tight radius around the anchor case (zenodo_p1_00073: lon [-92.14,-91.96],
# lat [19.37,19.55]), not the full Gulf of Mexico. A first attempt at the
# generous full-Gulf bbox produced ~2.4M+ in-bbox rows and OOM'd building
# that many RawAISPoint pydantic objects concurrently with NETRA's own
# training process holding several GB — this bbox is still genuinely
# anchored to the real case, just proportioned to what a single-day
# national file can support in memory on this machine.
BBOX = {"min_lon": -94.14, "max_lon": -89.96, "min_lat": 17.37, "max_lat": 21.55}

PROVENANCE = DataProvenance(
    source_id="ais.marinecadastre.2023-01-15",
    source_version="AIS_2023_01_15",
    download_url="https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2023/AIS_2023_01_15.zip",
    adapter_id="scripts.ingest_real_ais",
    license="Public domain (17 U.S.C. section 105)",
    raw_artifact_path=str(RAW_CSV),
    notes="See docs/datasets/AIS_ACQUISITION_RECORD.md and data/catalog/acquisition/ais.json",
)


# Per the AIS ITU-R M.1371 spec, these are "not available" sentinels, not
# real measurements. NOAA's feed passes them through raw. RawAISPoint has
# no upper-bound constraint (real bug: it silently stored 511 as if it were
# a heading), but the locked AISPoint contract correctly enforces
# `lt=360` for real headings/courses — so the sentinel must be normalized
# to None here, at the parsing boundary, rather than either weakening the
# locked contract's real-world bound or crashing on well-formed real data.
_HEADING_NOT_AVAILABLE = 511.0
_COG_NOT_AVAILABLE = 360.0


def _row_to_point(row: pd.Series) -> RawAISPoint | None:
    try:
        ts = datetime.fromisoformat(row["BaseDateTime"]).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None
    try:
        heading = float(row["Heading"]) if pd.notna(row.get("Heading")) else None
        if heading == _HEADING_NOT_AVAILABLE:
            heading = None
        cog = float(row["COG"]) if pd.notna(row.get("COG")) else None
        if cog is not None and cog >= _COG_NOT_AVAILABLE:
            cog = None
        return RawAISPoint(
            mmsi=str(int(row["MMSI"])),
            timestamp=ts,
            lon=float(row["LON"]),
            lat=float(row["LAT"]),
            sog_knots=float(row["SOG"]) if pd.notna(row.get("SOG")) else None,
            cog_deg=cog,
            heading_deg=heading,
            vessel_type_code=int(row["VesselType"]) if pd.notna(row.get("VesselType")) else None,
            imo=str(row["IMO"]) if pd.notna(row.get("IMO")) and row.get("IMO") else None,
            vessel_name=str(row["VesselName"]) if pd.notna(row.get("VesselName")) else None,
            length_m=float(row["Length"]) if pd.notna(row.get("Length")) else None,
            width_m=float(row["Width"]) if pd.notna(row.get("Width")) else None,
            draught_m=float(row["Draft"]) if pd.notna(row.get("Draft")) else None,
            nav_status=int(row["Status"]) if pd.notna(row.get("Status")) else None,
            source="marinecadastre",
            provenance=PROVENANCE,
        )
    except (ValueError, TypeError):
        return None


def ingest() -> None:
    if not RAW_CSV.exists():
        raise FileNotFoundError(f"{RAW_CSV} not found — run the AIS acquisition first.")
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    in_bbox_rows = 0
    invalid_rows = 0
    unique_mmsi: set[str] = set()
    points_by_mmsi: dict[str, list[RawAISPoint]] = defaultdict(list)

    chunk_iter = pd.read_csv(RAW_CSV, chunksize=200_000, dtype=str, low_memory=False)
    for chunk_no, chunk in enumerate(chunk_iter):
        total_rows += len(chunk)
        chunk = chunk.astype({"LAT": float, "LON": float}, errors="ignore")
        mask = (
            (chunk["LON"].astype(float) >= BBOX["min_lon"]) & (chunk["LON"].astype(float) <= BBOX["max_lon"]) &
            (chunk["LAT"].astype(float) >= BBOX["min_lat"]) & (chunk["LAT"].astype(float) <= BBOX["max_lat"])
        )
        gulf_chunk = chunk[mask]
        in_bbox_rows += len(gulf_chunk)

        for _, row in gulf_chunk.iterrows():
            pt = _row_to_point(row)
            if pt is None:
                invalid_rows += 1
                continue
            unique_mmsi.add(pt.mmsi)
            points_by_mmsi[pt.mmsi].append(pt)

        if chunk_no % 5 == 0:
            print(f"  processed {total_rows:,} rows, {in_bbox_rows:,} in Gulf bbox so far...")

    print(f"Total rows: {total_rows:,}, in Gulf bbox: {in_bbox_rows:,}, "
          f"invalid/unparseable within bbox: {invalid_rows:,}, unique MMSI in bbox: {len(unique_mmsi):,}")

    # Clean per-vessel, using the existing AISCleaner (now bug-fixed: no
    # in-place mutation, VERY_LONG gap boundary preserved, flags scoped
    # per segment).
    cleaner = AISCleaner()
    all_tracks = []
    total_gaps = 0
    gap_class_counts: dict[str, int] = defaultdict(int)
    flagged_tracks = 0
    for mmsi, pts in points_by_mmsi.items():
        tracks = cleaner.clean(pts, mmsi)
        for t in tracks:
            all_tracks.append(t)
            total_gaps += len(t.gaps)
            for g in t.gaps:
                gap_class_counts[g.gap_class.value] += 1
            if t.quality_flags:
                flagged_tracks += 1

    print(f"Tracks after cleaning/segmentation: {len(all_tracks):,}, "
          f"total gaps: {total_gaps:,}, gap classes: {dict(gap_class_counts)}, "
          f"tracks with quality flags: {flagged_tracks:,}")

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_csv": str(RAW_CSV),
        "bbox": BBOX,
        "total_rows_in_file": total_rows,
        "rows_in_bbox": in_bbox_rows,
        "invalid_rows_in_bbox": invalid_rows,
        "unique_mmsi_in_bbox": len(unique_mmsi),
        "tracks_after_cleaning": len(all_tracks),
        "total_gaps": total_gaps,
        "gap_class_counts": dict(gap_class_counts),
        "tracks_with_quality_flags": flagged_tracks,
    }
    (BRONZE_DIR / "gulf_2023-01-15_summary.json").write_text(json.dumps(summary, indent=2))

    tracks_out = [json.loads(t.model_dump_json()) for t in all_tracks]
    (BRONZE_DIR / "gulf_2023-01-15_tracks.json").write_text(json.dumps(tracks_out))

    print(f"Wrote {BRONZE_DIR / 'gulf_2023-01-15_summary.json'}")
    print(f"Wrote {BRONZE_DIR / 'gulf_2023-01-15_tracks.json'} ({len(tracks_out)} tracks)")


if __name__ == "__main__":
    ingest()
