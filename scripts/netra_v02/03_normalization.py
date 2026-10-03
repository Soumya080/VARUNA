"""
NETRA-GOLD-v0.2 | Stage 03 - Nodata-aware, train-only normalization (Phase 10).

The v0.1 record carried `VV.p98 = 0.0` and `VH.p98 = 0.0`. That was not a
backscatter percentile: ~2.7% of pooled train pixels are exactly 0.0 zero-fill
(land/border), which is just past the 98th-percentile threshold, so the
statistic was being set by nodata rather than by signal. It was also
discontinuous - a small change in corpus composition flips p98 from 0.0 to
about -26 dB and rescales every tile.

This stage recomputes the statistics over VALID pixels only:

    valid  <=>  finite  AND  NOT (VV == 0.0 AND VH == 0.0)

Statistics are computed on the TRAIN split alone and then frozen. The same
frozen record is applied verbatim to val and test; nothing is ever recomputed
per split.

Percentiles come from a 0.05 dB histogram over [-80, +40] dB, which is exact to
the bin width and streams in constant memory.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "reports" / "netra_v02"

DB_MIN, DB_MAX, DB_STEP = -80.0, 40.0, 0.05
NBINS = int(round((DB_MAX - DB_MIN) / DB_STEP))
CHANNELS = ("VV", "VH")
NORMALIZATION_VERSION = "netra-norm-v0.2-nodata-excluded"


class ChannelAccumulator:
    def __init__(self) -> None:
        self.hist = np.zeros(NBINS, dtype=np.int64)
        self.n = 0
        self.sum = 0.0
        self.sumsq = 0.0
        self.vmin = float("inf")
        self.vmax = -float("inf")
        self.n_below = 0
        self.n_above = 0

    def update(self, v: np.ndarray) -> None:
        if v.size == 0:
            return
        self.n += int(v.size)
        v64 = v.astype(np.float64)
        self.sum += float(v64.sum())
        self.sumsq += float((v64 * v64).sum())
        self.vmin = min(self.vmin, float(v.min()))
        self.vmax = max(self.vmax, float(v.max()))
        idx = np.floor((v64 - DB_MIN) / DB_STEP).astype(np.int64)
        self.n_below += int((idx < 0).sum())
        self.n_above += int((idx >= NBINS).sum())
        np.clip(idx, 0, NBINS - 1, out=idx)
        self.hist += np.bincount(idx, minlength=NBINS)

    def merge(self, other: "ChannelAccumulator") -> None:
        self.hist += other.hist
        self.n += other.n
        self.sum += other.sum
        self.sumsq += other.sumsq
        self.vmin = min(self.vmin, other.vmin)
        self.vmax = max(self.vmax, other.vmax)
        self.n_below += other.n_below
        self.n_above += other.n_above

    def percentile(self, q: float) -> float:
        if self.n == 0:
            return float("nan")
        target = q / 100.0 * self.n
        c = np.cumsum(self.hist)
        i = int(np.searchsorted(c, target, side="left"))
        i = min(i, NBINS - 1)
        return DB_MIN + (i + 0.5) * DB_STEP

    def stats(self) -> dict:
        mean = self.sum / self.n if self.n else float("nan")
        var = (self.sumsq / self.n - mean * mean) if self.n else float("nan")
        return {
            "n_valid_px": self.n,
            "mean": mean,
            "std": float(np.sqrt(max(var, 0.0))),
            "min": self.vmin,
            "max": self.vmax,
            "p1": self.percentile(1),
            "p2": self.percentile(2),
            "p50": self.percentile(50),
            "p98": self.percentile(98),
            "p99": self.percentile(99),
            "hist_underflow_px": self.n_below,
            "hist_overflow_px": self.n_above,
        }


def scene_accumulate(path: Path) -> tuple[ChannelAccumulator, ChannelAccumulator, int, int]:
    accs = (ChannelAccumulator(), ChannelAccumulator())
    with rasterio.open(path) as src:
        arr = src.read().astype(np.float32)
    finite = np.isfinite(arr).all(axis=0)
    nodata = (arr[0] == 0.0) & (arr[1] == 0.0)
    valid = finite & ~nodata
    for i in range(2):
        accs[i].update(arr[i][valid])
    return accs[0], accs[1], int(valid.sum()), int(valid.size)


def main() -> int:
    split_file = OUT / "02_dedup_split.json"
    if not split_file.exists():
        raise SystemExit(f"[FATAL] stage 02 output missing: {split_file}")
    split_info = json.loads(split_file.read_text(encoding="utf-8"))
    scene_split = split_info["split"]["scene_split"]

    audit = [json.loads(l) for l in (OUT / "01_source_audit.jsonl").read_text(encoding="utf-8").splitlines() if l]
    by_id = {r["scene_id"]: r for r in audit}

    train_ids = sorted(s for s, sp in scene_split.items() if sp == "train")
    paths = [REPO / by_id[s]["image_path"] for s in train_ids]
    print(f"[INFO] computing normalization from {len(paths)} TRAIN scenes only")
    print(f"[INFO] valid pixel rule: finite AND NOT (VV==0 AND VH==0)")

    total = [ChannelAccumulator(), ChannelAccumulator()]
    valid_px = 0
    all_px = 0
    t0 = time.perf_counter()
    done = 0
    with ThreadPoolExecutor(6) as ex:
        for a_vv, a_vh, v, n in ex.map(scene_accumulate, paths):
            total[0].merge(a_vv)
            total[1].merge(a_vh)
            valid_px += v
            all_px += n
            done += 1
            if done % 100 == 0:
                el = time.perf_counter() - t0
                print(f"  {done}/{len(paths)}  {el:6.0f}s  {done / el:5.2f} scenes/s", flush=True)

    channels = {}
    for i, ch in enumerate(CHANNELS):
        s = total[i].stats()
        s["clip_low"] = s["p2"]
        s["clip_high"] = s["p98"]
        channels[ch] = s

    record = {
        "normalization_version": NORMALIZATION_VERSION,
        "method": "clip_p2_p98_then_scale_unit",
        "formula": "x_norm = (clip(x, p2, p98) - p2) / (p98 - p2); nodata pixels forced to 0.0",
        "computed_from_split": "train",
        "n_train_scenes": len(paths),
        "valid_pixel_rule": "finite AND NOT (VV == 0.0 AND VH == 0.0)",
        "nodata_excluded": True,
        "valid_px": valid_px,
        "total_px": all_px,
        "nodata_frac": 1.0 - (valid_px / all_px if all_px else 0.0),
        "hist_bin_db": DB_STEP,
        "channels": channels,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    (OUT / "03_normalization.json").write_text(json.dumps(record, indent=2))

    print("\n[NORMALIZATION - TRAIN ONLY, NODATA EXCLUDED]")
    print(f"  nodata fraction over train pixels : {record['nodata_frac']:.4%}")
    for ch in CHANNELS:
        c = channels[ch]
        print(f"  {ch}: p2={c['p2']:.2f} dB  p50={c['p50']:.2f} dB  p98={c['p98']:.2f} dB  "
              f"mean={c['mean']:.2f}  std={c['std']:.2f}  min={c['min']:.2f}  max={c['max']:.2f}")
        if abs(c["p98"]) < 1e-6:
            print(f"  [FATAL] {ch} p98 is still 0.0 - nodata exclusion did not take effect")
            return 4
    print(f"\n[DONE] wrote {OUT / '03_normalization.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
