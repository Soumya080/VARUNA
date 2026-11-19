# ADR-0011: Preprocessing Compatibility — Verified, Channel-Binding Gap Flagged Separately

**Status:** Accepted
**Date:** 2026-09-02
**Session:** VARUNA_PRODUCT_READY hardening, Phase 4C

## Context

`docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md` §8 named preprocessing
compatibility between the live inference path and the frozen NETRA v0.2
checkpoint as *"the single most consequential gap this reconciliation surfaced
without closing"* — because an incompatible preprocessing pipeline would
explain a null detection as cleanly as a genuine out-of-domain scene, and
nothing previously distinguished the two.

## What was verified (empirically, this session)

**1. Normalization statistics.** `apply_netra_normalization()` in
`packages/varuna_data_eng/preprocessing/sentinel1_grd_calibration.py` clips and
scales using `clip_low`/`clip_high` read directly from
`data/manifests/netra_gold_v0_2.json::normalization.channels.{VV,VH}` — the
exact statistics computed over the training split, not scene-local or
re-derived values. `scripts/build_mc20_event_gold.py` calls this function with
those stats verbatim (line ~192-200). Confirmed by direct comparison of
Gold-v0.2-val tiles (n=40) against MC20 tiles (n=9): identical shape `(2, 512,
512)`, identical dtype `float32`, identical `[0, 1]` range, identical
near-zero fraction (~1-2%). MC20's std (0.29) is roughly 2.75× Gold-val's
(0.11) — consistent with genuine scene content difference (open water vs.
mixed training corpus), not a normalization defect.

**2. Channel-binding fix — real defect, empirically inconsequential for MC20.**
`resolve_frozen_v0_2_channel_binding()` in the same file documents a verified
VV/VH channel-swap in the checkpoint's training data (100% reversal across 120
sampled scenes, physically implausible for natural ocean surfaces unless
systematic). It has **zero callers anywhere in the repository** —
`build_mc20_event_gold.py` reads `vv_tiff`/`vh_tiff` directly by filename and
feeds them to `apply_netra_normalization(vv_db, vh_db, vv_stats, vh_stats)`
with no swap, which is exactly the mismatched pairing the fix's own docstring
describes as the bug.

A non-destructive diagnostic (`scratchpad/diag_channel_binding.py`, read-only,
writes only to scratch, no frozen asset touched) re-derived raw dB from the
existing 9 MC20 tiles, reapplied normalization with the channels swapped per
`resolve_frozen_v0_2_channel_binding()`, and ran the frozen checkpoint on both
versions:

| | max activation across all 9 tiles |
|---|---|
| As currently built (no swap) | 3.068 × 10⁻⁶ |
| With documented swap applied | 2.132 × 10⁻⁶ |

Both are ~5 orders of magnitude below the calibrated decision threshold
(0.806). **The channel-binding gap does not explain MC20's null detection
under either ordering** — this rules out the specific fabrication risk that
Demo A's "safe stop" narrative was secretly an artifact of a channel-mapping
bug rather than a genuine domain gap.

## Decision

1. Preprocessing compatibility for the REAL inference path is **verified
   correct** with respect to normalization statistics. Demo A's OOD/domain-gap
   conclusion stands independent of this question.
2. The channel-binding gap is real and should still be fixed in
   `scripts/build_mc20_event_gold.py` for scientific correctness — it is
   currently a silent inconsistency between documented, verified evidence and
   shipped code — but it is **not a blocker for this hardening session**,
   since it does not change any current conclusion.
3. **Not fixed in this session.** `scripts/build_mc20_event_gold.py` writes
   into `data/gold/events/mc20_v0_1/`, which this session's stop conditions
   treat as a frozen/protected asset. Rebuilding it — even to apply a verified
   fix — would change MC20 Gold's content, which is a stop condition
   ("scientific semantics would change materially," §24 of the session
   instructions). Flagged here for the Track 2 / NETRA-Gold-owning track to
   apply and re-freeze deliberately, not silently.
4. `NetraModelSpec` still has no `preprocessing_version` field, so nothing
   *mechanically* prevents a future incompatible combination from running
   silently. Recorded as a follow-on (see
   `docs/product/VARUNA_POST_INTEGRATION_RESEARCH_QUESTIONS.md`), out of scope
   for this session because adding the field without a companion migration for
   every existing `NetraModelSpec` construction site risks breaking the
   frozen-checkpoint gate under time pressure.

## Consequence

Phase 4B (real OOD signal) can proceed on the existing MC20 tiles without
first resolving the channel-binding question — the preprocessing path feeding
it is verified, and the outstanding channel-binding defect is orthogonal to
whether an OOD score built from Gold-v0.2-val activations is trustworthy.
