"""Fetch real ERA5 u10/v10 for the exact 23 dates needed by the 25 selected
ESSD/PANGAEA GRD scenes, over the Eastern Mediterranean bbox stated in the
PANGAEA record. Uses CDSAPI_URL/CDSAPI_KEY from environment (loaded from
.env by the caller). New file only -- does not touch existing
data/raw/era5/ or data/raw/era5_mc20/.
"""
from __future__ import annotations

import json
from pathlib import Path

import cdsapi

REPO = Path(__file__).resolve().parents[2]
PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"
OUT = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "era5_eastern_med_2019.nc"

with open(PROV_DIR / "era5_needed_dates.json") as f:
    dates = json.load(f)

years = sorted({d[:4] for d in dates})
months = sorted({d[5:7] for d in dates})
days = sorted({d[8:10] for d in dates})

# PANGAEA-stated bbox (look-alike extent, the larger of the two stated
# extents, so it safely covers every selected scene's footprint):
# 27.1212703E-36.0881997E, 29.2991798N-36.3715771N
NORTH, WEST, SOUTH, EAST = 36.5, 27.0, 29.0, 36.5

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = cdsapi.Client()
    c.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
            "year": years,
            "month": months,
            "day": days,
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": [NORTH, WEST, SOUTH, EAST],
            "format": "netcdf",
        },
        str(OUT),
    )
    print("saved:", OUT, OUT.stat().st_size, "bytes")
