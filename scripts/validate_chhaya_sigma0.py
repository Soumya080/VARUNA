"""
VARUNA GRID — CHHAYA sigma0 vs NETRA-normalized suitability report (Phase 5A).

Answers, per tile per product, at thresholds 4/5/6/7/8 sigma: is this tile's
peak signal above the mean high enough for CA-CFAR to have ANY chance of
firing at that threshold? This is the honest measurement Phase 5A's success
criterion depends on — "CFAR is now physically capable of firing", provable
here, NOT "CFAR found a ship" (a separate, genuine experiment; see
`build_mc20_chhaya_sigma0.py`'s module docstring).

Writes reports/chhaya_v2/CHHAYA_SIGMA0_SUITABILITY_REPORT.md.

Usage: python scripts/validate_chhaya_sigma0.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

import numpy as np  # noqa: E402

THRESHOLDS = [4.0, 6.0, 8.0, 15.0, 30.0]

PRODUCTS = {
    "netra_normalized (existing)": {
        "tile_records": REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1" / "sar" / "tile_records.json",
        "tile_dir": REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1" / "sar" / "tiles",
        "channel_order": ["VV_norm", "VH_norm"],  # apply_netra_normalization's real return order
        "is_db": False,
    },
    "sigma0 (Phase 5A, new)": {
        "tile_records": REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1_sigma0" / "sar" / "tile_records.json",
        "tile_dir": REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1_sigma0" / "sar" / "tiles",
        "channel_order": ["VV_db", "VH_db"],
        "is_db": True,
    },
}


def peak_sigma_above_mean(vh: np.ndarray) -> float:
    valid = vh[np.isfinite(vh)]
    if valid.size == 0:
        return float("nan")
    mean, std = float(valid.mean()), float(valid.std())
    if std <= 0:
        return float("nan")
    return float((valid.max() - mean) / std)


def main() -> None:
    rows = []
    for product_name, cfg in PRODUCTS.items():
        tr_path = cfg["tile_records"]
        if not tr_path.exists():
            rows.append((product_name, None, None, "MISSING — build script not yet run"))
            continue
        records = json.loads(tr_path.read_text(encoding="utf-8"))
        vh_index = cfg["channel_order"].index(
            next(c for c in cfg["channel_order"] if "VH" in c)
        )
        for rec in records:
            tile_id = rec["tile_id"]
            arr_path = cfg["tile_dir"] / f"{tile_id}.npy"
            if not arr_path.exists():
                rows.append((product_name, tile_id, None, "tile array missing on disk"))
                continue
            arr = np.load(arr_path)
            vh = np.asarray(arr[vh_index] if arr.ndim == 3 else arr, dtype=np.float32)
            if cfg["is_db"]:
                # Match apps/api/routers/chhaya.py's investigate() exactly:
                # CACFARDetector assumes non-negative linear amplitude, so
                # the router converts dB back to linear before detection.
                # This report must measure what CFAR actually sees, not the
                # raw dB array — the two peak-sigma numbers differ a lot
                # (exponentiating amplifies a bright pixel's separation from
                # the background far more than dB units do).
                mask_path = cfg["tile_dir"] / f"{rec['tile_id']}__valid_mask.npy"
                valid = np.load(mask_path) if mask_path.exists() else None
                vh_linear = np.power(10.0, np.nan_to_num(vh, nan=-100.0) / 10.0)
                if valid is not None:
                    vh_linear = np.where(valid, vh_linear, 0.0)
                vh = vh_linear.astype(np.float32)
            peak = peak_sigma_above_mean(vh)
            fires = {t: (peak >= t) for t in THRESHOLDS}
            rows.append((product_name, tile_id, peak, fires))

    lines = [
        "# CHHAYA sigma0 suitability report",
        "",
        "Peak-signal-above-mean (in sigma units) per tile per product, and whether",
        "CA-CFAR is physically CAPABLE of firing at each threshold. This measures",
        "capability, not detection — a tile that clears the threshold may still",
        "genuinely contain zero vessels.",
        "",
        "| Product | Tile | Peak sigma above mean | Fires @4σ | @6σ | @8σ | @15σ | @30σ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for product_name, tile_id, peak, fires in rows:
        if tile_id is None:
            lines.append(f"| {product_name} | — | — | {fires} | | | | |")
            continue
        if isinstance(fires, str):
            lines.append(f"| {product_name} | {tile_id} | — | {fires} | | | | |")
            continue
        cells = " | ".join("YES" if fires[t] else "no" for t in THRESHOLDS)
        peak_str = f"{peak:.2f}" if peak == peak else "nan"
        lines.append(f"| {product_name} | {tile_id} | {peak_str} | {cells} |")

    out_dir = REPO_ROOT / "reports" / "chhaya_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "CHHAYA_SIGMA0_SUITABILITY_REPORT.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    # Windows consoles often default to cp1252, which can't encode sigma
    # (U+03C3) — never let the report print crash after the file itself
    # (UTF-8) was already written successfully.
    try:
        print("\n".join(lines))
    except UnicodeEncodeError:
        print("\n".join(lines).encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    main()
