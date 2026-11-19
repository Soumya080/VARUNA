# MC20 Real E2E Backend Integration (Track 4)

Wires the existing producers into one live case pipeline and exposes the result
through the OperatorCase v1 read projection.

**Status: integration complete and REAL, but NOT `REAL_E2E_READY`.**

Every seam connects, the frozen NETRA checkpoint is wired and verified, and
forcing and AIS are both genuinely REAL — the first run with no simulated
component anywhere. `REAL_E2E_READY` is still withheld for one reason: a real
MC20 case has **not** traversed the complete chain. The model returns no
detection on this scene, so Phi, attribution, validity, forecast, tasking and
mission never run. The plumbing is proven; a complete real case is not.

The null detection must **not** be read as "no oil at MC20" — see
[The MC20 null result](#the-mc20-null-result).

---

## Execution graph

```
data/gold/events/mc20_v0_1
        |
        +-- forcing/era5_cube.json ---> CubeBackedWindField ----+
        +-- forcing/cmems_cube.json --> CubeBackedCurrentField -+--> PRATIVARTAN
        |                                                       |      |
        +-- sar/tiles/*.npy --> NETRA boundary --> SlickDetection      v
        |                                                    |      PhiField
        +-- ais/event_ais_join.json --> EventAISAdapter       |         |
                    |                       |                |         |
                    v                       v                |         v
            data/bronze/ais/...    FetchResult -> REAL -------+---> NYAYA
                                            |                          |
                                     VesselTrack[]                     v
                                                             AttributionResultV2
                                                                       |
                                                                       v
                                                               ValidityGate
                                                                 /        \
                                                     PRAVAAH <--+          +--> ABHIYAN
                                                        |                         |
                                                 ForwardForecast            AssetTasking[]
                                                                                  |
                                                                                  v
                                                                            Mission FSM
                                                                                  |
                                                                                  v
                                                                              Alerts
                                                                                  |
                                                                                  v
                                                                        OperatorCase v1
```

## Producer / consumer map

| Stage | Producer (owns the computation) | Input | Output contract | Boundary added by Track 4 |
|---|---|---|---|---|
| `forcing` | `CubeBacked{Wind,Current}Field` + `forcing_readers` | `era5_cube.json`, `cmems_cube.json` | `EventForcing` | `varuna_integration.forcing` |
| `netra_detection` | `NetraProvider` impl | `sar/tiles/*.npy` | `list[SlickDetection]` | `varuna_integration.netra_boundary` |
| `ais_ingest` | `EventAISAdapter` -> `fetch_with_mode()` | `event_ais_join.json` + bronze tracks | `list[VesselTrack]` | `varuna_integration.ais_source` |
| `phi_reconstruction` | `run_backward_ensemble` + `build_phi_field` | detection + forcing | `PhiField` | orchestration only |
| `attribution` | `NyayaService.attribute()` | `PhiField` + tracks | `AttributionResultV2` | orchestration only |
| `validity` | `ValidityService.evaluate()` | phi + attribution | `ValidityGateResult` | orchestration only |
| `forecast` | `CubeBackedPravaahProvider` | detection + current field | `ForwardForecast` | orchestration only |
| `decision` | `AbhiyanService.plan_mission()` | gate + phi search box | `list[AssetTasking]` | orchestration only |
| `mission` | `MissionService.create_mission()` | taskings | `list[MissionRecord]` | orchestration only |
| `alerts` | `AlertService.route_and_send()` | gate state | `list[DeliveryResult]` | orchestration only |
| `operator-view` | `build_operator_case()` | `Case.metadata` | `OperatorCase` | `varuna_integration.case_bridge` |

No scientific value is computed in `varuna_integration`. Confidence, posteriors,
Φ, vessel ranking, forecast trajectories and gate decisions are all produced by
the owning subsystem and passed through unmodified.

## Failure semantics

`StageStatus` (did it run) is kept strictly separate from `EvidenceMode` (how
real is the result).

| Condition | Stage status | Reason code |
|---|---|---|
| No frozen checkpoint, simulation not requested | `NOT_YET_PRODUCED` | `CHECKPOINT_NOT_FROZEN` |
| Checkpoint hash ≠ freeze record | `NOT_YET_PRODUCED` | `CHECKPOINT_HASH_MISMATCH` |
| Model ran, nothing above threshold | `NOT_YET_PRODUCED` | `NO_SLICK_DETECTED` (a valid outcome) |
| Inference raised on every tile | `BLOCKED` | `NETRA_INFERENCE_FAILED` |
| Cube missing / unreadable | `BLOCKED` | `{ERA5,CMEMS}_CUBE_MISSING` / `_INVALID` |
| Insufficient time series, partial coverage | `BLOCKED` | `{ERA5,CMEMS}_FIELD_UNUSABLE` |
| ERA5 and CMEMS windows disjoint | `BLOCKED` | `FORCING_WINDOWS_DISJOINT` |
| AIS source unreachable | `BLOCKED` | `AIS_UNAVAILABLE` |
| No track with the requested join status | `NOT_YET_PRODUCED` | `NO_TRACKS_WITH_STATUS_*` |
| No AIS for attribution | `BLOCKED` | `AIS_UNAVAILABLE_FOR_ATTRIBUTION` |
| Gate denies operational action | `PRODUCED` | gate's own `blocking_reasons` |
| Gate restricted → no tasking | `NOT_YET_PRODUCED` | `NO_TASKING` |
| No tasking → no mission | `NOT_YET_PRODUCED` | `NO_TASKING_TO_PROPOSE` |
| SCIENTIFIC run, too few obs points for requested particles | `BLOCKED` | `PARTICLE_COUNT_UNDER_RESOLVED` |
| Any upstream stage blocked | `BLOCKED` | `UPSTREAM_<STAGE>_UNAVAILABLE` |

Two deliberate distinctions:

* **A restrictive gate is `PRODUCED`, not `BLOCKED`.** The gate ran and answered.
  Collapsing "the gate said no" into "the gate crashed" would make the two
  indistinguishable and would tempt someone to "fix" the former.
* **`NO_SLICK_DETECTED` is not a failure.** A model that finds no oil has done
  its job.

### Particle loss is reported, not just its symptom

The phi detail block carries `particles_seeded`, `particles_lost` and
`particle_loss_fraction` alongside `convergence_flag`. Loss above 20% degrades
the field (see `PhiDiagnostics`), so reporting the degraded flag without the
count would show the symptom and hide the cause.

The dominant cause on a coastal event is the **CMEMS land mask**. Track 2
measured the real MC20 grids directly: CMEMS current is 26.4% NaN (MC20 sits
near the Louisiana coast), ERA5 wind is 0% NaN. A backward-advected particle
that enters a masked cell goes NaN and never returns, so loss grows with
backward duration.

Particle loss on MC20 is **not** a stable property of the event. It is a sharp
function of the observation time, because the loss mechanism is advection into
the mask and the current field is time-varying. Measured here at a fixed seed,
fixed 24h duration and 500 particles x 4 members:

| obs_time (Φ hours) | UTC | particle loss |
|---|---|---|
| -26001 | 2023-01-13 17:00 | 0.1% |
| -25989 | 2023-01-14 05:00 | 35.6% |
| -25971 | 2023-01-14 23:00 | 67.9% |
| -25953 | 2023-01-15 17:00 | 0.1% |
| -25921 | 2023-01-17 01:00 | 0.0% |

A single loss figure is therefore not characteristic of MC20; it is
characteristic of a time. The true acquisition (2023-01-15, `-25968.0`) sits
near the peak and loses **70.2%**.

### Particle loss also depends on seed cloud width — and that is a caveat on the gate

Two independent MC20 measurements at the same true acquisition time
(`-25968.0`), same 24h duration, same real CMEMS field, disagreed: 42.7%
(Track 2) against 70.2% (this pipeline). Ensemble size was ruled out
explicitly. The difference is the **width of the seed point cloud**, and
replicating Track 2's geometry here reproduces their figure to within the RNG
draw (42.4% vs 42.7%).

Sweeping cloud width at fixed time, duration and seed:

| seed σ (lat) | ≈ km | particle loss |
|---|---|---|
| 0.005° | 0.6 | 74.6% |
| 0.0167° | 1.8 | 66.1% |
| 0.030° | 3.3 | 54.8% |
| 0.050° | 5.5 | 48.8% |
| 0.096° | 10.6 | 46.0% |
| 0.150° | 16.6 | 47.0% |
| 0.250° | 27.6 | 45.5% |

Monotonic decay to a ~45–46% asymptote. The mechanism: a tight cloud advects
coherently as one packet, so if that packet's trajectory intersects the land
mask, nearly all of it is lost. A wide cloud samples many trajectories, only a
fraction of which intersect the mask, so loss converges on the *fraction of
origin-space that is land-blocked*.

**The consequence is that `particles_lost` conflates two different things:** the
physical land-blocked fraction (~45%, the asymptote, a real property of a
coastal event) and an artefact of how tightly the seed cloud happened to be
drawn (up to ~75% for a near-point seed). Since the Validity Gate reads
particle loss as a quality criterion, a `DEGRADED` verdict driven by
`particle_loss` is partly reporting seed geometry rather than data quality.
Neither measurement above was wrong; they were measuring different
configurations.

Report the curve, not a point value — for observation time and for seed width
alike.

### A clamped observation time selects a different physical answer

This was found the hard way. `SimulatedSlickProvider` defaults its
`observation_time` to `datetime.now()`, so a placeholder detection was dated
2026 against a 2023 forcing window. `clamp_time()` duly moved it onto the
window edge and set `was_clamped=True` — exactly as designed — and the run
reported a clean **0%** particle loss.

That zero was an artifact. The clamp had moved the observation ~47h away from
the real acquisition, out of the high-loss regime entirely. Nothing was
mislabelled and no value was fabricated: the flag was set and recorded. But a
boolean cannot distinguish a one-hour nudge onto the grid from a multi-year
relocation, and the magnitude is what decides whether the answer is still about
the event.

Two changes follow:

1. The detail block records `obs_time_clamp_delta_hours` alongside the boolean.
2. A `SCIENTIFIC` run whose clamp exceeds `MAX_SCIENTIFIC_CLAMP_HOURS` (2.0h,
   sized to the ~1h forcing resolution) returns `BLOCKED` /
   `OBS_TIME_OUTSIDE_FORCING_WINDOW` rather than advecting at a time that
   answers a different question.

Simulated placeholders must be dated to the event's real acquisition time. The
bounded test fixtures now do this, and with it they reproduce the 70.2% loss
rather than the artefactual zero.

### Requested scale is not achieved scale

`run_backward_ensemble()` subsamples with `min(config.n_particles, n_obs)` and
does so silently, so a requested particle count is only realised if at least
that many observation points exist. This bit two call sites independently
(Track 4's sampler and Track 2's first sensitivity pass), both at 12 points
against a requested 500 — it is a structural trap, not a slip.

Three things follow, and all three are load-bearing:

1. `_slick_points_from_detection()` takes `n` keyword-only with **no default**.
   The default was the bug; a caller must state the count it wants.
2. The phi detail block reports **`n_particles_advected` and
   `n_particles_requested` as a pair**, never a single `n_particles`. This
   mirrors the existing `n_ensemble_completed` / `n_ensemble_requested`
   convention — the ensemble dimension already refused to echo the request, and
   the particle dimension now does too.
3. A run classed `SCIENTIFIC` whose points cannot fill the requested count
   returns `BLOCKED` / `PARTICLE_COUNT_UNDER_RESOLVED` rather than advecting
   fewer and reporting the request. Reporting a particle count that was not
   achieved is a fabricated scientific parameter.

Note what a larger particle count does and does not buy: the points are
Monte-Carlo samples drawn inside one real detected bbox, so more of them refine
the sampling of that footprint — they are **not** additional independent
observations.

The same defect existed one layer down and has since been fixed by Track 2:
`PhiField.n_particles` was set from `config.n_particles`, making it a config
echo rather than a measurement, and it reached the API unmodified via
`apps/api/routers/cases.py:109`. `phi_builder.py` now measures the real
per-member count from `ensemble_results` and raises if members disagree rather
than picking one.

The two checks are complementary, not redundant: this pipeline's guard refuses
an under-resolved `SCIENTIFIC` run *before* advection, so no compute is spent
producing a number that would have to be caveated; `phi_builder`'s measurement
reports the truth *after*, for every caller including those that never go
through this pipeline.

Still open, deliberately not implemented: `PhiField` carries a single
`n_particles` field, so the advected/requested *pairing* used in this
pipeline's detail block has no equivalent on the contract object. Adding a
companion field is a schema change to a locked contract package and belongs in
an ADR, not in an integration branch.

## Provenance

`EvidenceMode` combines by monotonic worsening only
(`varuna_integration.stage.worst_mode`):

```
REAL + REAL       -> REAL
REAL + SIMULATED  -> SIMULATED
any + UNAVAILABLE -> UNAVAILABLE
```

There is no parameter, config key or environment variable that raises a mode.
Two enforcement points:

1. `NetraDetectionBoundary.__init__` raises if a `SimulatedSlickProvider` is
   labelled `REAL`.
2. `resolve_netra_boundary(allow_simulated=...)` must be passed explicitly in
   code — it cannot be set from configuration, so a demo cannot silently become
   a real run.

The checkpoint freeze gate is the third: real inference requires a
`<checkpoint>.frozen.json` sidecar whose recorded sha256 matches the file's
actual hash. This prevents inference against a `_last.pt` that a training
process is still rewriting.

## Recorded runs

Two runs are recorded: the real one, and the simulated-placeholder one that
exercises the stages the real run cannot reach.

### A. Real run — `RUN-20260830T015701Z-56b68c`

Frozen checkpoint `netra-v0.2-baseline` (sha256 `9f38c690d0ef1629...`,
threshold `0.806` read from the sidecar), `EXPERIMENTAL / UNVALIDATED`.

| Stage | Status | Mode | Time |
|---|---|---|---|
| forcing | produced | **real** | 3.82 s |
| netra_detection | not_yet_produced | — | 38.36 s |
| ais_ingest | produced | **real** | 15.89 s |
| phi_reconstruction | not_yet_produced | — | — |
| attribution | not_yet_produced | — | — |
| validity | not_yet_produced | — | — |
| forecast | not_yet_produced | — | — |
| decision | not_yet_produced | — | — |
| mission | not_yet_produced | — | — |
| alerts | not_yet_produced | — | — |
| **run** | **complete, `blocked_at: None`** | **real** | **26.49 s** |

No stage is BLOCKED — nothing broke. Every stage after detection reports
NOT_YET_PRODUCED naming the specific upstream reason. See
[The MC20 null result](#the-mc20-null-result) for why detection produced
nothing and what that does and does not mean.

### B. Simulated-placeholder run — `RUN-20260829T214346Z-2b315f`

`--allow-simulated`, class `INTEGRATION_SMOKE`. Exercises PRATIVARTAN, NYAYA,
the validity gate, PRAVAAH, ABHIYAN, Mission and Alerts, which run A cannot
reach.

| Stage | Status | Mode | Time |
|---|---|---|---|
| forcing | produced | **real** | 0.03 s |
| netra_detection | produced | simulated | 0.00 s |
| ais_ingest | produced | **real** | 17.68 s |
| phi_reconstruction | produced | simulated | 0.21 s |
| attribution | produced | simulated | 0.05 s |
| validity | produced | simulated | 0.00 s |
| forecast | produced | simulated | 0.00 s |
| decision | not_yet_produced | simulated | 0.00 s |
| mission | not_yet_produced | — | — |
| alerts | produced | simulated | 0.00 s |
| **run** | **complete** | **simulated** | **20.93 s** |

REAL forcing + REAL AIS + SIMULATED detection correctly yields a SIMULATED run:
provenance worsens monotonically and is never promoted back.

### Case-level lineage rollup

`OperatorCase.provenance` (`ProvenanceView`) is built by the API projection
from the PRAMAN artifact registry. This pipeline registers no PRAMAN artifacts,
so a case produced here originally shipped an **empty** lineage block —
`artifact_ids: []`, `source_ids: []`, `model_versions: {}` — even though every
stage knew its own version and source. On an operator-facing case that is a
defect, not a cosmetic gap: lineage is how an officer traces what produced a
decision.

`case_bridge.apply_run_to_case()` now collects `model_versions` and
`source_ids` from what the stages actually reported into
`case.metadata["pipeline_provenance"]`, and `_provenance()` **merges** that with
the registry rather than replacing it, so a CaseWorkflow-produced case is
unaffected. Absent that key the block stays empty rather than inventing a
version. A stage that produced nothing contributes nothing.

The real MC20 case now carries `model_versions: {netra_detection:
netra-v0.2-baseline}` and `source_ids: [ais.marinecadastre.event_gold]`. On the
simulated path the same field honestly reads `SIMULATED-no-model`.

`processing_versions` remains `{}` **deliberately**. It should record how the
inputs were prepared — the Gold v0.2 normalization contract — and nothing
versions that today. The detector boundary has no `preprocessing_version`
either. That is the field which would have made the MC20 domain gap visible
earlier, so it is left empty and named rather than filled with something
plausible.

Real values observed across both runs:

* ERA5 `(168, 17, 17)` and CMEMS `(133, 49, 49)`, both `time_series_status=sufficient`, 132 h overlap.
* 530 real AIS tracks: 425 spatially matched, 320 temporally matched, 210 temporally unavailable.
* Closest temporally-matched vessel MMSI `368181750` at **3.2554 km**, Δt +16 m 57 s — independently reproducing the dataset track's figure.
* Run B gate `RESTRICTED`, failing checks `phi_convergence`, `phi_diagnostics_availability`, `distinguishability`.
* Officer caveat: *"Evidence is SIMULATED — not a real-world observation."*

`ais_ingest` dominates the runtime: it streams the 276 MB bronze tracks file
with a bracket-depth scanner rather than loading it, on a spinning disk that was
concurrently serving NETRA training.

### Wind context (look-alike diagnostic)

`NetraService.detect_slicks()` raises an `AnomalyFlag.PHYSICALLY_IMPLAUSIBLE`
low-wind flag, but only from a wind `.npz` path nothing in this pipeline
produces — so that flag has never fired on a real case. Low wind (<3 m/s) is the
classic oil look-alike condition, so having no wind context at all was a real
hole.

`_annotate_wind_context()` samples the **real ERA5 field the case already
loaded** at each detection centroid and records the measured 10 m wind speed,
reusing NETRA's own 3.0 m/s threshold rather than introducing a second one. For
the recorded run: 9 detections sampled, **6.26 m/s**, 0 below threshold — this
scene is not a low-wind false-positive candidate.

It is a **diagnostic, not a classification**. It does not downgrade, reclassify
or suppress any detection; look-alike discrimination belongs to NETRA, which
still does not receive a wind input. Two tests pin that
(`test_real_wind_speed_is_recorded_at_each_detection`,
`test_wind_context_does_not_reclassify_any_detection`).

### OperatorCase v1 projection

What `GET /v1/cases/{case_id}/operator-view` returns for that run:

| Section | Status | Mode |
|---|---|---|
| observation | produced | — (ingest carries no envelope) |
| detection | produced | **simulated** |
| origin | produced | simulated |
| ais | produced | **real** |
| attribution | produced | simulated |
| validity | blocked¹ | simulated |
| forecast | produced | simulated |
| decision | not_yet_produced | — |
| mission | not_yet_produced | — |
| alerts | produced | simulated |

¹ `ProducerStatus.BLOCKED` here means the gate ran and a precondition stopped
the case — which is what that status is defined to mean ("stage ran but a
gate/precondition stopped it"). It is pinned by
`tests/contract/test_operator_case.py:150` and confirmed intentional by the
contract owner. The pipeline's own `validity` stage separately reports
`StageStatus.PRODUCED` for the same event, so at the orchestration layer "the
gate said no" stays distinguishable from "the gate crashed".

Evidence health carries no invented scores:

| Component | Status | Score |
|---|---|---|
| sar | produced | `0.0` — the placeholder's real (zero) confidence |
| ais | produced | `None` — no AIS completeness metric exists |
| model_consistency | not_yet_produced | `None` |
| forcing | produced | `1.0` — Φ's real `ensemble_completeness` |

AIS candidates surfaced are real vessels from the MarineCadastre extraction:
`MASON G` (630 pts), `HELEN` (165), `BRIANA MARIE` (1188), `ODYSSEA TITAN`
(1043), `PACIFIC DAWN` (645). Names are shown as AIS *observations*; NYAYA's
`latent_source` outcome names no responsible vessel, and none may be named
without human sign-off.

## The MC20 null result

The frozen checkpoint, run on all 9 real MC20 tiles at its own calibrated
threshold, returned **no detection**. The honest description of that outcome is
**detection unavailable — input outside the training distribution**, not a
negative detection.

Diagnostic evidence:

| Observation | Value |
|---|---|
| Max oil probability, 9 tiles / 2.36M px | `3.07e-06` |
| Max oil probability on random noise | `6.3e-02` |
| Oil logit across MC20 | near-uniform `-9.6` |
| Checkpoint load | 0 missing / 0 unexpected keys |

The model responds *more strongly to random noise than to real MC20 SAR*, and
its logit is nearly input-independent — the signature of saturation on
out-of-distribution input, not of a confident negative.

The distribution gap is measurable:

| | Gold v0.2 train | MC20 tiles | ratio |
|---|---|---|---|
| VV normalized std | 0.214 | 0.0755 | 0.35x |
| VH normalized std | 0.212 | 0.0780 | 0.37x |
| VV normalized mean | 0.362 (-32.1 dB) | 0.717 (-21.9 dB) | +1.66 sigma |
| VH normalized mean | 0.506 (-20.3 dB) | 0.157 (-29.3 dB) | -1.64 sigma |

MC20 tiles carry roughly **one third the contrast** of the training
distribution. A flat, low-variance scene reads as background everywhere.

### A hypothesis that was tested and rejected

The opposite-direction VV/VH shift suggested a channel transposition, since over
water co-pol is normally the brighter channel. That was tested directly:
re-running all 9 tiles with VV/VH swapped gave max `3.03e-06` against `3.07e-06`
as-is — **a 1x difference, no effect**. The hypothesis is refuted and channel
order is not the cause.

A related documentation gap did surface and is tracked separately: the raw
Zenodo GeoTIFFs carry no band descriptions or tags at all, so the
`VV=band0, VH=band1` assignment is a convention taken from the dataset's
documentation and cannot be verified against the files. It is recorded in
`NETRA_GOLD_V0_2.md`; it is not a retraining trigger and demonstrably not the
cause of this null result.

### What this does and does not license

* It **does** show the integration is sound: a frozen checkpoint, real
  preprocessing, real georeferencing and honest downstream propagation all work.
* It **does not** support any claim about oil at MC20, in either direction.
* Whether the contrast gap reflects a generalization limit, a preprocessing
  difference between the Zenodo and MC20 paths, or genuinely quiet sea state is
  an open scientific question owned by the NETRA track. Nine tiles cannot settle
  it.

## Limitations

1. **No real NETRA detection.** Training is at epoch 34/50; no checkpoint is
   frozen. Detection is an explicitly-`SIMULATED` placeholder, so the whole
   downstream lineage is `SIMULATED`. This is the single blocker for
   `REAL_E2E_READY`.
2. **Not a scientific result.** 20 particles / 4 ensemble members. `Φ` reports
   `not_converged` — honestly. `--scientific` refuses to run below 500 particles
   / 20 members rather than mislabel a toy run.
3. **`Φ` sensitivity is `None`.** The 7× sweep (ADR-0007) was not run, so the
   gate correctly blocks on `phi_diagnostics_availability`.
4. **Observation time is clamped** into the ERA5/CMEMS overlap window; the run
   record flags `obs_time_clamped_into_forcing_window=true`.
5. **Slick points are resampled inside the detection's real bbox.** NETRA does
   not yet expose a mask-to-point-cloud extractor, so PRATIVARTAN is seeded from
   the detection's real centroid and bbox with seeded within-bbox scatter.
6. **NETRA still receives no wind input.** The wind context above is recorded
   alongside the detection, not fed into the model, so look-alike suppression is
   still not happening anywhere in the chain.
7. **ABHIYAN uses `MockAbhiyanProvider`.** No real asset-optimization provider
   exists. It is never reached at a restricted gate anyway.
8. **Alerts reach the console channel only.** Suppressed by the materiality rule
   at a restricted gate; no external provider is implemented.
9. **Search box is Φ's full support**, not a tightened credible region.
   Narrowing belongs in PRATIVARTAN, which owns the distribution.
10. **The 0.5 decision threshold is UNCALIBRATED.** Training logs metrics at a
   fixed 0.5 and no best-F1 PR sweep has been persisted, so the value has no
   validation behind it (confirmed with the training owner). No detection
   produced at this threshold may be described as calibrated. A swept threshold
   will replace it once training completes.
11. **NetCDF auto-detect is a known hazard, but the canonical readers are fine.**
    `xr.open_dataset(path)` with no explicit engine has been observed to hang
    indefinitely on the real MC20 `.nc` files by two sessions independently.
    `forcing_readers.load_era5_wind_arrays()`/`load_cmems_current_arrays()` pass
    `engine="netcdf4"` explicitly and do **not** hang — measured at 0.75 s (ERA5)
    and 0.18 s (CMEMS), so this boundary uses them unmodified. A first cold read
    can still take ~20 s on the spinning disk while it serves training; that is
    slowness, not a hang.

## Commands

```bash
# Full run with an explicitly-simulated detection placeholder
PYTHONPATH=packages .venv/Scripts/python.exe scripts/mc20_track4_e2e.py --allow-simulated

# Honest run with NO detection at all (what happens with no frozen checkpoint)
PYTHONPATH=packages .venv/Scripts/python.exe scripts/mc20_track4_e2e.py

# Once a checkpoint IS frozen, this uses it for real inference automatically
PYTHONPATH=packages .venv/Scripts/python.exe scripts/mc20_track4_e2e.py \
    --checkpoint artifacts/checkpoints/netra_v0_2/<name>.pt --scientific \
    --particles 500 --ensemble 20

# Tests (OPENBLAS/OMP pinning avoids allocation failures under concurrent GPU load)
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=packages:. \
    .venv/Scripts/python.exe -m pytest tests/unit/test_track4_boundaries.py \
    tests/integration/test_track4_mc20_e2e.py -q
```

Outputs: `reports/mc20_track4_e2e_run.json`, `reports/mc20_track4_operator_case.json`.

## Freezing a checkpoint

Real inference stays unavailable until a sidecar exists next to the checkpoint:

```json
{
  "checkpoint_sha256": "<sha256 of the .pt file>",
  "frozen_at": "2026-08-30T12:00:00+00:00",
  "model_version": "netra-v0.2-baseline",
  "metrics": {"iou_oil": 0.6149, "epoch": 32},
  "notes": "frozen after training completed; hash verified"
}
```

Write it only **after** training has stopped writing the file. The gate re-hashes
on every load, so a checkpoint edited afterwards is rejected automatically.
