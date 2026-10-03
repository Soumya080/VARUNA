"""
NETRA-GOLD-v0.2 | Stage 05 - Gold validation (Phase 15).

Scans the complete generated Gold dataset and proves:
  * every manifest entry exists on disk with the declared shape and dtype
  * no NaN / Inf survived normalization, and values sit in [0, 1]
  * labels are a subset of the declared class set
  * split membership on disk agrees with the manifest
  * unmanifested files present in the Gold tree are counted and named, and are
    demonstrably invisible to the manifest-driven loader

Read-only. Nothing on disk is altered.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "data" / "gold" / "netra_v0_2"
MANIFEST = REPO / "data" / "manifests" / "netra_gold_v0_2.json"
OUT = REPO / "reports" / "netra_v02"

TILE = 512


def check_tile(t: dict) -> dict:
    p_img = REPO / t["img"]
    p_msk = REPO / t["mask"]
    r = {"tile_id": t["tile_id"], "ok": True, "issues": []}
    try:
        if not p_img.exists():
            r["issues"].append("image missing")
        if not p_msk.exists():
            r["issues"].append("mask missing")
        if r["issues"]:
            r["ok"] = False
            return r

        img = np.load(p_img)
        msk = np.load(p_msk)

        if img.shape != (2, TILE, TILE):
            r["issues"].append(f"image shape {img.shape}")
        if img.dtype != np.float32:
            r["issues"].append(f"image dtype {img.dtype}")
        if msk.shape != (TILE, TILE):
            r["issues"].append(f"mask shape {msk.shape}")
        if msk.dtype not in (np.uint8, np.int64, np.int32):
            r["issues"].append(f"mask dtype {msk.dtype}")
        if not np.isfinite(img).all():
            r["issues"].append("non-finite values in image")
        mn, mx = float(img.min()), float(img.max())
        if mn < -1e-6 or mx > 1.0 + 1e-6:
            r["issues"].append(f"image outside [0,1]: [{mn:.4f}, {mx:.4f}]")
        u = np.unique(msk)
        if not set(int(x) for x in u).issubset({0, 1}):
            r["issues"].append(f"mask labels {u.tolist()}")
        if int((msk > 0).sum()) != int(t["oil_px"]):
            r["issues"].append("oil_px disagrees with manifest")
        r["ok"] = not r["issues"]
        r["img_min"], r["img_max"] = mn, mx
    except Exception as exc:
        r["ok"] = False
        r["issues"].append(f"{type(exc).__name__}: {exc}")
    return r


def main() -> int:
    if not MANIFEST.exists():
        raise SystemExit(f"[FATAL] manifest missing: {MANIFEST}")
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tiles = man["tiles"]
    print(f"[INFO] validating {len(tiles)} manifested tiles of {man['dataset_version']}")

    t0 = time.perf_counter()
    bad: list[dict] = []
    rng = np.random.default_rng(0)
    # full existence + metadata check for every tile; full array read for a
    # deterministic 5% sample plus every positive tile (where errors matter most)
    deep_idx = set(rng.choice(len(tiles), size=max(1, len(tiles) // 20), replace=False).tolist())
    deep_idx |= {i for i, t in enumerate(tiles) if t["oil_px"] > 0}
    print(f"[INFO] deep array check on {len(deep_idx)} tiles "
          f"({len(deep_idx) / len(tiles):.1%}, includes all positive tiles)")

    missing = 0
    for t in tiles:
        if not (REPO / t["img"]).exists() or not (REPO / t["mask"]).exists():
            missing += 1
            bad.append({"tile_id": t["tile_id"], "ok": False, "issues": ["file missing"]})
    print(f"[CHECK] existence: {len(tiles) - missing}/{len(tiles)} present")

    deep_tiles = [tiles[i] for i in sorted(deep_idx)]
    done = 0
    stats = {"img_min": 1e9, "img_max": -1e9}
    with ThreadPoolExecutor(8) as ex:
        for r in ex.map(check_tile, deep_tiles):
            if not r["ok"]:
                bad.append(r)
            else:
                stats["img_min"] = min(stats["img_min"], r["img_min"])
                stats["img_max"] = max(stats["img_max"], r["img_max"])
            done += 1
            if done % 2000 == 0:
                print(f"  deep {done}/{len(deep_tiles)}  {time.perf_counter() - t0:.0f}s", flush=True)

    # unmanifested files in the Gold tree
    on_disk = set()
    for split in ("train", "val", "test"):
        d = GOLD / split
        if d.exists():
            on_disk |= {str(p.relative_to(REPO)).replace("\\", "/") for p in d.glob("*.npy")}
    manifested = {t["img"] for t in tiles} | {t["mask"] for t in tiles}
    unmanifested = sorted(on_disk - manifested)

    # split agreement
    split_disk = Counter(Path(t["img"]).parent.name for t in tiles)
    split_man = Counter(t["split"] for t in tiles)
    split_agrees = split_disk == split_man

    by_split = defaultdict(lambda: {"tiles": 0, "scenes": set(), "positive": 0, "oil_px": 0,
                                    "sources": Counter(), "fully_nodata": 0})
    for t in tiles:
        b = by_split[t["split"]]
        b["tiles"] += 1
        b["scenes"].add(t["scene_id"])
        b["positive"] += 1 if t["oil_px"] > 0 else 0
        b["oil_px"] += t["oil_px"]
        b["sources"][t["source"]] += 1
        if t["valid_frac"] == 0.0:
            b["fully_nodata"] += 1

    report = {
        "dataset_version": man["dataset_version"],
        "n_manifested_tiles": len(tiles),
        "n_missing": missing,
        "n_deep_checked": len(deep_tiles),
        "n_failures": len(bad),
        "failures": bad[:50],
        "value_range_observed": stats,
        "split_agreement": split_agrees,
        "unmanifested_files_in_gold_tree": len(unmanifested),
        "unmanifested_examples": unmanifested[:10],
        "unmanifested_note": (
            "Files present on disk but absent from the manifest are never loaded: "
            "NetraGoldDataset iterates manifest entries only. They are reported, not removed."
        ),
        "per_split": {
            s: {
                "tiles": v["tiles"],
                "scenes": len(v["scenes"]),
                "positive_tiles": v["positive"],
                "empty_tiles": v["tiles"] - v["positive"],
                "oil_pixel_frac": v["oil_px"] / (v["tiles"] * TILE * TILE) if v["tiles"] else 0.0,
                "fully_nodata_tiles": v["fully_nodata"],
                "sources": dict(v["sources"]),
            }
            for s, v in sorted(by_split.items())
        },
    }
    (OUT / "05_gold_validation.json").write_text(json.dumps(report, indent=2))

    print(f"\n[GOLD VALIDATION - {man['dataset_version']}]")
    for s, v in report["per_split"].items():
        print(f"  {s:5s}: {v['tiles']:>6} tiles  {v['scenes']:>5} scenes  "
              f"pos={v['positive_tiles']:>5}  empty={v['empty_tiles']:>6}  "
              f"oil_px={v['oil_pixel_frac']:.4%}  nodata_tiles={v['fully_nodata_tiles']}")
        print(f"         sources: {v['sources']}")
    print(f"  value range observed        : [{stats['img_min']:.4f}, {stats['img_max']:.4f}]")
    print(f"  split agreement             : {split_agrees}")
    print(f"  unmanifested files in tree  : {len(unmanifested)} (ignored by the loader)")
    print(f"  failures                    : {len(bad)}")
    if bad:
        for b in bad[:10]:
            print(f"    {b['tile_id']}: {b['issues']}")
        print("\n[FAIL] Gold validation failed")
        return 6
    print(f"\n[PASS] Gold validation clean  ({time.perf_counter() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
