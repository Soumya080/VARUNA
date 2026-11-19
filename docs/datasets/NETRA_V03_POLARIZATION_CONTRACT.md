# NETRA v0.3 Physical Polarization Contract

**Status:** in force for all NETRA-GOLD-v0.3 ingestion. Supersedes silent
filename-based inference. Every source integrated into v0.3 MUST declare
the two fields below before any tile is written to Gold.

## Canonical v0.3 channel convention

    channel 0 = VH (cross-polarized)
    channel 1 = VV (co-polarized)

This is the frozen v0.2 model's *learned* convention (see
`reports/netra_v02/NETRA_SMART_FIX_FINAL.md`), carried forward for v0.3 so
that a v0.2→v0.3 comparison is not confounded by a channel-order change.
It is a convention choice, not a law of physics — any *new* source's raw
band order must still be independently verified against it, never assumed.

## Required per-source declaration

| Field | Meaning | Must be MEASURED, never guessed |
|---|---|---|
| `source_band` | which raw file/band index the image comes from | yes |
| `physical_polarization` | VV or VH, verified independently of filename | yes |

## Verification method (mandatory per source, not per file)

A source's band→polarization mapping is accepted only after:

1. Reading the source's own documentation/metadata for its *stated*
   band order, AND
2. Independently checking a deterministic sample of real scenes for the
   physical signature that co-pol (VV) is brighter than cross-pol (VH)
   over open water / non-target background — the same method used to
   catch the Zenodo Part I/II reversal (100% consistency required; a
   study is inconclusive, not confirmatory, if it produces less than
   ~95–100% agreement on a same-conditions, non-target sample).

If (1) and (2) disagree, (2) governs, and the disagreement is recorded
explicitly — never silently reconciled.

## Sources declared so far

| Source | source_band → physical_polarization | Verification | Confidence |
|---|---|---|---|
| Zenodo Part I / II (already in NETRA-GOLD-v0.2 training) | raw band 0 = VH, raw band 1 = VV | MEASURED: 100% brightness-reversal across 120 real scenes, 3 sub-corpora (Smart-Fix investigation) | HIGH |
| Zenodo Part III (`zenodo.org/records/13761290`) | raw band 0 = VH, raw band 1 = VV (same as Part I/II) | MEASURED: band1>band0 in 40/40 Oil (100%), 38/40 Lookalike (95%), 39/40 No-oil (97.5%) real scenes; mean gaps +7.8/+5.1/+7.7 dB respectively. Slightly below Part I/II's 100% because Lookalike/No-oil scenes have inherently lower VV/VH contrast — expected physical variance, not a labeling ambiguity | HIGH |

| ESSD/PANGAEA raw GRD (`data/raw/netra_v03_sources/essd_grd/`) | filename-declared: `*-vv-*.tiff` = VV, `*-vh-*.tiff` = VH (official ESA/Copernicus IPF product naming, not inferred) | MEASURED, two independent ways: (1) filename convention is the standard Sentinel-1 GRD product naming, authoritative by construction; (2) sanity-checked on scene `...016468_01EFFB_A41B`: mean DN VV=69.6 > VH=29.5, matching physical expectation | HIGH — this source needs no `resolve_frozen_v0_2_channel_binding()`-style correction; each polarization ships in its own correctly-named file |

## Enforcement

- No v0.3 Gold tile may be written until its source row exists in the
  table above with a non-UNVERIFIED confidence.
- `resolve_frozen_v0_2_channel_binding()` (from
  `packages/varuna_data_eng/preprocessing/sentinel1_grd_calibration.py`)
  remains the mechanism for correcting a source whose raw file order is
  the reverse of this contract's channel 0/1 convention. It is applied
  per-source based on the table above, never applied blindly.
