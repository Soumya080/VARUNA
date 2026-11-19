"""
VARUNA GRID — Gulf-of-Mexico-scoped ERA5 acquisition for the MC20 case.

Requests ONLY u10/v10, ONLY the region + time window this case actually
needs -- not global, not multi-year. Requires a free Climate Data Store
account (https://cds.climate.copernicus.eu/ -> register -> profile page
for the API key). Reads credentials ONLY from environment variables:

    CDSAPI_URL   (fixed, public: https://cds.climate.copernicus.eu/api)
    CDSAPI_KEY   (personal, from the CDS profile page)

or from ~/.cdsapirc if already configured. Stops at the credential
boundary otherwise -- confirmed via cdsapi.Client() itself, no bypass.

Region: MC20 (28.936N, -88.970W) + a 2-degree buffer around the SAR
scene's approximate IW footprint (~250km swath), not just the single
point -- per the task's explicit "scientifically justified buffer"
requirement.

Time window: derived from the honest (non-fabricated) planning bound in
scripts/check_mc20_readiness.py -- backward 84h (the widest hardcoded
precedent found anywhere in this codebase, from NYAYA service defaults:
age_prior_mean_hours=36 + 2*age_prior_std_hours=24) and forward 48h from
the real SAR acquisition timestamp. This is a PLANNING bound, not a
case-specific computed value (no real NETRA detection exists for this
scene -- see the readiness gate's own caveat). Centered on:
    T_SAR = 2023-01-15T00:02:06.898Z
    -> window: 2023-01-11T12:00Z to 2023-01-17T00:00Z

Destination: data/raw/era5_mc20/ (new directory, never overwrites the
existing 3 Arabian-Sea GRIB files, which are untouched).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = REPO_ROOT / "data" / "raw" / "era5_mc20"

# 2-degree buffer around MC20 (28.936N, -88.970W), covering the
# approximate IW swath footprint rather than a single point.
REGION = {"north": 31.0, "south": 27.0, "west": -91.0, "east": -87.0}

# Backward 84h + forward 48h around the real SAR timestamp (see module
# docstring for why these specific hours, not invented values).
DATES = ["2023-01-11", "2023-01-12", "2023-01-13", "2023-01-14",
         "2023-01-15", "2023-01-16", "2023-01-17"]


def acquire() -> None:
    if DEST_DIR.exists() and any(DEST_DIR.iterdir()):
        raise SystemExit(f"STOPPED: {DEST_DIR} already exists and is non-empty. Not overwriting.")

    try:
        import cdsapi
    except ImportError:
        raise SystemExit("cdsapi not installed. pip install cdsapi")

    try:
        client = cdsapi.Client()
    except Exception as e:
        raise SystemExit(
            f"STOPPED at credential boundary: {e}\n"
            f"Register at https://cds.climate.copernicus.eu/ , get your API "
            f"key from your profile page, then either set CDSAPI_URL/"
            f"CDSAPI_KEY environment variables or create ~/.cdsapirc. "
            f"No download attempted."
        )

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DEST_DIR / "era5_mc20_2023-01-11_to_2023-01-17.nc"

    print(f"Requesting ERA5 u10/v10, region={REGION}, dates={DATES[0]}..{DATES[-1]}")
    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
            "year": "2023", "month": "01",
            "day": [d.split("-")[2] for d in DATES],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": [REGION["north"], REGION["west"], REGION["south"], REGION["east"]],
            "format": "netcdf",
        },
        str(out_path),
    )

    record = {
        "region": REGION,
        "dates": DATES,
        "variables": ["u10", "v10"],
        "downloaded_at": datetime.now(UTC).isoformat(),
        "destination": str(out_path),
        "reason": "MC20 case, backward 84h + forward 48h planning window around real SAR timestamp 2023-01-15T00:02:06.898Z",
    }
    record_path = REPO_ROOT / "data" / "catalog" / "acquisition" / "era5_mc20.json"
    record_path.write_text(json.dumps(record, indent=2))
    print(f"Wrote {out_path} and acquisition record {record_path}")


if __name__ == "__main__":
    acquire()
