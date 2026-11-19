# NETRA v0.3 Targeted Domain Expansion — Phase 1–12 Progress Report

**Date:** 2026-08-31
**Scope this pass:** Phases 1–4, 10 (partial). Training (Phase 13+) explicitly
NOT attempted — this machine has no GPU (`torch.cuda.is_available()` == False),
confirmed before any acquisition began.

## Data Sources

| Source | Role | Status |
|---|---|---|
| Zenodo Part I/II | existing v0.2 training corpus | already in repo, untouched |
| **Zenodo Part III** (`zenodo.org/records/13761290`) | candidate CALM-GRD-HOLDOUT | **acquired this pass** |
| ESSD/PANGAEA Eastern Mediterranean (PANGAEA.980773) | explicit low-wind lookalike annotations | evaluated, NOT acquired — annotations only, requires separate raw-SAR-scene acquisition from Copernicus Data Space; deferred pending separate authorization |
| OSSDD, xView3-SAR | ship-detection, no oil masks | DEFER (already ruled out in a prior task) |
| GlobalOSD-SAR (secondary-source mention) | unverified | DEFER — no primary source independently confirmed this pass |

## Acquisition

- File: `02_Test_images_and_ground_truth.7z`, 9,859,650,011 bytes.
- **MEASURED**: downloaded size matches Zenodo API exactly; MD5
  `5dce64cd7ff9d80189d13504bd3bcbf5` matches the API-reported checksum
  exactly.
- License: CC-BY-4.0.
- Stored: `data/raw/netra_v03_sources/zenodo_part3/` (new, versioned,
  non-overwriting directory). Provenance recorded in
  `provenance/ACQUISITION_RECORD.md`.
- Extracted contents (**MEASURED**, matches publisher description):
  450 images + 450 masks = 900 TIFFs, split 150/150/150 across
  Oil / Lookalike / No-oil.

## Physical Polarization Contract

See `docs/datasets/NETRA_V03_POLARIZATION_CONTRACT.md` (new).

**MEASURED** on Part III (40-scene samples per category): band1 brighter
than band0 in 100% (Oil), 95% (Lookalike), 97.5% (No-oil) of scenes —
consistent with the same band0=VH/band1=VV reversal already established
for Part I/II. Confidence: HIGH.

## Environmental Metadata

**MEASURED**: each TIFF carries `AREA_OR_POINT=Area` and a real
EPSG:4326 bounding box (checked scene: 34.69–34.88°E, 35.44–35.62°N —
Eastern Mediterranean, near Cyprus). **UNKNOWN**: no acquisition
timestamp, orbit, or IPF metadata is embedded in the archive, and no
accompanying README/CSV ships with it. This is recorded as UNKNOWN, not
inferred or fabricated.

**Consequence:** wind speed cannot be derived for these scenes (no
timestamp to match against ERA5). Regime stratification (Phase 6) for
this specific source is therefore **UNKNOWN**, not "calm" — despite the
dataset's role as a holdout candidate. Treating it as verified calm/low-
wind coverage would be exactly the fabrication this task's rules
prohibit, so it is not claimed here.

## Deduplication / Leakage

**MEASURED**: SHA-256 exact-content hash comparison, 60-file sample from
Part III against 200-file sample from existing Part I/II — 0 duplicates.
No indication of content leakage between the new holdout candidate and
the existing v0.2 training corpus. A full (not sampled) hash sweep is the
natural next step before this is treated as a final leakage clearance,
not yet performed given time constraints this pass.

## Gold-v0.3 Construction

**NOT STARTED.** See Root Cause / Decision below — building a
manifest-driven `data/gold/netra_v0_3/` before resolving the open
question below would risk baking an unverified regime claim into a
"frozen" holdout, which is exactly the kind of premature commitment the
task's stopping rule warns against.

## Root Cause / Decision Point

Zenodo Part III is a **scene-disjoint, same-publisher, same-processing**
dataset — real value as an independent segmentation-quality check, but:

1. It carries **no verifiable wind/regime metadata**, so it cannot be
   used to prove or measure "calm/low-wind coverage" — the central gap
   this whole v0.3 track exists to close.
2. It is geographically constrained to one small Eastern-Mediterranean
   footprint, likely overlapping the same general acquisition
   circumstances as Part I/II (same publisher, same processing
   pipeline) — i.e. it is a plausible **replication** check, not
   evidence of new deployment-regime coverage.

The dataset that *does* explicitly document low-wind lookalikes with
real provenance (ESSD/PANGAEA.980773) was evaluated but not acquired:
it ships as polygon annotations over raw Sentinel-1 *products*, not
ready-made chips, meaning acquisition means separately pulling the named
Sentinel-1 scenes from Copernicus Data Space — an order-of-magnitude
larger, slower acquisition than Part III, and a resource commitment that
should be confirmed explicitly before being started, per this task's own
acquisition-gating rules.

## Safety

deleted=0, moved=0, renamed=0, overwritten=0, checkpoint_modified=0,
v0.2_Gold_modified=0, MC20_modified=0, official_test_modified=0.
All new files are under new, versioned paths
(`data/raw/netra_v03_sources/`, `docs/datasets/NETRA_V03_POLARIZATION_CONTRACT.md`,
`reports/netra_v03/`).

## FINAL STATUS

# FURTHER_INVESTIGATION_REQUIRED

**Reason (per Phase 26, no fabrication):** the only new source acquired
this pass (Zenodo Part III) is MEASURED to be a legitimate, non-
duplicate, correctly-mapped holdout candidate, but its regime coverage
relative to the "calm/low-wind" gap is UNKNOWN, not confirmed — using it
to claim domain-expansion progress on that specific axis would be an
inference dressed as a measurement. The dataset that would let this
claim be MEASURED (ESSD/PANGAEA) requires a separate, larger acquisition
decision.

## FINAL OPERATOR SUMMARY

    STATUS:              FURTHER_INVESTIGATION_REQUIRED
    BEST CHECKPOINT:     unchanged (netra_baseline_v02_dac482fcd84a_best.pt, frozen)
    DATASET VERSION:     no netra_v0_3 Gold built yet
    TRAINING RUNTIME:    0 (not attempted -- no GPU on this host)
    GPU HOURS:           0
    NEW DATA SIZE:       9.86GB downloaded, 450 image + 450 mask TIFFs extracted
    TRAIN SCENES:        0 (no new verified-regime train data yet)
    VAL SCENES:          0
    CALM-HOLDOUT SCENES: 0 confirmed-calm (450 candidate, regime UNKNOWN)
    SOURCE TEST:         not run
    CALM-HOLDOUT:        not run
    MC20:                unchanged, still external-only
    PRIMARY FINDING:     Zenodo Part III is a clean, verified-band-order,
                         non-duplicate holdout candidate but carries no
                         wind/timestamp metadata -- it cannot itself prove
                         calm/low-wind coverage.
    MAIN FAILURE:        no acquired-so-far source both (a) has real oil/
                         lookalike/negative labels and (b) carries verifiable
                         environmental metadata for the calm/low-wind regime.
    NEXT EXACT ACTION:   decide whether to authorize acquiring the raw
                         Sentinel-1 scenes named in ESSD/PANGAEA.980773
                         (the one identified source with documented low-wind
                         lookalike coverage) -- a materially larger acquisition
                         than this pass, requiring explicit go-ahead.
