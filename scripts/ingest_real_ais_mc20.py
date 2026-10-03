"""
VARUNA GRID — Real AIS re-extraction for the MC20 (Taylor Energy) candidate
event region, reusing the ALREADY-DOWNLOADED national AIS file for
2023-01-15 (no new download; data/raw/ais/2023-01-15/AIS_2023_01_15.csv
is read-only here, exactly as in scripts/ingest_real_ais.py).

MC20 site: 28.936N, -88.970E (Mississippi Canyon Block 20, the
persistent/chronic oil-slick site documented in NOAA/BSEE monitoring and
in published Sentinel-1 oil-detection literature — see
docs/datasets/FIRST_REAL_E2E_CASE_FINAL.md for the full citation trail).

This produces a SEPARATE bronze output from the existing
gulf_2023-01-15_{summary,tracks}.json (which covers a different bbox, the
Bay of Campeche anchor from the earlier pass) — that file is not touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datetime import UTC

import ingest_real_ais as base

# ~1 degree pad around the real MC20 coordinates (28.936N, -88.970E) --
# tighter than the earlier Gulf bbox since this is anchored to one precise
# site, not a broad anchor-scene footprint.
base.BBOX = {"min_lon": -90.0, "max_lon": -88.0, "min_lat": 28.0, "max_lat": 30.0}

BRONZE_DIR = base.REPO_ROOT / "data" / "bronze" / "ais"


def main() -> None:
    orig_ingest = base.ingest

    # Monkeypatch the two output filenames so this run does not overwrite
    # the earlier gulf_2023-01-15_* bronze outputs (different bbox, same
    # source date).
    import json
    from collections import defaultdict
    from datetime import datetime

    import pandas as pd

    if not base.RAW_CSV.exists():
        raise FileNotFoundError(f"{base.RAW_CSV} not found — this reuses the already-acquired file.")
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    in_bbox_rows = 0
    invalid_rows = 0
    unique_mmsi: set[str] = set()
    points_by_mmsi: dict[str, list] = defaultdict(list)

    chunk_iter = pd.read_csv(base.RAW_CSV, chunksize=200_000, dtype=str, low_memory=False)
    for chunk_no, chunk in enumerate(chunk_iter):
        total_rows += len(chunk)
        chunk = chunk.astype({"LAT": float, "LON": float}, errors="ignore")
        mask = (
            (chunk["LON"].astype(float) >= base.BBOX["min_lon"]) & (chunk["LON"].astype(float) <= base.BBOX["max_lon"]) &
            (chunk["LAT"].astype(float) >= base.BBOX["min_lat"]) & (chunk["LAT"].astype(float) <= base.BBOX["max_lat"])
        )
        region_chunk = chunk[mask]
        in_bbox_rows += len(region_chunk)
        for _, row in region_chunk.iterrows():
            pt = base._row_to_point(row)
            if pt is None:
                invalid_rows += 1
                continue
            unique_mmsi.add(pt.mmsi)
            points_by_mmsi[pt.mmsi].append(pt)
        if chunk_no % 5 == 0:
            print(f"  processed {total_rows:,} rows, {in_bbox_rows:,} in MC20 bbox so far...")

    print(f"Total rows: {total_rows:,}, in MC20 bbox: {in_bbox_rows:,}, "
          f"invalid: {invalid_rows:,}, unique MMSI: {len(unique_mmsi):,}")

    from varuna_data_eng.preprocessing.ais_cleaner import AISCleaner
    cleaner = AISCleaner()
    all_tracks = []
    total_gaps = 0
    gap_class_counts: dict[str, int] = defaultdict(int)
    for mmsi, pts in points_by_mmsi.items():
        tracks = cleaner.clean(pts, mmsi)
        for t in tracks:
            all_tracks.append(t)
            total_gaps += len(t.gaps)
            for g in t.gaps:
                gap_class_counts[g.gap_class.value] += 1

    print(f"Tracks after cleaning: {len(all_tracks):,}, total gaps: {total_gaps:,}, "
          f"gap classes: {dict(gap_class_counts)}")

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_csv": str(base.RAW_CSV),
        "bbox": base.BBOX,
        "anchor_site": "MC20 / Taylor Energy, 28.936N -88.970W",
        "total_rows_in_file": total_rows,
        "rows_in_bbox": in_bbox_rows,
        "invalid_rows_in_bbox": invalid_rows,
        "unique_mmsi_in_bbox": len(unique_mmsi),
        "tracks_after_cleaning": len(all_tracks),
        "total_gaps": total_gaps,
        "gap_class_counts": dict(gap_class_counts),
    }
    (BRONZE_DIR / "mc20_2023-01-15_summary.json").write_text(json.dumps(summary, indent=2))
    tracks_out = [json.loads(t.model_dump_json()) for t in all_tracks]
    (BRONZE_DIR / "mc20_2023-01-15_tracks.json").write_text(json.dumps(tracks_out))
    print(f"Wrote {BRONZE_DIR / 'mc20_2023-01-15_summary.json'}")
    print(f"Wrote {BRONZE_DIR / 'mc20_2023-01-15_tracks.json'} ({len(tracks_out)} tracks)")


if __name__ == "__main__":
    main()
