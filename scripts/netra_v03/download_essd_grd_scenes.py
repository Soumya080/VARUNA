"""Download the 25 selected ESSD/PANGAEA Sentinel-1 GRD scenes from
Copernicus Data Space (CDSE), resumable, checksum-verified.

Credentials come from CDSE_USERNAME / CDSE_PASSWORD environment
variables (loaded from .env by the caller) -- never printed, never
persisted to disk.

Never overwrites an existing, checksum-verified file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "scenes"
PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"
SCENE_LIST = PROV_DIR / "scene_list.txt"
ACQ_LOG = PROV_DIR / "scene_acquisition_log.json"

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_URL_TMPL = "https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"


def get_token() -> str:
    username = os.environ["CDSE_USERNAME"]
    password = os.environ["CDSE_PASSWORD"]
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def catalogue_lookup(name: str) -> dict:
    resp = requests.get(
        CATALOGUE_URL,
        params={"$filter": f"Name eq '{name}'"},
        timeout=30,
    )
    resp.raise_for_status()
    values = resp.json().get("value", [])
    if not values:
        raise RuntimeError(f"not found in catalogue: {name}")
    return values[0]


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_one(token: str, name: str, label: str, log: list) -> dict:
    meta = catalogue_lookup(name)
    product_id = meta["Id"]
    expected_size = meta["ContentLength"]
    expected_md5 = next(
        (c["Value"] for c in meta.get("Checksum", []) if c["Algorithm"] == "MD5"),
        None,
    )
    dest = OUT_DIR / f"{name}.zip"
    dest_part = OUT_DIR / f"{name}.zip.part"

    entry = {
        "product_id": name,
        "cdse_id": product_id,
        "label": label,
        "source_url": DOWNLOAD_URL_TMPL.format(product_id=product_id),
        "expected_size_bytes": expected_size,
        "expected_md5": expected_md5,
        "content_date_start": meta.get("ContentDate", {}).get("Start"),
        "access_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if dest.exists() and dest.stat().st_size == expected_size:
        actual_md5 = md5_of(dest)
        entry["actual_size_bytes"] = dest.stat().st_size
        entry["actual_md5"] = actual_md5
        entry["status"] = "already_present_verified" if actual_md5 == expected_md5 else "SIZE_OK_MD5_MISMATCH"
        print(f"[skip] {name}: already present, {entry['status']}")
        log.append(entry)
        return entry

    url = DOWNLOAD_URL_TMPL.format(product_id=product_id)
    headers = {"Authorization": f"Bearer {token}"}
    resume_from = dest_part.stat().st_size if dest_part.exists() else 0
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
        mode = "ab"
    else:
        mode = "wb"

    print(f"[download] {name} ({expected_size/1e9:.2f}GB) resume_from={resume_from}")
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest_part, mode) as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)

    actual_size = dest_part.stat().st_size
    if actual_size != expected_size:
        entry["status"] = f"SIZE_MISMATCH expected={expected_size} actual={actual_size}"
        print(f"[FAIL] {name}: {entry['status']}")
        log.append(entry)
        return entry

    actual_md5 = md5_of(dest_part)
    entry["actual_size_bytes"] = actual_size
    entry["actual_md5"] = actual_md5
    if expected_md5 and actual_md5 != expected_md5:
        entry["status"] = "MD5_MISMATCH"
        print(f"[FAIL] {name}: MD5 mismatch expected={expected_md5} actual={actual_md5}")
        log.append(entry)
        return entry

    dest_part.rename(dest)
    entry["status"] = "verified"
    print(f"[ok] {name}: size+md5 verified")
    log.append(entry)
    return entry


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scenes = []
    with open(SCENE_LIST) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, label = line.split("\t")
            scenes.append((name, label))

    log = []
    if ACQ_LOG.exists():
        log = json.loads(ACQ_LOG.read_text())

    done_names = {e["product_id"] for e in log if e.get("status") in ("verified", "already_present_verified")}
    # drop stale failure entries for scenes we're about to retry, so the
    # final log reflects the outcome of this run, not a transient 401
    log = [e for e in log if e.get("product_id") in done_names]

    for name, label in scenes:
        if name in done_names:
            print(f"[skip] {name}: already logged verified")
            continue
        token = get_token()  # fresh token per scene -- CDSE tokens expire in 1800s
        try:
            download_one(token, name, label, log)
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            log.append({"product_id": name, "label": label, "status": f"ERROR: {e}"})
        ACQ_LOG.write_text(json.dumps(log, indent=2))

    ACQ_LOG.write_text(json.dumps(log, indent=2))
    n_ok = sum(1 for e in log if e.get("status") in ("verified", "already_present_verified"))
    print(f"\n{n_ok}/{len(scenes)} scenes verified")


if __name__ == "__main__":
    main()
