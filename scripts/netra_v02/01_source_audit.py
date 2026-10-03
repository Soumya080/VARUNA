"""
NETRA-GOLD-v0.2 | Stage 01 - Unified source audit (Phases 4, 5, 6).

Single disk pass over every Zenodo Part I and Part II scene:
  - SHA-256 of image file bytes and mask file bytes (dedup evidence)
  - geospatial + dtype + shape validation
  - NaN / Inf / nodata accounting
  - mask label validation and oil-pixel census

Raw files are opened read-only and never modified.
Output: reports/netra_v02/01_source_audit.jsonl (+ .summary.json)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw" / "zenodo" / "extracted"
OUT = REPO / "reports" / "netra_v02"
OUT.mkdir(parents=True, exist_ok=True)

# (source_key, label_semantics, images_dir, masks_dir)
SOURCES = [
    ("zenodo_part1", "OIL_POSITIVE", RAW / "part1", RAW / "part1" / "Mask_oil"),
    ("zenodo_part2_lookalike", "HARD_NEGATIVE_LOOKALIKE",
     RAW / "part2" / "Lookalike" / "Lookalike", RAW / "part2" / "Lookalike" / "Mask_lookalike"),
    ("zenodo_part2_no_oil", "HARD_NEGATIVE_NO_OIL",
     RAW / "part2" / "No_Oil" / "No_oil", RAW / "part2" / "No_Oil" / "Mask_no_oil"),
]


def _read_bytes(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def audit_scene(source: str, semantics: str, img_path: Path, mask_path: Path) -> dict:
    rec: dict = {
        "scene_id": f"{source}__{img_path.stem}",
        "source": source,
        "label_semantics": semantics,
        "image_path": str(img_path.relative_to(REPO)),
        "mask_path": str(mask_path.relative_to(REPO)),
        "checks": {},
        "verdict": "PASS",
        "failures": [],
    }
    try:
        img_blob = _read_bytes(img_path)
        msk_blob = _read_bytes(mask_path)
        rec["image_sha256"] = _sha256(img_blob)
        rec["mask_sha256"] = _sha256(msk_blob)
        rec["image_bytes"] = len(img_blob)
        rec["mask_bytes"] = len(msk_blob)

        with MemoryFile(img_blob) as mf, mf.open() as src:
            rec["width"], rec["height"] = src.width, src.height
            rec["bands"] = src.count
            rec["dtypes"] = list(src.dtypes)
            rec["crs"] = str(src.crs) if src.crs else None
            b = src.bounds
            rec["bbox"] = [b.left, b.bottom, b.right, b.top]
            rec["res"] = list(src.res)
            rec["nodata_declared"] = src.nodata
            arr = src.read().astype(np.float32)  # (bands, H, W)

        n_px = arr[0].size
        rec["checks"]["nan_count"] = int(np.isnan(arr).sum())
        rec["checks"]["inf_count"] = int(np.isinf(arr).sum())
        finite = np.isfinite(arr)
        # zero-fill is the observed nodata convention in this corpus (border/land fill)
        zero_frac = float((arr == 0.0).all(axis=0).mean())
        rec["checks"]["zerofill_frac"] = zero_frac
        with np.errstate(all="ignore"):
            valid = finite & (arr != 0.0)
            for i, ch in enumerate(("VV", "VH")):
                if i < arr.shape[0]:
                    v = arr[i][valid[i]]
                    rec["checks"][f"{ch}_valid_px"] = int(v.size)
                    if v.size:
                        rec["checks"][f"{ch}_min"] = float(v.min())
                        rec["checks"][f"{ch}_max"] = float(v.max())
                        rec["checks"][f"{ch}_mean"] = float(v.mean())

        with MemoryFile(msk_blob) as mf, mf.open() as msrc:
            rec["mask_width"], rec["mask_height"] = msrc.width, msrc.height
            rec["mask_bands"] = msrc.count
            rec["mask_dtype"] = msrc.dtypes[0]
            m = msrc.read(1)
        uniq = np.unique(m)
        rec["mask_unique"] = [int(u) for u in uniq]
        rec["oil_px"] = int((m > 0).sum())
        rec["oil_frac"] = float((m > 0).mean())

        # ---- hard quality gates ----
        f = rec["failures"]
        if rec["bands"] != 2:
            f.append(f"expected 2 bands (VV,VH), got {rec['bands']}")
        if (rec["width"], rec["height"]) != (2048, 2048):
            f.append(f"unexpected image size {rec['width']}x{rec['height']}")
        if (rec["mask_width"], rec["mask_height"]) != (rec["width"], rec["height"]):
            f.append("image/mask dimension mismatch")
        if rec["checks"]["nan_count"] or rec["checks"]["inf_count"]:
            f.append("non-finite pixels present")
        if not set(rec["mask_unique"]).issubset({0, 1}):
            f.append(f"mask labels outside {{0,1}}: {rec['mask_unique']}")
        if rec["crs"] is None:
            f.append("image has no CRS")
        if zero_frac > 0.90:
            f.append(f"scene is {zero_frac:.1%} zero-fill")
        # negatives must genuinely be negative
        if semantics.startswith("HARD_NEGATIVE") and rec["oil_px"] != 0:
            f.append("negative-class scene carries positive mask pixels")
        # positives should carry at least some oil
        if semantics == "OIL_POSITIVE" and rec["oil_px"] == 0:
            rec["checks"]["positive_with_empty_mask"] = True

        rec["verdict"] = "QUARANTINE" if f else "PASS"
    except Exception as exc:  # never silently skip
        rec["verdict"] = "ERROR"
        rec["failures"].append(f"{type(exc).__name__}: {exc}")
    return rec


def main() -> int:
    tasks = []
    for source, semantics, img_dir, msk_dir in SOURCES:
        if not img_dir.exists():
            print(f"[FATAL] missing image dir {img_dir}")
            return 2
        for p in sorted(img_dir.glob("*.tif")):
            mp = msk_dir / f"{p.stem}.tif"
            if not mp.exists():
                print(f"[UNPAIRED] {source}/{p.name} has no mask -> recorded, not skipped")
                tasks.append((source, semantics, p, mp))
                continue
            tasks.append((source, semantics, p, mp))
    print(f"[INFO] {len(tasks)} scenes queued across {len(SOURCES)} sources")

    out_path = OUT / "01_source_audit.jsonl"
    t0 = time.perf_counter()
    done = 0
    counts: dict = {}
    with open(out_path, "w", encoding="utf-8") as fh, ThreadPoolExecutor(8) as ex:
        for rec in ex.map(lambda a: audit_scene(*a), tasks):
            fh.write(json.dumps(rec) + "\n")
            done += 1
            counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
            if done % 100 == 0:
                el = time.perf_counter() - t0
                print(f"  {done}/{len(tasks)}  {el:6.0f}s  {done/el:5.2f} scenes/s", flush=True)

    el = time.perf_counter() - t0
    summary = {
        "n_scenes": len(tasks),
        "verdicts": counts,
        "elapsed_s": round(el, 1),
        "scenes_per_s": round(len(tasks) / el, 3),
        "sources": [s[0] for s in SOURCES],
    }
    (OUT / "01_source_audit.summary.json").write_text(json.dumps(summary, indent=2))
    print("\n[DONE]", json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
