# NETRA-GOLD-v0.3-CANDIDATE — Dataset Card

**Status:** EXPERIMENTAL. Suitable for a weak-label domain-expansion
**pilot** only. Not a segmentation benchmark, not production NETRA.

## Source
- **PANGAEA.980773** (Yang & Singha 2025), supplement to ESSD 17, 6807–6837.
- 25 original Sentinel-1 **IW GRDH 1SDV** scenes, re-acquired from
  Copernicus Data Space (not the packaged JPGs), 43.80 GB, 25/25
  MD5-verified against the CDSE catalogue.
- License CC-BY-4.0 (annotations) + Copernicus Sentinel Data Terms.
- Region: Eastern Mediterranean Sea. Year: 2019 only.

## Content
| Split | Tiles | Scenes | OIL | NEG/LOOKALIKE | Wind |
|---|---|---|---|---|---|
| train | 217 | 8 | 179 | 38 | 111 low / 106 medium |
| val | 81 | 3 | 58 | 23 | 81 low |
| **CALM-GRD-HOLDOUT** | 217 | 8 | 187 | 30 | 217 low |
| excluded (proximity) | 77 | — | — | — | — |
| excluded (duplicate) | 8 | — | — | — | — |

Tiles are 512×512, 2-channel float32 Sigma0 dB, **channel 0 = VH,
channel 1 = VV** (per `NETRA_V03_POLARIZATION_CONTRACT.md`; matches what
the frozen v0.2 checkpoint actually learned). Final Gold size 1.80 GB.

## Labels
`WEAK_BOX` for every sample — see `NETRA_V03_LABEL_POLICY.md`. Measured
~62.3% of box-interior pixels are not plausibly oil, so box interiors are
supplied as **ignore regions**, not positives. No confirmed positive
pixels exist in this dataset.

## Verification performed
- Coordinate chain proven 3 ways (grid round-trip err 5e-13 px; 0/687
  out-of-bounds; geodetic-vs-pixel scale ratio 0.99).
- **Independent alignment check: box regions are darker than their
  surroundings in 98.2% of oil tiles (t=−35.9, p≈0)** — the boxes land on
  genuinely oil-like dark pixels in the raw scenes.
- VV brighter than VH in 25/25 scenes.
- ERA5 wind joined per scene from a real CDS API pull.

## Leakage
Exhaustive: all **3,020** Zenodo Part I/II/III tiles' footprints checked
(not a sample). 15/25 scenes fall within 15 km of some Zenodo tile.
**Holdout: 0/8 flagged** (6 scenes were removed from holdout when the
exhaustive check superseded the earlier sampled one). Train 6/8 and
**val 3/3 are flagged** — see Limitations. Cross-split duplicates: 0.
MC20 geographically disjoint. Part III read-only.

## Known limitations
1. **No confirmed positive pixels.** Cannot alone train positive
   segmentation; must be paired with v0.2's strong masks.
2. **Val is proximity-contaminated (3/3 scenes).** Val-based model
   selection is biased toward the v0.2 source domain. The CALM-GRD-HOLDOUT
   is the trustworthy evaluation surface.
3. Single region, single year — no geographic/seasonal diversity.
4. Negative and look-alike semantics are combined, not separable.
5. 8 train scenes is small; results will be noisy.

## Intended use
NETRA-v0.3 **DOMAIN-EXPANSION PILOT**: "does exposure to the new
low-wind GRD domain improve frozen-architecture model behavior?"
Not for: accuracy claims, benchmark comparison, production deployment.

## Prohibited use
Never for tuning against MC20 or Zenodo Part III. The CALM-GRD-HOLDOUT
must never be used for training, normalization, early stopping, or model
selection.
