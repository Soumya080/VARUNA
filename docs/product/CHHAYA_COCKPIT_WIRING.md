# CHHAYA v2 — wired into the cockpit

**Date:** 2026-09-03

Workstream B was built but isolated (zero imports from `varuna_integration`,
`varuna_domain` or `apps/`). It is now reachable from the operator cockpit
and runs against **real Sentinel-1 data**, not a fixture.

## What was wired

| Piece | File |
|---|---|
| API — tile listing + investigation | `apps/api/routers/chhaya.py` (new) |
| Router registration | `apps/api/main.py` |
| Cockpit panel | `frontend/.../components/cockpit/chhaya-panel.tsx` (new) |
| Panel placement | `frontend/.../app/page.tsx` (right-hand evidence column) |

## Data it actually reads

- **SAR:** `data/gold/events/mc20_v0_1/sar/tiles/*.npy` — 9 real
  Sentinel-1A IW GRDH tiles (512×512) from scene `mc20_2023-01-15`, each
  with a real georeferenced bbox from `tile_records.json`.
- **AIS:** `data/gold/events/mc20_v0_1/ais/event_ais_join.json` — the real
  MC20 AIS join (530 tracks, 425 spatially matched).

Nothing is synthesised. The response echoes `sar_source`, `ais_source`,
`tile_shape` and `sensor` so a reviewer can verify the inputs.

## Detector selected — and why it is not xView3

The xView3 Faster-RCNN checkpoint is **not** used. Its published weights
require a third `bathymetry` input channel (`conv1` is `Conv2d(3, 64, …)`,
confirmed by direct inspection in
`reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md`), and no bathymetry
raster exists for this event. CHHAYA therefore runs the classical
**CA-CFAR** detector (`cfar_ca_v1`), which is a real detector on real
imagery — not a stand-in for a model. Every response names
`detector_source` / `detector_mode` so CFAR output can never be mistaken
for a learned model's.

## Honest finding: this imagery cannot support vessel CFAR

Running CFAR across all 9 tiles at both 6.0σ and 4.5σ produced **zero**
candidates. Investigating why, rather than reporting an empty ocean:

```
tile r0c0 : min 0.222  max 1.000  mean 0.738  std 0.076  peak = 3.46σ
```

The tiles are **normalised and clipped to [0,1]** — NETRA oil-slick
*segmentation* preprocessing. That compression destroys the amplitude
dynamic range CFAR needs: the brightest pixel sits ~3.5σ above the mean, so
no threshold at or above 4σ can physically fire, and dropping below ~3.5σ
would return speckle rather than vessels.

The endpoint now detects this and returns a `suitability` block, and the
cockpit renders a warning panel:

> **Imagery unsuitable for vessel CFAR** — This tile is normalised/clipped
> to [0,1] (NETRA oil-slick segmentation preprocessing). Its brightest pixel
> is only 3.5 sigma above the mean, below the 6.0 sigma CFAR threshold, so
> vessel detection cannot fire on this product. A `NO_SUPPORTED_VESSEL`
> outcome here means *"this imagery cannot support vessel detection"*, NOT
> *"no vessels are present"*. Raw (uncalibrated or sigma0) GRD amplitude is
> required.

This distinction matters: without it, the product would silently report an
empty ocean on evidence that cannot answer the question.

## What a reviewer sees in the cockpit

Right-hand evidence column → **CHHAYA — Vessel intelligence (real
Sentinel-1)**: tile selector (9 real tiles), *Investigate tile* button,
outcome badge, detector id/mode, tile shape, sensor, AIS positions in tile,
candidate count, the outcome reason, the suitability warning, and an
explicit note that scores are **relative plausibility, not calibrated
probabilities**.

## Remaining gaps

1. **No vessel detections are demonstrable on this dataset** until raw
   (uncalibrated or sigma0) GRD amplitude tiles are produced. The pipeline
   is wired and correct; the input product is the blocker.
2. **xView3 remains unusable** without a bathymetry raster for the event.
3. **AIS positions per tile currently resolve to 0** — the MC20 join file
   carries summary counts and a footprint, not per-position payloads under
   a `tracks[].points[]` key. `classify_outcome()` correctly treats that as
   insufficient AIS coverage rather than as dark-vessel evidence.
4. CHHAYA is exposed as its own investigation surface; it is **not yet a
   stage inside `GoldenCaseWorkflow`**, because the replay fixtures carry no
   SAR raster to run it on.
