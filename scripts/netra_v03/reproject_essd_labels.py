"""Phase 1 of this turn: reproject every PANGAEA oil-object annotation
from lon/lat (already given per-row in the PANGAEA data table) into the
corresponding raw Sentinel-1 GRD scene's own line/pixel coordinate
system, using that scene's real geolocationGridPoint metadata (210
points per polarization annotation XML, standard Sentinel-1 product
format).

Method: build a local linear inverse-interpolator (lon,lat) -> (line,
pixel) per scene from its own 210 real grid points (scipy griddata,
linear), then evaluate it at each object's four real corner lon/lats
already recorded in the PANGAEA table. This does NOT go through the
640x640 packaged-patch pixel space at all -- it uses the same real
geodetic corners PANGAEA already published, which is a more direct and
verifiable route than re-deriving the original patch-generation affine
transform (undocumented).

No-oil/negative rows have no per-object corners (only patch corners) --
handled by mapping the patch's own four corners instead, since there is
no finer geometry to reproject for that class.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from scipy.interpolate import griddata

REPO = Path(__file__).resolve().parents[2]
EXTRACTED = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "extracted"
PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"
TABLE = PROV_DIR / "pangaea_980773_table.tab"


def load_geolocation_grid(scene_dir: Path, pol: str = "vv") -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Returns (lons, lats, lines, pixels) arrays, one entry per real
    geolocationGridPoint parsed from the scene's own annotation XML."""
    ann = list((scene_dir / "annotation").glob(f"*-{pol}-*.xml"))
    ann = [a for a in ann if "calibration" not in str(a) and "support" not in str(a)]
    if not ann:
        raise FileNotFoundError(f"no {pol} annotation xml in {scene_dir}")
    tree = ET.parse(ann[0])
    root = tree.getroot()
    pts = root.findall(".//geolocationGridPoint")
    if not pts:
        raise ValueError(f"no geolocationGridPoint in {ann[0]}")
    lons, lats, lines, pixels = [], [], [], []
    for p in pts:
        lons.append(float(p.find("longitude").text))
        lats.append(float(p.find("latitude").text))
        lines.append(int(p.find("line").text))
        pixels.append(int(p.find("pixel").text))
    return np.array(lons), np.array(lats), np.array(lines), np.array(pixels)


def build_inverse_interpolator(lons, lats, lines, pixels):
    points = np.stack([lons, lats], axis=-1)

    def inverse(query_lon, query_lat):
        q = np.array([[query_lon, query_lat]])
        line = griddata(points, lines, q, method="linear")
        pixel = griddata(points, pixels, q, method="linear")
        if np.isnan(line) or np.isnan(pixel):
            line = griddata(points, lines, q, method="nearest")
            pixel = griddata(points, pixels, q, method="nearest")
        return float(line[0]), float(pixel[0])

    return inverse


def load_table_rows():
    with open(TABLE, encoding="utf-8") as f:
        lines_ = f.readlines()
    hdr_idx = next(i for i, l in enumerate(lines_) if l.startswith("Image set"))
    header = lines_[hdr_idx].rstrip("\n").split("\t")
    rows = []
    for l in lines_[hdr_idx + 1:]:
        l = l.rstrip("\n")
        if not l.strip():
            continue
        parts = l.split("\t")
        parts += [""] * (len(header) - len(parts))
        rows.append(dict(zip(header, parts)))
    return rows, header


def fnum(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def main():
    with open(PROV_DIR / "minimum_useful_scene_set.json") as f:
        sel = json.load(f)
    selected_ids = {s["sentinel_product_id"] for s in sel["oil_scenes"] + sel["negative_lookalike_scenes"]}

    rows, header = load_table_rows()
    subset_col = header[0]

    scene_dirs = {Path(p).name: Path(p) for p in glob.glob(str(EXTRACTED / "*.SAFE"))}

    results = []
    skipped_geom_fail = 0
    interpolators = {}

    for r in rows:
        sid = r["ID (Sentinel_ID)"]
        if sid not in selected_ids:
            continue
        scene_dir = scene_dirs.get(sid)
        if scene_dir is None:
            continue

        if sid not in interpolators:
            lons, lats, lines_, pixels_ = load_geolocation_grid(scene_dir, "vv")
            interpolators[sid] = build_inverse_interpolator(lons, lats, lines_, pixels_)
        inv = interpolators[sid]

        subset = r[subset_col]
        is_oil = subset in ("oc", "ow")
        label = "oil" if is_oil else "negative_lookalike"

        if is_oil:
            corner_keys = [
                ("obj_ul_lon", "obj_ul_lat"), ("obj_ur_lon", "obj_ur_lat"),
                ("obj_br_lon", "obj_br_lat"), ("obj_bl_lon", "obj_bl_lat"),
            ]
        else:
            corner_keys = [
                ("patch_ul_lon", "patch_ul_lat"), ("patch_ur_lon", "patch_ur_lat"),
                ("patch_br_lon", "patch_br_lat"), ("patch_bl_lon", "patch_bl_lat"),
            ]

        corners_raw = []
        ok = True
        for lon_k, lat_k in corner_keys:
            lon = fnum(r.get(f"Longitude ({lon_k})", ""))
            lat = fnum(r.get(f"Latitude ({lat_k})", ""))
            if lon is None or lat is None:
                ok = False
                break
            line, pixel = inv(lon, lat)
            corners_raw.append({"lon": lon, "lat": lat, "line": line, "pixel": pixel})
        if not ok:
            skipped_geom_fail += 1
            continue

        lines_vals = [c["line"] for c in corners_raw]
        pixels_vals = [c["pixel"] for c in corners_raw]
        results.append({
            "tag": r["ID (tag)"],
            "sentinel_product_id": sid,
            "label": label,
            "corners_lonlat_and_raw_pixel": corners_raw,
            "raw_bbox_line_min_max": [min(lines_vals), max(lines_vals)],
            "raw_bbox_pixel_min_max": [min(pixels_vals), max(pixels_vals)],
        })

    with open(PROV_DIR / "reprojected_labels.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"reprojected {len(results)} label rows across {len(interpolators)} scenes")
    print(f"skipped (missing geometry fields): {skipped_geom_fail}")
    n_oil = sum(1 for r in results if r["label"] == "oil")
    n_neg = sum(1 for r in results if r["label"] == "negative_lookalike")
    print(f"oil rows: {n_oil}, negative/lookalike rows: {n_neg}")


if __name__ == "__main__":
    main()
