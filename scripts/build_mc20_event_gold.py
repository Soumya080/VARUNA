"""
VARUNA GRID — MC20 Event Gold builder.

Converts the four verified-real MC20 modalities (Sentinel-1 GRD, AIS,
ERA5, CMEMS) into a single versioned, manifest-driven, provenance-
complete Event Gold corpus for inference / E2E validation. NOT a
training dataset -- no oil labels exist for this scene and none are
fabricated here.

Output: data/gold/events/mc20_v0_1/ (refuses to touch it if it already
exists and is non-empty -- a defect found later means mc20_v0_2, never
an in-place edit of v0_1).

Raw sources are never copied wholesale where a reference (path +
checksum) suffices -- see each section below for what is materialized
vs. referenced.

Usage: python scripts/build_mc20_event_gold.py
"""
from __future__ import annotations

# IMPORT ORDER: schema imports before netCDF4 (see
# packages/varuna_data_eng/preprocessing/mc20_forcing_netcdf4.py's module
# docstring -- netCDF4-before-pydantic-schemas hangs indefinitely and
# reproducibly in this environment on Windows).
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

from varuna_contracts import EvidenceMode  # noqa: E402
from varuna_contracts.schemas import BBox  # noqa: E402
from varuna_data_eng.schemas.provenance import DataProvenance, PixelWindow, TileRecord  # noqa: E402
from varuna_data_eng.preprocessing.mc20_forcing_netcdf4 import (  # noqa: E402
    read_cmems_netcdf4, read_era5_netcdf4,
)
from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (  # noqa: E402
    apply_netra_normalization, parse_calibration_lut, tile_512,
)
import varuna_data_eng.preprocessing.sentinel1_grd_calibration as calmod  # noqa: E402

import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import subprocess  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# ---------------------------------------------------------------------------
# Constants -- the locked MC20 case
# ---------------------------------------------------------------------------
CASE_NAME = "MC20 / Taylor Energy"
CASE_ID = "mc20_2023-01-15"
EVENT_VERSION = "mc20_v0_1"
MC20_LAT, MC20_LON = 28.936, -88.970
T_SAR = datetime(2023, 1, 15, 0, 2, 6, 898000, tzinfo=UTC)
AIS_WINDOW_BEFORE_HOURS = 48   # reused from .env.example's real config, not invented
AIS_WINDOW_AFTER_HOURS = 6
WINDOW = 1536                  # same real-validated crop window as the calibration pass

SAFE_DIR = (
    REPO_ROOT / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15"
    / "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE"
)
SAR_PRODUCT_NAME = "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE"
SAR_PRODUCT_UUID = "6fc676ba-b961-5bfc-9211-8076f8f1481c"
SAR_ZIP_SHA256 = "68f5c1f4a35fc64f92f07ee595036d668ef87582bfeaa69b1b8fe86742857d96"

AIS_BRONZE_TRACKS = REPO_ROOT / "data" / "bronze" / "ais" / "mc20_2023-01-15_tracks.json"
AIS_BRONZE_SUMMARY = REPO_ROOT / "data" / "bronze" / "ais" / "mc20_2023-01-15_summary.json"
ERA5_FILE = REPO_ROOT / "data" / "raw" / "era5_mc20" / "era5_mc20_2023-01-11_to_2023-01-17.nc"
CMEMS_FILE = REPO_ROOT / "data" / "raw" / "cmems_mc20_timeseries" / "cmems_mc20_2023-01-11_to_2023-01-17.nc"
GOLD_MANIFEST_V02 = REPO_ROOT / "data" / "manifests" / "netra_gold_v0_2.json"

OUT_ROOT = REPO_ROOT / "data" / "gold" / "events" / EVENT_VERSION

# Non-standard split value, deliberately outside NetraGoldDataset.VALID_SPLITS
# ("train","val","test") -- a structural guard, not just a naming choice; see
# tests/unit/test_mc20_event_gold.py::test_netra_gold_dataset_rejects_this_manifest.
EVENT_SPLIT = "mc20_event_inference"


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
            text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _file_sha256(path: Path, limit_bytes: int = 200 * 1024 * 1024) -> tuple[str | None, str]:
    size = path.stat().st_size
    if size > limit_bytes:
        return None, f"not computed: {size} bytes exceeds {limit_bytes} byte threshold for this build"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest(), "sha256 computed"


