"""
NETRA-GOLD-v0.2 | Stage 02 - Correct dedup, geographic split, leakage guard
(Phases 4, 7, 8, 9).

Deduplication policy
--------------------
An exact duplicate requires BOTH image content and mask content to be
identical (SHA-256 of the file bytes, computed in stage 01):

    same image_sha256 AND same mask_sha256          -> exact duplicate
    same image, different mask                      -> PRESERVE both, report
    same mask, different image                      -> PRESERVE both, report
    overlapping bounding boxes only                 -> NOT a duplicate

The v0.1 pipeline treated bbox overlap alone as duplication and discarded 826
of 1,200 Part I scenes. That behaviour is not reproduced here.

Split policy
------------
Scene-level, computed BEFORE tiling, and geographic because real EPSG:4326
bounds exist for every scene. Temporal split is UNAVAILABLE: this corpus
carries no acquisition timestamps and none are invented.

Grouping is by connected component of the footprint-overlap graph, so two
scenes imaging the same water can never land on opposite sides of a split.
Components are then assigned to splits a whole geographic region at a time.

Raw files are never modified. Duplicates are excluded from training membership
but remain on disk and remain recorded in the outputs.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "reports" / "netra_v02"
AUDIT = OUT / "01_source_audit.jsonl"

REGION_DEG = 5.0
TRAIN_RATIO, VAL_RATIO, TEST_RATIO = 0.80, 0.10, 0.10
MIN_GEO_DISTANCE_KM = 50.0
MIN_EVAL_REGIONS = 4
SEED = 42


def load_audit() -> list[dict]:
    if not AUDIT.exists():
        raise SystemExit(f"[FATAL] stage 01 output missing: {AUDIT}")
    recs = [json.loads(line) for line in AUDIT.read_text(encoding="utf-8").splitlines() if line]
    if not recs:
        raise SystemExit("[FATAL] stage 01 output is empty")
    return recs


# --------------------------------------------------------------------- #
# dedup
# --------------------------------------------------------------------- #
def dedup(records: list[dict]) -> dict:
    by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_img: dict[str, list[str]] = defaultdict(list)
    by_msk: dict[str, list[str]] = defaultdict(list)

    for r in records:
        sid = r["scene_id"]
        by_pair[(r["image_sha256"], r["mask_sha256"])].append(sid)
        by_img[r["image_sha256"]].append(sid)
        by_msk[r["mask_sha256"]].append(sid)

    exact_groups = {k: sorted(v) for k, v in by_pair.items() if len(v) > 1}
    duplicate_of: dict[str, str] = {}
    for members in exact_groups.values():
        keeper = members[0]
        for m in members[1:]:
            duplicate_of[m] = keeper

    same_img_diff_mask = {
        h: sorted(v) for h, v in by_img.items()
        if len(v) > 1 and len({r["mask_sha256"] for r in records if r["scene_id"] in set(v)}) > 1
    }
    # same mask + different image is expected en masse for the all-zero negative
    # masks, so it is summarised rather than enumerated scene by scene.
    same_mask_diff_img = {
        h: len(v) for h, v in by_msk.items()
        if len(v) > 1 and len({r["image_sha256"] for r in records if r["scene_id"] in set(v)}) > 1
    }

    return {
        "exact_duplicate_groups": [sorted(v) for v in exact_groups.values()],
        "n_exact_duplicate_groups": len(exact_groups),
        "n_scenes_dropped_as_exact_duplicate": len(duplicate_of),
        "duplicate_of": duplicate_of,
        "same_image_different_mask_groups": {k[:16]: v for k, v in same_img_diff_mask.items()},
        "n_same_image_different_mask": len(same_img_diff_mask),
        "same_mask_different_image_group_sizes": sorted(same_mask_diff_img.values(), reverse=True)[:10],
        "n_same_mask_different_image_groups": len(same_mask_diff_img),
        "policy": "exact duplicate = identical image bytes AND identical mask bytes; "
                  "bbox overlap alone is NOT duplication",
    }


# --------------------------------------------------------------------- #
# grouping + split
# --------------------------------------------------------------------- #
class UnionFind:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def overlap_components(boxes: np.ndarray) -> np.ndarray:
    """Connected components of the footprint-intersection graph."""
    n = len(boxes)
    uf = UnionFind(n)
    left, bottom, right, top = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    order = np.argsort(left)
    for oi in range(n):
        i = order[oi]
        for oj in range(oi + 1, n):
            j = order[oj]
            if left[j] > right[i]:
                break  # sorted by left edge: nothing further can intersect i
            if right[j] >= left[i] and top[j] >= bottom[i] and bottom[j] <= top[i]:
                uf.union(int(i), int(j))
    return np.array([uf.find(i) for i in range(n)])


def region_of(box: np.ndarray) -> str:
    lon = (box[0] + box[2]) / 2.0
    lat = (box[1] + box[3]) / 2.0
    return f"r{int(math.floor(lat / REGION_DEG))}_{int(math.floor(lon / REGION_DEG))}"


def assign_splits(region_sizes: dict[str, int]) -> dict[str, str]:
    """Deterministic size-stratified dealing of whole regions to splits.

    A plain greedy "give the next region to whichever split is furthest below
    quota" collapses here: region sizes in this corpus are very unequal, so the
    first few regions overshoot val and test and every remaining region lands in
    train. The first attempt produced 59 train regions and exactly ONE region
    each for val and test, which would have meant evaluating in a single 5-degree
    box.

    Instead, regions are sorted by size and dealt in fixed-width windows of ten,
    with reserved slots for val and test inside every window. Both evaluation
    splits therefore span roughly a tenth of all regions and inherit the same
    spread of region sizes as train, while scene counts stay near the target
    ratios. Fully deterministic, no RNG.
    """
    ordered = [r for r, _ in sorted(region_sizes.items(), key=lambda kv: (-kv[1], kv[0]))]
    window = 10
    val_slot, test_slot = 3, 7          # interior slots: neither the largest nor the smallest
    assignment: dict[str, str] = {}
    for i, region in enumerate(ordered):
        pos = i % window
        if pos == val_slot:
            assignment[region] = "val"
        elif pos == test_slot:
            assignment[region] = "test"
        else:
            assignment[region] = "train"
    return assignment


def centroid_km(b1: np.ndarray, b2: np.ndarray) -> float:
    lat1, lon1 = (b1[1] + b1[3]) / 2, (b1[0] + b1[2]) / 2
    lat2, lon2 = (b2[1] + b2[3]) / 2, (b2[0] + b2[2]) / 2
    mlat = math.radians((lat1 + lat2) / 2)
    dy = (lat1 - lat2) * 111.32
    dx = (lon1 - lon2) * 111.32 * math.cos(mlat)
    return math.hypot(dx, dy)


def main() -> int:
    records = load_audit()
    print(f"[INFO] loaded {len(records)} audited scenes")

    verdicts = Counter(r["verdict"] for r in records)
    print(f"[INFO] verdicts: {dict(verdicts)}")
    quarantined = [r for r in records if r["verdict"] != "PASS"]
    for r in quarantined[:20]:
        print(f"  [QUARANTINE] {r['scene_id']}: {r['failures']}")

    eligible = [r for r in records if r["verdict"] == "PASS"]
    print(f"[INFO] {len(eligible)} scenes cleared quality; {len(quarantined)} quarantined")

    dd = dedup(eligible)
    print(f"[DEDUP] exact duplicate groups          : {dd['n_exact_duplicate_groups']}")
    print(f"[DEDUP] scenes dropped as exact dup     : {dd['n_scenes_dropped_as_exact_duplicate']}")
    print(f"[DEDUP] same image / different mask     : {dd['n_same_image_different_mask']} (preserved)")
    print(f"[DEDUP] same mask / different image grp : {dd['n_same_mask_different_image_groups']} (preserved)")

    dup_of = dd["duplicate_of"]
    pool = [r for r in eligible if r["scene_id"] not in dup_of]
    print(f"[POOL]  unified training pool           : {len(pool)} scenes")
    print(f"        by source: {dict(Counter(r['source'] for r in pool))}")

    boxes = np.array([r["bbox"] for r in pool], dtype=np.float64)
    comp = overlap_components(boxes)
    n_comp = len(set(comp.tolist()))
    print(f"[GROUP] footprint-overlap components    : {n_comp}")

    comp_members: dict[int, list[int]] = defaultdict(list)
    for i, c in enumerate(comp):
        comp_members[int(c)].append(i)

    comp_region: dict[int, str] = {}
    for c, idxs in comp_members.items():
        regions = Counter(region_of(boxes[i]) for i in idxs)
        comp_region[c] = regions.most_common(1)[0][0]

    region_sizes: dict[str, int] = Counter()
    for c, idxs in comp_members.items():
        region_sizes[comp_region[c]] += len(idxs)
    print(f"[GROUP] geographic regions ({REGION_DEG}deg)      : {len(region_sizes)}")

    region_split = assign_splits(dict(region_sizes))
    scene_split: dict[str, str] = {}
    for c, idxs in comp_members.items():
        s = region_split[comp_region[c]]
        for i in idxs:
            scene_split[pool[i]["scene_id"]] = s

    counts = Counter(scene_split.values())
    region_counts = Counter(region_split.values())
    if min(region_counts.get("val", 0), region_counts.get("test", 0)) < MIN_EVAL_REGIONS:
        print(f"[FATAL] evaluation splits lack geographic diversity: {dict(region_counts)}; "
              f"val and test each need at least {MIN_EVAL_REGIONS} regions")
        return 8
    print(f"[SPLIT] strategy=geographic_region_stratified seed={SEED}")
    print(f"[SPLIT] regions: {dict(region_counts)} of {len(region_sizes)}")
    print(f"[SPLIT] scenes: {dict(counts)}")
    for s in ("train", "val", "test"):
        by_src = Counter(r["source"] for r in pool if scene_split[r["scene_id"]] == s)
        print(f"        {s:5s}: {dict(by_src)}")

    # ---------------- leakage guard (Phase 9) ---------------- #
    print("\n[LEAKAGE] running guard...")
    idx_of = {r["scene_id"]: i for i, r in enumerate(pool)}
    split_scenes = {s: [r["scene_id"] for r in pool if scene_split[r["scene_id"]] == s]
                    for s in ("train", "val", "test")}

    leak: dict = {"failures": []}

    # 1. scene identity
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        inter = set(split_scenes[a]) & set(split_scenes[b])
        if inter:
            leak["failures"].append(f"scene_id overlap {a}/{b}: {sorted(inter)[:5]}")
    leak["scene_identity"] = "PASS" if not leak["failures"] else "FAIL"

    # 2. exact content duplication across splits
    content_key = {r["scene_id"]: (r["image_sha256"], r["mask_sha256"]) for r in pool}
    cross = []
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        ka = {content_key[s] for s in split_scenes[a]}
        kb = {content_key[s] for s in split_scenes[b]}
        shared = ka & kb
        if shared:
            cross.append(f"{a}/{b}: {len(shared)} identical image+mask pairs")
    if cross:
        leak["failures"].extend(cross)
    leak["content_duplication"] = "PASS" if not cross else "FAIL"

    # 3. footprint overlap across splits
    overlap_fail = 0
    for c, idxs in comp_members.items():
        splits = {scene_split[pool[i]["scene_id"]] for i in idxs}
        if len(splits) > 1:
            overlap_fail += 1
    if overlap_fail:
        leak["failures"].append(f"{overlap_fail} overlap-components span multiple splits")
    leak["footprint_overlap"] = "PASS" if overlap_fail == 0 else "FAIL"

    # 4. geographic proximity (reported; region-atomic assignment is the control)
    prox = {}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        A = np.array([boxes[idx_of[s]] for s in split_scenes[a]])
        B = np.array([boxes[idx_of[s]] for s in split_scenes[b]])
        if len(A) == 0 or len(B) == 0:
            prox[f"{a}_{b}"] = None
            continue
        ca = np.stack([(A[:, 1] + A[:, 3]) / 2, (A[:, 0] + A[:, 2]) / 2], 1)
        cb = np.stack([(B[:, 1] + B[:, 3]) / 2, (B[:, 0] + B[:, 2]) / 2], 1)
        mlat = np.radians((ca[:, 0].mean() + cb[:, 0].mean()) / 2)
        dy = (ca[:, None, 0] - cb[None, :, 0]) * 111.32
        dx = (ca[:, None, 1] - cb[None, :, 1]) * 111.32 * np.cos(mlat)
        d = np.hypot(dx, dy)
        prox[f"{a}_{b}"] = {
            "min_centroid_km": float(d.min()),
            "pairs_under_50km": int((d < MIN_GEO_DISTANCE_KM).sum()),
            "n_pairs": int(d.size),
        }
    leak["geographic_proximity"] = prox
    leak["temporal"] = "UNAVAILABLE"
    leak["temporal_reason"] = (
        "source corpus carries no acquisition timestamps; no temporal leakage test "
        "can be performed and none is claimed"
    )

    for k in ("scene_identity", "content_duplication", "footprint_overlap"):
        print(f"  {k:22s}: {leak[k]}")
    for k, v in prox.items():
        if v:
            print(f"  proximity {k:14s}: min={v['min_centroid_km']:.1f} km, "
                  f"{v['pairs_under_50km']}/{v['n_pairs']} pairs < {MIN_GEO_DISTANCE_KM} km")
    print(f"  {'temporal':22s}: UNAVAILABLE (no timestamps in source)")

    if leak["failures"]:
        print("\n[FATAL] LEAKAGE DETECTED - stopping before Gold generation")
        for f in leak["failures"]:
            print(f"  {f}")
        (OUT / "02_leakage.json").write_text(json.dumps(leak, indent=2))
        return 3

    out = {
        "n_audited": len(records),
        "n_quarantined": len(quarantined),
        "quarantined": [{"scene_id": r["scene_id"], "failures": r["failures"]} for r in quarantined],
        "dedup": dd,
        "pool_size": len(pool),
        "pool_by_source": dict(Counter(r["source"] for r in pool)),
        "grouping": {
            "key": "footprint_overlap_component",
            "n_components": n_comp,
            "region_deg": REGION_DEG,
            "n_regions": len(region_sizes),
            "regions_per_split": dict(region_counts),
        },
        "split": {
            "strategy": "geographic_region_stratified",
            "seed": SEED,
            "ratios": [TRAIN_RATIO, VAL_RATIO, TEST_RATIO],
            "counts": dict(counts),
            "region_assignment": region_split,
            "scene_split": scene_split,
        },
        "leakage": leak,
    }
    (OUT / "02_dedup_split.json").write_text(json.dumps(out, indent=2))
    print(f"\n[DONE] wrote {OUT / '02_dedup_split.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
