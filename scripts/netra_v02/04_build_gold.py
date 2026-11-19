"""
NETRA-GOLD-v0.2 | Stage 04 - Tiling, Gold emission, manifest (Phases 11-14).

Order is load-bearing and matches the corrected pipeline:

    unified raw/canonical pool
      -> correct dedup            (stage 02)
      -> scene-level geo split    (stage 02)
      -> leakage guard            (stage 02)
      -> train-only normalization (stage 03)
      -> tile                     (here)
      -> Gold + manifest          (here)

Every tile is written with its parent scene, split, pixel window, bbox and
source recorded in the manifest. Nothing is loaded wholesale into RAM: scenes
are streamed one at a time and tiles are flushed as they are produced.

Empty-oil tiles are NOT dropped. Membership and sampling policy are separate
concerns; `oil_px` and `valid_frac` are recorded per tile so a sampler can
weight them without the dataset silently losing data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "reports" / "netra_v02"
GOLD = REPO / "data" / "gold" / "netra_v0_2"
MANIFEST = REPO / "data" / "manifests" / "netra_gold_v0_2.json"

DATASET_ID = "netra_zenodo_p1p2"
DATASET_VERSION = "NETRA-GOLD-v0.2"
TILE_SIZE = 512
CHANNELS = ["VV", "VH"]
LABEL_MAPPING = {
    "classes": {"0": "NOT_OIL", "1": "OIL"},
    "policy": (
        "Zenodo Part II Lookalike and No_Oil scenes are HARD NEGATIVES carrying "
        "all-zero masks. They are NOT a third segmentation class; the source "
        "provides no pixel-level lookalike labels."
    ),
}


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def normalize(arr: np.ndarray, norm: dict) -> tuple[np.ndarray, np.ndarray]:
    """Apply the frozen train-only record. nodata is forced to 0.0 explicitly."""
    finite = np.isfinite(arr).all(axis=0)
    nodata = (arr[0] == 0.0) & (arr[1] == 0.0)
    valid = finite & ~nodata
    out = np.empty_like(arr, dtype=np.float32)
    for i, ch in enumerate(CHANNELS):
        lo = float(norm["channels"][ch]["clip_low"])
        hi = float(norm["channels"][ch]["clip_high"])
        span = hi - lo
        if span <= 0:
            raise ValueError(f"degenerate normalization span for {ch}: [{lo}, {hi}]")
        x = np.clip(np.nan_to_num(arr[i], nan=lo, posinf=hi, neginf=lo), lo, hi)
        out[i] = ((x - lo) / span).astype(np.float32)
    out[:, ~valid] = 0.0
    return out, valid


def process_scene(rec: dict, split: str, norm: dict) -> list[dict]:
    img_path = REPO / rec["image_path"]
    msk_path = REPO / rec["mask_path"]
    scene_id = rec["scene_id"]

    with rasterio.open(img_path) as src:
        arr = src.read().astype(np.float32)
        b = src.bounds
        transform = src.transform
    with rasterio.open(msk_path) as msrc:
        mask = msrc.read(1).astype(np.uint8)

    if mask.shape != arr.shape[1:]:
        raise ValueError(f"{scene_id}: image {arr.shape[1:]} vs mask {mask.shape}")

    norm_arr, valid = normalize(arr, norm)
    del arr

    H, W = mask.shape
    lon_per_px = (b.right - b.left) / W
    lat_per_px = (b.top - b.bottom) / H

    split_dir = GOLD / split
    split_dir.mkdir(parents=True, exist_ok=True)

    tiles: list[dict] = []
    for y in range(0, H - TILE_SIZE + 1, TILE_SIZE):
        for x in range(0, W - TILE_SIZE + 1, TILE_SIZE):
            img_t = np.ascontiguousarray(norm_arr[:, y:y + TILE_SIZE, x:x + TILE_SIZE])
            msk_t = np.ascontiguousarray(mask[y:y + TILE_SIZE, x:x + TILE_SIZE])
            val_t = valid[y:y + TILE_SIZE, x:x + TILE_SIZE]

            tile_id = f"{scene_id}__r{y // TILE_SIZE}c{x // TILE_SIZE}"
            ip = split_dir / f"{tile_id}_img.npy"
            mp = split_dir / f"{tile_id}_mask.npy"
            np.save(ip, img_t)
            np.save(mp, msk_t)

            tiles.append({
                "tile_id": tile_id,
                "scene_id": scene_id,
                "source": rec["source"],
                "label_semantics": rec["label_semantics"],
                "split": split,
                "row": y // TILE_SIZE,
                "col": x // TILE_SIZE,
                "pixel_window": [x, y, TILE_SIZE, TILE_SIZE],
                "bbox": [
                    b.left + x * lon_per_px,
                    b.top - (y + TILE_SIZE) * lat_per_px,
                    b.left + (x + TILE_SIZE) * lon_per_px,
                    b.top - y * lat_per_px,
                ],
                "oil_px": int((msk_t > 0).sum()),
                "valid_frac": float(val_t.mean()),
                "img": str(ip.relative_to(REPO)).replace("\\", "/"),
                "mask": str(mp.relative_to(REPO)).replace("\\", "/"),
            })
    return tiles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="debug: cap scene count")
    args = ap.parse_args()

    split_info = json.loads((OUT / "02_dedup_split.json").read_text(encoding="utf-8"))
    norm = json.loads((OUT / "03_normalization.json").read_text(encoding="utf-8"))
    audit = [json.loads(l) for l in (OUT / "01_source_audit.jsonl").read_text(encoding="utf-8").splitlines() if l]
    by_id = {r["scene_id"]: r for r in audit}

    scene_split: dict[str, str] = split_info["split"]["scene_split"]
    scenes = sorted(scene_split)
    if args.limit:
        scenes = scenes[: args.limit]
    print(f"[INFO] tiling {len(scenes)} scenes at {TILE_SIZE}x{TILE_SIZE} -> {GOLD}")
    print(f"[INFO] normalization: {norm['normalization_version']} "
          f"(VV p2={norm['channels']['VV']['p2']:.2f} p98={norm['channels']['VV']['p98']:.2f} dB)")

    GOLD.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    all_tiles: list[dict] = []
    errors: list[dict] = []
    t0 = time.perf_counter()
    done = 0

    def work(sid: str):
        try:
            return sid, process_scene(by_id[sid], scene_split[sid], norm), None
        except Exception as exc:  # never silently skip a scene
            return sid, [], f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(args.workers) as ex:
        for sid, tiles, err in ex.map(work, scenes):
            if err:
                errors.append({"scene_id": sid, "error": err})
                print(f"  [ERROR] {sid}: {err}", flush=True)
            all_tiles.extend(tiles)
            done += 1
            if done % 50 == 0:
                el = time.perf_counter() - t0
                print(f"  {done}/{len(scenes)} scenes  {len(all_tiles)} tiles  "
                      f"{el:6.0f}s  {done / el:5.2f} scenes/s", flush=True)

    if errors:
        print(f"\n[FATAL] {len(errors)} scenes failed; not writing a manifest that omits them")
        (OUT / "04_errors.json").write_text(json.dumps(errors, indent=2))
        return 5

    counts = {s: sum(1 for t in all_tiles if t["split"] == s) for s in ("train", "val", "test")}
    split_scene_ids = {
        s: sorted({t["scene_id"] for t in all_tiles if t["split"] == s})
        for s in ("train", "val", "test")
    }

    src_hashes = {}
    for src in ("zenodo_part1", "zenodo_part2_lookalike", "zenodo_part2_no_oil"):
        h = hashlib.sha256()
        for sid in sorted(s for s in scenes if by_id[s]["source"] == src):
            h.update(by_id[sid]["image_sha256"].encode())
            h.update(by_id[sid]["mask_sha256"].encode())
        src_hashes[src] = h.hexdigest()

    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "pipeline_stage_scripts": [
            "scripts/netra_v02/01_source_audit.py",
            "scripts/netra_v02/02_dedup_split.py",
            "scripts/netra_v02/03_normalization.py",
            "scripts/netra_v02/04_build_gold.py",
        ],
        "scientific_status": "EXPERIMENTAL / UNVALIDATED",
        "source_datasets": [
            {"id": "zenodo_part1", "role": "OIL_POSITIVE", "record": "8346860",
             "license": "CC-BY-4.0", "content_hash": src_hashes["zenodo_part1"]},
            {"id": "zenodo_part2_lookalike", "role": "HARD_NEGATIVE", "record": "8253899",
             "license": "CC-BY-4.0", "content_hash": src_hashes["zenodo_part2_lookalike"]},
            {"id": "zenodo_part2_no_oil", "role": "HARD_NEGATIVE", "record": "8253899",
             "license": "CC-BY-4.0", "content_hash": src_hashes["zenodo_part2_no_oil"]},
        ],
        "channels": CHANNELS,
        "label_mapping": LABEL_MAPPING,
        "tiling": {"tile_size": TILE_SIZE, "stride": TILE_SIZE,
                   "tiles_per_scene": (2048 // TILE_SIZE) ** 2,
                   "order": "split_before_tile"},
        "counts": {
            "audited_scenes": split_info["n_audited"],
            "quarantined_scenes": split_info["n_quarantined"],
            "exact_duplicate_scenes_excluded": split_info["dedup"]["n_scenes_dropped_as_exact_duplicate"],
            "pool_scenes": split_info["pool_size"],
            "gold_scenes": len(scenes),
            "tiles_total": len(all_tiles),
            "tiles_by_split": counts,
            "pool_by_source": split_info["pool_by_source"],
        },
        "dedup": {k: v for k, v in split_info["dedup"].items() if k != "duplicate_of"},
        "split": {
            "strategy": split_info["split"]["strategy"],
            "seed": split_info["split"]["seed"],
            "ratios": split_info["split"]["ratios"],
            "grouping": split_info["grouping"],
            "scene_counts": split_info["split"]["counts"],
            "scene_ids": split_scene_ids,
            "region_assignment": split_info["split"]["region_assignment"],
        },
        "leakage": split_info["leakage"],
        "normalization": norm,
        "provenance": {
            "raw_root": "data/raw/zenodo/extracted",
            "raw_modified": False,
            "supersedes": "NETRA-GOLD-v0.1 (retained at data/gold/netra/ as historical evidence)",
        },
        "tiles": all_tiles,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1))

    el = time.perf_counter() - t0
    print(f"\n[DONE] {len(all_tiles)} tiles in {el / 60:.1f} min")
    print(f"       train={counts['train']}  val={counts['val']}  test={counts['test']}")
    print(f"       manifest: {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