# ---------------------------------------------------------------------------
# 1. SAR event tiles
# ---------------------------------------------------------------------------
def build_sar_event() -> dict:
    out_dir = OUT_ROOT / "sar"
    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    vv_ann = SAFE_DIR / "annotation" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
    vh_ann = SAFE_DIR / "annotation" / "s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
    vv_cal = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
    vh_cal = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
    vv_tiff = SAFE_DIR / "measurement" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.tiff"
    vh_tiff = SAFE_DIR / "measurement" / "s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.tiff"

    tree = ET.parse(vv_ann)
    grid_pts = tree.getroot().findall(".//geolocationGridPoint")
    all_lats = [float(p.find("latitude").text) for p in grid_pts]
    all_lons = [float(p.find("longitude").text) for p in grid_pts]
    scene_footprint = BBox(min_lon=min(all_lons), min_lat=min(all_lats),
                            max_lon=max(all_lons), max_lat=max(all_lats))

    def nearest_grid_point(target_line: int, target_pixel: int) -> tuple[float, float]:
        best, best_d2 = None, None
        for p in grid_pts:
            line, pixel = int(p.find("line").text), int(p.find("pixel").text)
            d2 = (line - target_line) ** 2 + (pixel - target_pixel) ** 2
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best = (float(p.find("latitude").text), float(p.find("longitude").text))
        return best

    anchor_best, anchor_d2 = None, None
    for p in grid_pts:
        lat, lon = float(p.find("latitude").text), float(p.find("longitude").text)
        d2 = (lat - MC20_LAT) ** 2 + (lon - MC20_LON) ** 2
        if anchor_d2 is None or d2 < anchor_d2:
            anchor_d2 = d2
            anchor_best = (int(p.find("line").text), int(p.find("pixel").text), lat, lon)
    line, pixel, grid_lat, grid_lon = anchor_best

    im = Image.open(vv_tiff)
    W, H = im.size
    half = WINDOW // 2
    left = max(0, min(pixel - half, W - WINDOW))
    top = max(0, min(line - half, H - WINDOW))

    def read_dn_window(tiff_path: Path) -> np.ndarray:
        im0 = Image.open(tiff_path)
        first_two = im0.tile[:2]
        base_offset = first_two[0].offset
        row_stride = first_two[1].offset - first_two[0].offset
        assert row_stride == W * 2
        out = np.empty((WINDOW, WINDOW), dtype=np.uint16)
        with open(tiff_path, "rb") as f:
            for i, row in enumerate(range(top, top + WINDOW)):
                f.seek(base_offset + row * row_stride + left * 2)
                out[i] = np.frombuffer(f.read(WINDOW * 2), dtype="<u2")
        return out

    vv_dn = read_dn_window(vv_tiff)
    vh_dn = read_dn_window(vh_tiff)

    def calibrate_window(dn_window: np.ndarray, cal_xml: Path) -> np.ndarray:
        lut = parse_calibration_lut(cal_xml)
        shifted_lut = replace(lut, lines=lut.lines - top, pixels=lut.pixels - left)
        sigma_grid = calmod._interpolate_lut_to_grid(shifted_lut, dn_window.shape[0], dn_window.shape[1])
        with np.errstate(divide="ignore", invalid="ignore"):
            sigma0_linear = (dn_window.astype(np.float64) ** 2) / (sigma_grid ** 2)
            db = 10.0 * np.log10(sigma0_linear)
        return np.where(dn_window == 0, np.nan, db).astype(np.float32)

    vv_db = calibrate_window(vv_dn, vv_cal)
    vh_db = calibrate_window(vh_dn, vh_cal)

    gold_manifest = json.loads(GOLD_MANIFEST_V02.read_text())
    norm = gold_manifest["normalization"]
    vv_stats, vh_stats = norm["channels"]["VV"], norm["channels"]["VH"]
    normalization_version = norm["normalization_version"]

    normalized = apply_netra_normalization(vv_db, vh_db, vv_stats, vh_stats)
    tiles = tile_512(normalized, scene_id=CASE_ID)

    tile_records = []
    for t in tiles:
        tile_path = tiles_dir / f"{t.tile_id}.npy"
        np.save(tile_path, t.array)

        # Approximate geo bbox for this tile: nearest real grid points to
        # its 4 corners in scene-pixel space. Sparse (210 points across the
        # whole scene) -- this is an approximation, not bilinear-exact,
        # documented as such. Adequate for an inference/validation corpus,
        # not claimed adequate for sub-pixel geolocation.
        #
        # The 210-point grid is coarser than a single 512px tile (grid
        # spacing >> tile footprint), so all 4 corners routinely snap to
        # the SAME nearest grid point -- a genuine degenerate case, not a
        # bug in the lookup. When that collapses min==max (violating
        # BBox's strict inequality), pad symmetrically by half the tile's
        # own approximate angular footprint (derived from the real scene
        # footprint span / scene pixel dimensions -- not an arbitrary
        # constant), and record that this happened.
        r0, c0 = top + t.row, left + t.col
        r1, c1 = r0 + 512, c0 + 512
        corners = [nearest_grid_point(r0, c0), nearest_grid_point(r0, c1),
                   nearest_grid_point(r1, c0), nearest_grid_point(r1, c1)]
        lats = [c[0] for c in corners]
        lons = [c[1] for c in corners]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        deg_per_px_lon = (scene_footprint.max_lon - scene_footprint.min_lon) / W
        deg_per_px_lat = (scene_footprint.max_lat - scene_footprint.min_lat) / H
        eps_lon, eps_lat = 256 * deg_per_px_lon, 256 * deg_per_px_lat  # half of 512px
        bbox_padded = False
        if min_lon >= max_lon:
            min_lon, max_lon = min_lon - eps_lon, max_lon + eps_lon
            bbox_padded = True
        if min_lat >= max_lat:
            min_lat, max_lat = min_lat - eps_lat, max_lat + eps_lat
            bbox_padded = True
        tile_bbox = BBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)

        rec = TileRecord(
            tile_id=t.tile_id,
            parent_scene_id=CASE_ID,
            split=EVENT_SPLIT,
            sensor="Sentinel-1A_IW_GRDH",
            source="sentinel1_grd_mc20",
            row=t.row, column=t.col,
            pixel_window=PixelWindow(x_offset=c0, y_offset=r0, width=512, height=512),
            bbox=tile_bbox,
            provenance=DataProvenance(
                source_id="sentinel1_grd_mc20",
                adapter_id="scripts.build_mc20_event_gold",
                license="Copernicus Sentinel Data Terms and Conditions (free, open)",
                raw_artifact_path=str(SAFE_DIR),
                notes=(
                    f"calibrated via sentinel1_grd_calibration.py (real, unmodified); "
                    f"normalized with FROZEN {normalization_version}; "
                    f"tile bbox is an approximation from the nearest of 210 sparse "
                    f"geolocationGrid points, not exact bilinear interpolation"
                    + ("; bbox corners collapsed to a single grid point (tile smaller "
                       "than grid spacing) -- padded by half the tile's approximate "
                       "angular footprint" if bbox_padded else "")
                ),
            ),
        )
        tile_records.append(json.loads(rec.model_dump_json()))

    tile_records_path = out_dir / "tile_records.json"
    tile_records_path.write_text(json.dumps(tile_records, indent=2))

    return {
        "product_name": SAR_PRODUCT_NAME,
        "product_uuid": SAR_PRODUCT_UUID,
        "safe_dir": str(SAFE_DIR),
        "zip_sha256": SAR_ZIP_SHA256,
        "acquisition_timestamp": T_SAR.isoformat(),
        "scene_footprint": json.loads(scene_footprint.model_dump_json()),
        "anchor_geolocation_lookup": {"line": line, "pixel": pixel, "lat": grid_lat, "lon": grid_lon,
                                        "distance_from_exact_anchor_km": _haversine_km(MC20_LAT, MC20_LON, grid_lat, grid_lon)},
        "crop_window_px": {"top": top, "left": left, "size": WINDOW},
        "n_tiles": len(tiles),
        "tile_dir": str(tiles_dir),
        "tile_records_path": str(tile_records_path),
        "channels": ["VV", "VH"],
        "normalization_version": normalization_version,
        "vv_db_range": [float(np.nanmin(vv_db)), float(np.nanmax(vv_db))],
        "vh_db_range": [float(np.nanmin(vh_db)), float(np.nanmax(vh_db))],
        "normalized_range": [float(normalized.min()), float(normalized.max())],
        "normalized_has_nan": bool(np.isnan(normalized).any()),
        "normalized_has_inf": bool(np.isinf(normalized).any()),
        "thermal_noise_removed": False,
        "terrain_correction_applied": False,
        "speckle_filter_applied": False,
    }


