# NETRA v0.3 Acquisition Decision — ESSD/PANGAEA Source (Updated)

**Decision: ESSD_GRD_USEFUL_BUT_SECOND_SOURCE_REQUIRED**

Supersedes the earlier `ACQUISITION_BLOCKED` determination now that CDSE
credentials are available. All 25 selected scenes were downloaded,
checksum-verified, and independently analyzed.

## What changed the picture

Real ERA5 join (not proxy, not inferred): **21 of 25 scenes (84%) sit in
the low-wind regime (<5 m/s)**, split 12 oil / 9 negative-lookalike. This
is the first source in this whole investigation that supplies *both*
verified low-wind timestamps *and* real oil-positive labels — Zenodo
Part III had neither (no timestamps at all); MC20 has the regime but no
labels to train against (it's evaluation-only by design).

Real calibrated dB stats: VV brighter than VH in 25/25 scenes (physical
sanity, no exceptions), and all 25 scenes' aggregate brightness falls
inside NETRA-GOLD-v0.2's existing train-clip range — confirming the gap
is specifically about *regime* coverage, not raw signal-level coverage.

## Why not "sufficient alone" (A)

Real diversity limits, stated plainly: single region (Eastern
Mediterranean), single year (2019), 21 usable scenes. A first controlled
experiment can be built on this alone, but broader geographic/seasonal
generalization would still be thin from this source by itself.

## Why not "mainly evaluation" (C)

It independently supplies 15 real oil-positive scenes with real
low-wind timestamps — a genuine training-signal source, not just a
lookalike/evaluation set.

## Concrete blocker before Gold-v0.3 construction

PANGAEA's object/patch bounding boxes are in 640×640 packaged-patch
pixel space, not yet re-projected into each raw scene's own line/pixel
grid (via `geolocationGridPoint`s, same mechanism as MC20's tile
geolocation). This is a scoped, doable task — named explicitly here so
it isn't mistaken for "need more data."

## Recommendation

Proceed with (a) the geolocation re-projection step, and in parallel
decide whether a second, geographically distinct low-wind source is
worth acquiring before or alongside the first Gold-v0.3 build — not
launched automatically; needs explicit authorization, consistent with
every prior gate in this investigation.
