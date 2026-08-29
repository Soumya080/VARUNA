"""
VARUNA GRID — MC20 Sentinel-1 GRD acquisition.

Downloads exactly ONE identified, catalog-confirmed product:
    S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE
    UUID 6fc676ba-b961-5bfc-9211-8076f8f1481c
    1,741,458,044 bytes (1.74GB)

Requires a free Copernicus Data Space Ecosystem account
(https://dataspace.copernicus.eu/ -> register). Reads credentials ONLY
from environment variables -- never hardcoded, never prompted for and
echoed, never committed:

    CDSE_USERNAME
    CDSE_PASSWORD

Stops at the credential boundary if either is unset -- does not attempt
the download, does not bypass authentication.

Destination (never overwrites an existing directory):
    D:\\ROUTER(DATASETS)\\_downloads\\sentinel1_grd\\  (raw download)
    data/raw/sentinel1_grd/mc20_2023-01-15/            (derived extraction)

Usage: python scripts/acquire_mc20_sar.py
"""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_UUID = "6fc676ba-b961-5bfc-9211-8076f8f1481c"
PRODUCT_NAME = "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE"
EXPECTED_SIZE_BYTES = 1_741_458_044

DOWNLOAD_DIR = Path("D:/ROUTER(DATASETS)/_downloads/sentinel1_grd")
RAW_DEST_DIR = REPO_ROOT / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15"

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
DOWNLOAD_URL = f"https://download.dataspace.copernicus.eu/odata/v1/Products({PRODUCT_UUID})/$value"


def get_access_token() -> str:
    username = os.environ.get("CDSE_USERNAME")
    password = os.environ.get("CDSE_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "STOPPED at credential boundary: CDSE_USERNAME / CDSE_PASSWORD "
            "not set in the environment. Register a free account at "
            "https://dataspace.copernicus.eu/ , then set these two "
            "environment variables before re-running. No download attempted."
        )
    resp = requests.post(TOKEN_URL, data={
        "client_id": "cdse-public",
        "grant_type": "password",
        "username": username,
        "password": password,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def download() -> Path:
    if RAW_DEST_DIR.exists() and any(RAW_DEST_DIR.iterdir()):
        raise SystemExit(f"STOPPED: {RAW_DEST_DIR} already exists and is non-empty. Not overwriting.")

    token = get_access_token()
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DOWNLOAD_DIR / f"{PRODUCT_NAME}.zip"
    if zip_path.exists():
        raise SystemExit(f"STOPPED: {zip_path} already exists. Verify manually before proceeding; not overwriting.")

    print(f"Downloading {PRODUCT_NAME} ({EXPECTED_SIZE_BYTES:,} bytes expected)...")
    headers = {"Authorization": f"Bearer {token}"}
    with requests.get(DOWNLOAD_URL, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with zip_path.open("wb") as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded % (100 * 1024 * 1024) < 1024 * 1024:
                    print(f"  {downloaded:,} / {EXPECTED_SIZE_BYTES:,} bytes")

    actual_size = zip_path.stat().st_size
    print(f"Downloaded {actual_size:,} bytes (expected {EXPECTED_SIZE_BYTES:,})")

    print("Computing SHA-256...")
    h = hashlib.sha256()
    with zip_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    checksum = h.hexdigest()

    print(f"Extracting to {RAW_DEST_DIR}...")
    RAW_DEST_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(RAW_DEST_DIR)

    record = {
        "product_name": PRODUCT_NAME,
        "product_uuid": PRODUCT_UUID,
        "source": "Copernicus Data Space Ecosystem",
        "acquisition_timestamp": "2023-01-15T00:02:06.898000+00:00",
        "downloaded_at": datetime.now(UTC).isoformat(),
        "downloaded_size_bytes": actual_size,
        "expected_size_bytes": EXPECTED_SIZE_BYTES,
        "size_matches": actual_size == EXPECTED_SIZE_BYTES,
        "sha256": checksum,
        "raw_zip_path": str(zip_path),
        "extracted_to": str(RAW_DEST_DIR),
        "license": "Copernicus Sentinel Data Terms and Conditions (free, open)",
    }
    record_path = REPO_ROOT / "data" / "catalog" / "acquisition" / "sentinel1_grd_mc20.json"
    record_path.write_text(json.dumps(record, indent=2))
    print(f"Wrote acquisition record: {record_path}")
    return RAW_DEST_DIR


if __name__ == "__main__":
    download()