# ---------------------------------------------------------------------------
# 2. AIS event join
# ---------------------------------------------------------------------------
def build_ais_event(sar_footprint: BBox) -> dict:
    out_dir = OUT_ROOT / "ais"
    out_dir.mkdir(parents=True, exist_ok=True)

    tracks = json.loads(AIS_BRONZE_TRACKS.read_text())
    summary = json.loads(AIS_BRONZE_SUMMARY.read_text())

    win_before = T_SAR.timestamp() - AIS_WINDOW_BEFORE_HOURS * 3600
    win_after = T_SAR.timestamp() + AIS_WINDOW_AFTER_HOURS * 3600

    joined = []
    n_spatial = n_temporal = 0
    global_closest = None       # closest by pure distance, any time (informational only)
    closest_in_window = None    # closest among points that are BOTH spatially in-footprint
                                 # AND inside the temporal window -- the scientifically
                                 # meaningful "nearest AIS relationship" figure

    for tr in tracks:
        in_footprint_pts = [
            p for p in tr["points"]
            if sar_footprint.min_lon <= p["lon"] <= sar_footprint.max_lon
            and sar_footprint.min_lat <= p["lat"] <= sar_footprint.max_lat
        ]
        spatially_matched = len(in_footprint_pts) > 0

        closest_dist_km = None
        closest_time_delta_s = None
        closest_ts = None
        temporally_matched = False
        for p in (in_footprint_pts if spatially_matched else tr["points"]):
            ts = datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00"))
            dist_km = _haversine_km(MC20_LAT, MC20_LON, p["lat"], p["lon"])
            if closest_dist_km is None or dist_km < closest_dist_km:
                closest_dist_km = dist_km
                closest_time_delta_s = ts.timestamp() - T_SAR.timestamp()
                closest_ts = ts.isoformat()
            in_window = win_before <= ts.timestamp() <= win_after
            if spatially_matched and in_window:
                temporally_matched = True
                if closest_in_window is None or dist_km < closest_in_window[0]:
                    closest_in_window = (dist_km, ts.timestamp() - T_SAR.timestamp(),
                                          tr["track_id"], tr["mmsi"], ts.isoformat())

        if spatially_matched:
            n_spatial += 1
        if temporally_matched:
            n_temporal += 1

        abs_delta = abs(closest_time_delta_s) if closest_time_delta_s is not None else None
        if abs_delta is not None and (global_closest is None or (closest_dist_km, abs_delta) < (global_closest[0], global_closest[1])):
            global_closest = (closest_dist_km, abs_delta, tr["track_id"], tr["mmsi"], closest_ts)

        status = "TEMPORALLY_MATCHED" if temporally_matched else (
            "SPATIALLY_MATCHED" if spatially_matched else "TEMPORALLY_UNAVAILABLE"
        )
        joined.append({
            "track_id": tr["track_id"],
            "mmsi": tr["mmsi"],
            "vessel_name": tr.get("vessel_name"),
            "n_points": len(tr["points"]),
            "n_points_in_sar_footprint": len(in_footprint_pts),
            "spatially_matched": spatially_matched,
            "temporally_matched": temporally_matched,
            "status": status,
            "closest_distance_km": closest_dist_km,
            "closest_point_timestamp": closest_ts,
            "closest_time_delta_seconds": closest_time_delta_s,
        })

    closest_in_window_dict = {
        "distance_km": closest_in_window[0], "time_delta_seconds": closest_in_window[1],
        "track_id": closest_in_window[2], "mmsi": closest_in_window[3], "timestamp": closest_in_window[4],
    } if closest_in_window else None

    join_path = out_dir / "event_ais_join.json"
    join_path.write_text(json.dumps({
        "generated_at": datetime.now(UTC).isoformat(),
        "sar_footprint": json.loads(sar_footprint.model_dump_json()),
        "t_sar": T_SAR.isoformat(),
        "window_before_hours": AIS_WINDOW_BEFORE_HOURS,
        "window_after_hours": AIS_WINDOW_AFTER_HOURS,
        "n_tracks_total": len(tracks),
        "n_tracks_spatially_matched": n_spatial,
        "n_tracks_temporally_matched": n_temporal,
        "n_tracks_temporally_unavailable": len(tracks) - n_temporal,
        "closest_temporally_matched": closest_in_window_dict,
        "raw_source_reference": {
            "bronze_tracks_path": str(AIS_BRONZE_TRACKS),
            "bronze_summary_path": str(AIS_BRONZE_SUMMARY),
            "raw_csv_path": summary["source_csv"],
            "note": "referenced, not copied -- see README for why",
        },
        "tracks": joined,
    }, indent=2))

    return {
        "join_path": str(join_path),
        "n_tracks_total": len(tracks),
        "n_tracks_spatially_matched": n_spatial,
        "n_tracks_temporally_matched": n_temporal,
        "global_closest": {
            "distance_km": global_closest[0], "time_delta_seconds": global_closest[1],
            "track_id": global_closest[2], "mmsi": global_closest[3], "timestamp": global_closest[4],
        } if global_closest else None,
        "closest_temporally_matched": closest_in_window_dict,
        "raw_records_total": summary["rows_in_bbox"],
        "unique_vessels": summary["unique_mmsi_in_bbox"],
    }


