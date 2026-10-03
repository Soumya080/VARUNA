"""
VARUNA GRID — MC20-vicinity CMEMS time-series acquisition.

Product per docs/datasets/CMEMS_ACQUISITION_READY.md's already-specified
method (continuity with the existing single-timestep snapshot, same
product family): cmems_mod_glo_phy_anfc_0.083deg_PT1H-m, uo/vo only.

Requires a free Copernicus Marine account (https://marine.copernicus.eu/
-> register). Reads credentials ONLY from environment variables:

    COPERNICUSMARINE_SERVICE_USERNAME
    COPERNICUSMARINE_SERVICE_PASSWORD

Stops at the credential boundary otherwise (confirmed via
copernicusmarine.login(check_credentials_valid=True), no bypass).

Region: MC20 + 2-degree buffer (same as the ERA5 request, for spatial
consistency between forcing sources). Time: same 84h backward / 48h
forward planning window around the real SAR timestamp (see
scripts/acquire_mc20_era5.py's docstring for why these specific hours).

Destination: data/raw/cmems_mc20_timeseries/ (new directory; the
existing single-timestep global snapshots are untouched).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = REPO_ROOT / "data" / "raw" / "cmems_mc20_timeseries"

REGION = {"min_lon": -91.0, "max_lon": -87.0, "min_lat": 27.0, "max_lat": 31.0}
START_DATETIME = "2023-01-11T12:00:00"
END_DATETIME = "2023-01-17T00:00:00"


def acquire() -> None:
    if DEST_DIR.exists() and any(DEST_DIR.iterdir()):
        raise SystemExit(f"STOPPED: {DEST_DIR} already exists and is non-empty. Not overwriting.")

    import copernicusmarine

    username = os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")
    password = os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "STOPPED at credential boundary: COPERNICUSMARINE_SERVICE_USERNAME / "
            "COPERNICUSMARINE_SERVICE_PASSWORD not set. Register a free account "
            "at https://marine.copernicus.eu/ , then set these two environment "
            "variables before re-running. No download attempted."
        )

    valid = copernicusmarine.login(
        username=username, password=password, check_credentials_valid=True,
    )
    if not valid:
        raise SystemExit("STOPPED: credentials provided but invalid per copernicusmarine.login(). No download attempted.")

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    out_filename = f"cmems_mc20_{START_DATETIME[:10]}_to_{END_DATETIME[:10]}.nc"

    print(f"Requesting CMEMS uo/vo, region={REGION}, {START_DATETIME}..{END_DATETIME}")
    copernicusmarine.subset(
        dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
        variables=["uo", "vo"],
        minimum_longitude=REGION["min_lon"], maximum_longitude=REGION["max_lon"],
        minimum_latitude=REGION["min_lat"], maximum_latitude=REGION["max_lat"],
        start_datetime=START_DATETIME, end_datetime=END_DATETIME,
        output_filename=out_filename,
        output_directory=str(DEST_DIR),
    )

    record = {
        "product_id": "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
        "variables": ["uo", "vo"],
        "region": REGION,
        "start_datetime": START_DATETIME,
        "end_datetime": END_DATETIME,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "destination": str(DEST_DIR / out_filename),
        "reason": "MC20 case, same planning window as ERA5 request",
    }
    record_path = REPO_ROOT / "data" / "catalog" / "acquisition" / "cmems_mc20.json"
    record_path.write_text(json.dumps(record, indent=2))
    print(f"Wrote acquisition record {record_path}")


if __name__ == "__main__":
    acquire()
