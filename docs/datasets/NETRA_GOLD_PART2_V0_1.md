# NETRA_GOLD_PART2_V0_1

## Source
- **Dataset**: Zenodo Part II (Oil Spill Detection Dataset)
- **Categories**: Lookalike, No_Oil
- **Status**: EXPERIMENTAL / UNVALIDATED
- **Dataset Version**: NETRA-GOLD-PART2-v0.1

## Archives
- 01_Train_Val_Lookalike_images.7z (SHA256: 62ee4edf05abcfc08a5e78e89534e5e427d9573df0c9241d754f73b3370bd32d)
- 01_Train_Val_Lookalike_mask.7z (SHA256: ac0a6aa66005e623c39e0b562df19e69c03c802ae146d55a427e44aa0d2495e2)
- 01_Train_Val_No_Oil_Images.7z (SHA256: 0d851e3d35cff0a87458ce1eb1d6ff50e89bf79f7108d770b3b8986d899b4de8)
- 01_Train_Val_No_Oil_mask.7z (SHA256: 52a07257bf4bc608810b78094205e8e214d13be28edd1da82363adcb7e63d8cf)

## Image and Mask Properties
- **Images**: Sentinel-1 SAR (GRD), 2048x2048, 2 channels (VV, VH), Float32. EPSG:4326. Resolution ~10m.
- **Masks**: 2048x2048, 1 channel, UInt8. Value `0` denotes background (not oil).
- **Label Semantics**: Part II represents negative classes. Lookalike & No_Oil contain absolutely zero positive pixels (all zeroes). 
- **Gold Semantics**: `OIL = 1`, `NOT_OIL = 0`. Both categories map to `NOT_OIL`.

## Deduplication and Pairing
- **Pairing Rule**: Direct exact filename matching mapping images to masks.
- **Dedup Policy**: Exact Image Hash + Exact Mask Hash -> Duplicate. Same Image + Different Mask -> Preserve.
- **Results**: 1370 total pairs discovered. 708 pairs accepted as unique. 662 pairs were mathematically exact duplicates (memorization) and successfully quarantined by DataGuard.

## Quality and Splitting
- **Split Strategy**: `hash_random` (DEVELOPMENT SPLIT ONLY)
- **LeakageGuard**: Temporal and Spatial leakage checks marked as *Unavailable* (timestamps natively absent). Exact content duplicate leakage prevented perfectly by DataGuard.
- **Tiling**: Split first, tile second. Images tiled into 512x512 non-overlapping sections.

## Normalization and Distribution
- **Normalization**: Standard `p2`/`p98` clipping and scaling computed **STRICTLY ON TRAIN SPLIT** via randomized subset Welford sampling (to prevent OOM). 
- **Train-only constraint**: Passed.
- **Distribution**:
  - Total Accepted Scenes: 708
  - Lookalike: 357 scenes (5712 tiles)
  - No_Oil: 351 scenes (5616 tiles)
  - Oil tiles: 0
  - Empty-oil tiles: 11,328 (100% negatives)

## Generation
- **Output Size**: 11,328 Tensors
- **Train/Val/Test**: 9072 / 1280 / 976
- **DataLoader**: Successfully verified shape `[B, 2, 512, 512]` via PyTorch.

## Known Limitations
- Does not contain explicit temporal/timestamp metadata (acquisition_time=null).
- Spatial Generalization not guaranteed across splits due to `hash_random`.
- 100% negative imbalance; this dataset **MUST** be merged with Part I for actual training.