# ---------------------------------------------------------------------------
# 3 & 4. Forcing (ERA5 + CMEMS)
# ---------------------------------------------------------------------------
def build_forcing_event() -> dict:
    out_dir = OUT_ROOT / "forcing"
    out_dir.mkdir(parents=True, exist_ok=True)

    era5_cube = read_era5_netcdf4(ERA5_FILE)
    cmems_cube = read_cmems_netcdf4(CMEMS_FILE)

    era5_path = out_dir / "era5_cube.json"
    cmems_path = out_dir / "cmems_cube.json"
    era5_path.write_text(era5_cube.model_dump_json(indent=2))
    cmems_path.write_text(cmems_cube.model_dump_json(indent=2))

    def contains(cube, lat, lon) -> bool:
        return cube.bbox.min_lat <= lat <= cube.bbox.max_lat and cube.bbox.min_lon <= lon <= cube.bbox.max_lon

    def contains_time(cube, t: datetime) -> bool:
        return cube.time_range[0] <= t <= cube.time_range[1]

    return {
        "era5_cube_path": str(era5_path),
        "cmems_cube_path": str(cmems_path),
        "era5": {
            "n_timesteps": len(era5_cube.time_coords),
            "time_series_status": era5_cube.time_series_status.value,
            "bbox": json.loads(era5_cube.bbox.model_dump_json()),
            "time_range": [era5_cube.time_range[0].isoformat(), era5_cube.time_range[1].isoformat()],
            "contains_sar_point": contains(era5_cube, MC20_LAT, MC20_LON),
            "contains_t_sar": contains_time(era5_cube, T_SAR),
            "file_checksum": era5_cube.file_checksum,
        },
        "cmems": {
            "n_timesteps": len(cmems_cube.time_coords),
            "time_series_status": cmems_cube.time_series_status.value,
            "bbox": json.loads(cmems_cube.bbox.model_dump_json()),
            "time_range": [cmems_cube.time_range[0].isoformat(), cmems_cube.time_range[1].isoformat()],
            "contains_sar_point": contains(cmems_cube, MC20_LAT, MC20_LON),
            "contains_t_sar": contains_time(cmems_cube, T_SAR),
            "file_checksum": cmems_cube.file_checksum,
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if OUT_ROOT.exists() and any(OUT_ROOT.iterdir()):
        raise SystemExit(
            f"STOPPED: {OUT_ROOT} already exists and is non-empty. Event Gold is "
            f"immutable once built -- create mc20_v0_2 instead of overwriting this."
        )

    print(f"Building MC20 Event Gold at {OUT_ROOT}")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    for sub in ("metadata", "provenance", "diagnostics", "validation"):
        (OUT_ROOT / sub).mkdir(exist_ok=True)

    sar_result = build_sar_event()
    print(f"  SAR: {sar_result['n_tiles']} tiles, dB range VV{sar_result['vv_db_range']} VH{sar_result['vh_db_range']}")

    sar_footprint = BBox(**sar_result["scene_footprint"])
    ais_result = build_ais_event(sar_footprint)
    print(f"  AIS: {ais_result['n_tracks_spatially_matched']}/{ais_result['n_tracks_total']} spatially matched, "
          f"{ais_result['n_tracks_temporally_matched']} temporally matched")

    forcing_result = build_forcing_event()
    print(f"  ERA5: {forcing_result['era5']['n_timesteps']} steps, contains_t_sar={forcing_result['era5']['contains_t_sar']}")
    print(f"  CMEMS: {forcing_result['cmems']['n_timesteps']} steps, contains_t_sar={forcing_result['cmems']['contains_t_sar']}")

    # --- metadata ---
    metadata = {
        "event_id": CASE_ID,
        "case_name": CASE_NAME,
        "dataset_version": EVENT_VERSION,
        "anchor": {"lat": MC20_LAT, "lon": MC20_LON},
        "t_sar": T_SAR.isoformat(),
        "creation_timestamp": datetime.now(UTC).isoformat(),
        "processing_git_commit": _git_commit(),
        "purpose": "inference and E2E validation -- NOT a training dataset, no oil labels",
    }
    (OUT_ROOT / "metadata" / "event_metadata.json").write_text(json.dumps(metadata, indent=2))

    # --- diagnostics / alignment ---
    four_way = (
        ais_result["n_tracks_spatially_matched"] > 0
        and forcing_result["era5"]["contains_sar_point"]
        and forcing_result["cmems"]["contains_sar_point"]
    )
    alignment = {
        "spatial": {
            "sar_footprint": sar_result["scene_footprint"],
            "sar_ais": {"n_spatially_matched_tracks": ais_result["n_tracks_spatially_matched"],
                        "n_total_tracks": ais_result["n_tracks_total"]},
            "sar_era5_contains_anchor": forcing_result["era5"]["contains_sar_point"],
            "sar_cmems_contains_anchor": forcing_result["cmems"]["contains_sar_point"],
            "four_way_non_empty": four_way,
        },
        "temporal": {
            "t_sar": T_SAR.isoformat(),
            "ais_closest_by_pure_distance": ais_result["global_closest"],
            "ais_closest_temporally_matched": ais_result["closest_temporally_matched"],
            "ais_closest_note": (
                "closest_by_pure_distance is the nearest AIS point regardless of time -- "
                "informational only. closest_temporally_matched is the nearest point that "
                "is ALSO within the AIS join window -- this is the scientifically relevant "
                "figure, and matches the prior data-track report's finding "
                "(MMSI 368181750, 3.26km, +16m57s)."
            ),
            "era5_contains_t_sar": forcing_result["era5"]["contains_t_sar"],
            "cmems_contains_t_sar": forcing_result["cmems"]["contains_t_sar"],
        },
    }
    (OUT_ROOT / "diagnostics" / "alignment.json").write_text(json.dumps(alignment, indent=2))

    # --- provenance ---
    provenance = {
        "sar": {"product_uuid": sar_result["product_uuid"], "zip_sha256": sar_result["zip_sha256"],
                "raw_path": sar_result["safe_dir"]},
        "ais": {"raw_source_reference": json.loads((OUT_ROOT / "ais" / "event_ais_join.json").read_text())["raw_source_reference"]},
        "era5": {"cube_path": forcing_result["era5_cube_path"], "file_checksum": forcing_result["era5"]["file_checksum"],
                  "raw_path": str(ERA5_FILE)},
        "cmems": {"cube_path": forcing_result["cmems_cube_path"], "file_checksum": forcing_result["cmems"]["file_checksum"],
                   "raw_path": str(CMEMS_FILE)},
        "processing_git_commit": metadata["processing_git_commit"],
        "raw_data_immutability": "all raw sources referenced by path+checksum; none copied except where noted; none modified",
    }
    (OUT_ROOT / "provenance" / "provenance.json").write_text(json.dumps(provenance, indent=2))

    # --- validation ---
    validation = {
        "sar_tiles": {
            "n_tiles": sar_result["n_tiles"], "shape_expected": [2, 512, 512],
            "normalized_has_nan": sar_result["normalized_has_nan"],
            "normalized_has_inf": sar_result["normalized_has_inf"],
            "normalized_range": sar_result["normalized_range"],
        },
        "ais": {
            "n_tracks_total": ais_result["n_tracks_total"],
            "n_tracks_spatially_matched": ais_result["n_tracks_spatially_matched"],
            "n_tracks_temporally_matched": ais_result["n_tracks_temporally_matched"],
        },
        "forcing": forcing_result,
    }
    (OUT_ROOT / "validation" / "validation_report.json").write_text(json.dumps(validation, indent=2))

    # --- top-level manifest ---
    manifest = {
        "event_id": CASE_ID,
        "case_name": CASE_NAME,
        "dataset_version": EVENT_VERSION,
        "creation_timestamp": metadata["creation_timestamp"],
        "processing_git_commit": metadata["processing_git_commit"],
        "modalities": {
            "sar": {
                "source": "sentinel1_grd_mc20", "product_id": sar_result["product_uuid"],
                "source_checksum": sar_result["zip_sha256"],
                "timestamp": sar_result["acquisition_timestamp"], "timestamp_status": "AVAILABLE",
                "bbox": sar_result["scene_footprint"], "crs": "EPSG:4326",
                "resolution": "IW GRD, ~10m ground range sample spacing (native product)",
                "variables": ["VV", "VH"], "channels": 2,
                "preprocessing_version": "sentinel1_grd_calibration.py (unmodified)",
                "normalization_version": sar_result["normalization_version"],
                "evidence_mode": EvidenceMode.REAL.value,
                "quality_status": "REAL, validated against real SAFE product",
                "parent_source": sar_result["safe_dir"],
            },
            "ais": {
                "source": "ais.marinecadastre.2023-01-15", "product_id": "AIS_2023_01_15",
                "source_checksum": None,
                "timestamp": "2023-01-15 (full day)", "timestamp_status": "AVAILABLE",
                "bbox": None, "crs": "EPSG:4326",
                "variables": ["mmsi", "lat", "lon", "sog", "cog", "heading", "timestamp"],
                "evidence_mode": EvidenceMode.REAL.value,
                "quality_status": f"REAL, {ais_result['n_tracks_total']} tracks, "
                                  f"{ais_result['n_tracks_spatially_matched']} spatially matched",
                "parent_source": str(AIS_BRONZE_TRACKS),
            },
            "era5": {
                "source": "era5.real.mc20", "product_id": "reanalysis-era5-single-levels:10m_wind",
                "source_checksum": forcing_result["era5"]["file_checksum"],
                "timestamp": forcing_result["era5"]["time_range"], "timestamp_status": "AVAILABLE",
                "bbox": forcing_result["era5"]["bbox"], "crs": "EPSG:4326",
                "variables": ["u10", "v10"],
                "evidence_mode": EvidenceMode.REAL.value,
                "quality_status": f"REAL, {forcing_result['era5']['n_timesteps']} timesteps, "
                                  f"time_series_status={forcing_result['era5']['time_series_status']}",
                "parent_source": str(ERA5_FILE),
            },
            "cmems": {
                "source": "cmems.real.mc20", "product_id": "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
                "source_checksum": forcing_result["cmems"]["file_checksum"],
                "timestamp": forcing_result["cmems"]["time_range"], "timestamp_status": "AVAILABLE",
                "bbox": forcing_result["cmems"]["bbox"], "crs": "EPSG:4326",
                "variables": ["uo", "vo"],
                "evidence_mode": EvidenceMode.REAL.value,
                "quality_status": f"REAL, {forcing_result['cmems']['n_timesteps']} timesteps, "
                                  f"time_series_status={forcing_result['cmems']['time_series_status']}",
                "parent_source": str(CMEMS_FILE),
            },
        },
        "spatial_alignment": alignment["spatial"],
        "temporal_alignment": alignment["temporal"],
        "paths": {
            "sar_tiles_dir": sar_result["tile_dir"],
            "sar_tile_records": sar_result["tile_records_path"],
            "ais_event_join": ais_result["join_path"],
            "era5_cube": forcing_result["era5_cube_path"],
            "cmems_cube": forcing_result["cmems_cube_path"],
            "metadata": str(OUT_ROOT / "metadata" / "event_metadata.json"),
            "provenance": str(OUT_ROOT / "provenance" / "provenance.json"),
            "diagnostics": str(OUT_ROOT / "diagnostics" / "alignment.json"),
            "validation": str(OUT_ROOT / "validation" / "validation_report.json"),
        },
        "netra_training_isolation": {
            "split_value": EVENT_SPLIT,
            "note": "deliberately outside NetraGoldDataset.VALID_SPLITS; not referenced by any NETRA manifest",
        },
        "locked_evaluation_isolation": {
            "zenodo_part3_used": False, "essd_used": False,
        },
        "purpose": metadata["purpose"],
    }
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote manifest: {OUT_ROOT / 'manifest.json'}")


if __name__ == "__main__":
    main()
