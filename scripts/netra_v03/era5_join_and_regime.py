"""Phase 6-7: join each of the 25 ESSD/PANGAEA scenes to real ERA5 wind at
its exact acquisition timestamp and footprint, classify wind regime, and
cross-tab regime x label.

Thresholding policy (documented, not invented ad hoc): reuses the same
low/medium/high-wind convention already established for MC20 in the
Smart-Fix investigation, where MC20's 4.63 m/s was independently
characterized as "calm" (15th percentile of its local week). Absent a
universal physical standard, this task adopts the commonly used
oceanographic Beaufort-derived bins for open water:
    low-wind:    < 5 m/s   (Beaufort <= 2, "calm/light air/light breeze")
    medium-wind: 5-10 m/s  (Beaufort 3-5)
    high-wind:   > 10 m/s  (Beaufort >= 6)
This is a documented dataset-analysis convention for this report, not a
universal physical law -- recorded explicitly per Phase 6's requirement.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4 as nc
import numpy as np

REPO = Path(__file__).resolve().parents[2]
PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"
ERA5_FILE = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "era5_eastern_med_2019.nc"

LOW_WIND_MAX = 5.0
HIGH_WIND_MIN = 10.0


def classify(wind_ms: float | None) -> str:
    if wind_ms is None:
        return "unknown"
    if wind_ms < LOW_WIND_MAX:
        return "low-wind"
    if wind_ms >= HIGH_WIND_MIN:
        return "high-wind"
    return "medium-wind"


def main():
    with open(PROV_DIR / "minimum_useful_scene_set.json") as f:
        sel = json.load(f)
    scenes = [(s, "oil") for s in sel["oil_scenes"]] + [(s, "negative") for s in sel["negative_lookalike_scenes"]]

    ds = nc.Dataset(ERA5_FILE)
    valid_time = ds.variables["valid_time"][:]  # seconds since epoch (era5 cds default)
    time_units = ds.variables["valid_time"].units
    lats = ds.variables["latitude"][:]
    lons = ds.variables["longitude"][:]
    u10 = ds.variables["u10"][:]  # (time, lat, lon)
    v10 = ds.variables["v10"][:]

    # decode valid_time to python datetimes
    base_str = time_units.split("since")[1].strip()
    base = datetime.fromisoformat(base_str.replace("Z", "").split("+")[0].strip())
    times = [base + timedelta(seconds=int(t)) for t in valid_time]

    results = []
    for s, label in scenes:
        sid = s["sentinel_product_id"]
        t0 = s["start_times_distinct"][0]
        t_scene = datetime.fromisoformat(t0)
        lon_c = (s["lon_range"][0] + s["lon_range"][1]) / 2 if s.get("lon_range") else None
        lat_c = (s["lat_range"][0] + s["lat_range"][1]) / 2 if s.get("lat_range") else None

        # nearest ERA5 hour
        diffs = [abs((t - t_scene).total_seconds()) for t in times]
        idx = int(np.argmin(diffs))
        offset_s = diffs[idx]

        wind = None
        if lon_c is not None and lat_c is not None:
            lat_i = int(np.argmin(np.abs(lats - lat_c)))
            lon_i = int(np.argmin(np.abs(lons - lon_c)))
            u = float(u10[idx, lat_i, lon_i])
            v = float(v10[idx, lat_i, lon_i])
            wind = float(np.sqrt(u**2 + v**2))

        regime = classify(wind)
        results.append({
            "sentinel_product_id": sid,
            "label": label,
            "scene_start_time": t0,
            "era5_matched_time": times[idx].isoformat(),
            "temporal_offset_seconds": offset_s,
            "lon_center": lon_c,
            "lat_center": lat_c,
            "wind_speed_ms": wind,
            "wind_regime": regime,
            "oil_patch_rows": s.get("oil_patch_rows", 0),
            "no_oil_patch_rows": s.get("no_oil_patch_rows", 0),
        })

    with open(PROV_DIR / "era5_regime_join.json", "w") as f:
        json.dump(results, f, indent=2)

    # cross-tab
    from collections import Counter
    tab = Counter((r["wind_regime"], r["label"]) for r in results)
    print("threshold policy: low<5.0 m/s, medium 5.0-10.0, high>=10.0 (documented Beaufort-derived bins)")
    for regime in ["low-wind", "medium-wind", "high-wind", "unknown"]:
        for label in ["oil", "negative"]:
            print(f"{regime:12s} + {label:10s}: {tab.get((regime, label), 0)} scenes")

    with open(PROV_DIR / "regime_crosstab.json", "w") as f:
        json.dump({f"{k[0]}__{k[1]}": v for k, v in tab.items()}, f, indent=2)


if __name__ == "__main__":
    main()
