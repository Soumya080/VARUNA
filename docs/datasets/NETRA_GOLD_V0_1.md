> [!CAUTION]
> **SUPERSEDED AND PARTLY INCORRECT. Retained unchanged below for audit purposes.**
>
> This document describes NETRA-GOLD-v0.1. It is superseded by
> [`NETRA_GOLD_V0_2.md`](NETRA_GOLD_V0_2.md). Two of its claims are factually
> wrong and are corrected here rather than edited out of the text below.
>
> **Correction 1 - the 826 "duplicates" were not duplicates.**
> Section 3 states *"Duplicates (MD5/SHA256 Match): 826"*. No MD5 or SHA-256
> comparison was ever performed: `DedupPipeline.process()` compared sensor,
> platform, a 60-second time window and bounding-box intersection. Because every
> Part I scene carried the same placeholder timestamp, the rule collapsed to a
> bare footprint-overlap test.
>
> A forensic re-run over all 1,200 pairs (`reports/netra_v02/01_source_audit.jsonl`)
> found **1,198 of 1,200 bounding boxes distinct** and **1,197 of 1,200 file sizes
> distinct**. Under a genuine content-hash rule there is exactly **one** exact
> duplicate pair in Part I (`00356` / `00357`). The corrected pipeline retains
> **1,199 of 1,200 Part I scenes, not 374** - a 3.2x recovery of training data
> that v0.1 discarded to a bug.
>
> **Correction 2 - geospatial metadata was available; only temporal was missing.**
> The warning in section 1 attributes the LeakageGuard bypass to *"the lack of
> accurate geospatial and temporal metadata"*. Every Part I GeoTIFF carries a real
> EPSG:4326 transform and real bounds, and the pipeline already derived 47 working
> region bins from them. A geographic split and a geographic leakage check were
> both available and were simply not used. Only the **temporal** metadata is
> genuinely absent, and it remains absent in v0.2, where it is reported as
> `UNAVAILABLE` rather than as a pass.
>
> **Also note - the normalization statistics below were set by nodata, not signal.**
> The frozen record gives `VV.p98 = 0.0` and `VH.p98 = 0.0`. Roughly 2.6% of
> pooled train pixels are exactly zero (land/border fill), which is just past the
> 98th-percentile threshold, so the statistic measured the fill rather than the
> backscatter. Recomputed over valid pixels only, the real values are
> `VV.p98 = -13.83 dB` and `VH.p98 = -7.52 dB`.
>
> **No model was ever trained on this dataset.** See
> [`artifacts/experiments/INVALID.md`](../../artifacts/experiments/INVALID.md).
>
> The v0.1 Gold tiles at `data/gold/netra/` are retained on disk as historical
> evidence and are not used by any current training path.

---

# Dataset Release: NETRA-GOLD-v0.1

**Scientific Status**: EXPERIMENTAL / UNVALIDATED
**Generated Date**: 2026-08-28
**Source Pipeline**: VARUNA GRID v2 (`scripts/build_zenodo_part1_gold.py`)

## 1. Overview
The `NETRA-GOLD-v0.1` dataset is the first baseline dataset prepared for training the VARUNA NETRA model. It is derived entirely from the Zenodo Part I SAR Oil Spill Dataset.

The pipeline executes standard Data Engineering Quality Gates, Deduplication, hash-based splitting, spatial tiling, and global channel normalization. 

**This split represents a DEVELOPMENT split ONLY.**

> [!WARNING]
> Due to the lack of accurate geospatial and temporal metadata in the raw source, spatial and temporal LeakageGuard constraints were bypassed in favor of a simplistic `hash_random` split, grouped strictly by `scene_id`. Consequently, test metrics obtained on this split do not strictly validate geographical or temporal generalization.

## 2. Technical Specifications
- **Sensor**: Sentinel-1 (C-band)
- **Channels**: 2 (VV, VH)
- **Classes**: 2 (Background, Oil Slick)
- **Spatial Dimension**: 512x512 pixels
- **Data Type**: Float32 (Imagery), UInt8 (Mask)
- **Split Strategy**: `hash_random` (DEVELOPMENT split)

## 3. Pipeline Metrics

### Scene-Level Breakdown
The pipeline consumed the extracted scenes from the Zenodo dataset, running full DataGuard, deduplication, and quality evaluation on all pairs:

- **Total Pairs Analyzed**: 1,200
- **Accepted for Training**: 374
- **Quarantined**: 826
  - **Quality Rejected**: 0
  - **Duplicates (MD5/SHA256 Match)**: 826

### Tile-Level Yield
Upon successfully passing deduplication, the 374 accepted scenes were tiled into 512x512 multi-channel slices:

- **Total GOLD Tile Pairs**: 5,984
- **Train Split**: 4,704
- **Validation Split**: 784
- **Test Split**: 496

## 4. Normalization Statistics
Global channel normalization was strictly computed on the `train` split. The derived statistics were frozen and systematically applied uniformly to `val` and `test` data. 
*(Specific normalization factors are baked into the generated manifest)*.

## 5. Metadata and Provenance
All dummy timestamps used for internal pipeline compatability were strictly flagged with `metadata.timestamp_status = "unavailable"`, ensuring they do not leak into downstream temporal scientific logic.

Full dataset providence and precise cryptographic checksums for every split tile are maintained in `data/manifests/zenodo_part1_manifest.json`.
