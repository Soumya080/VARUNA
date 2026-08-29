# CHHAYA Architecture Decision

**Status:** Proposed — not yet ratified. No model is implemented or trained
against this decision until an operator/science-lead explicitly accepts one
option below.

## Context

Prior audits described this as a two-way choice: "xView3 SAR vessel
detector" (per project documentation) vs. "AIS trajectory forecasting
model" (per `packages/varuna_chhaya/model/factory.py`). Direct inspection
of the current code shows the situation is more specific than that, and the
ADR needs to be precise about what actually exists before recommending.

### What is actually in the repository today

**Three coexisting things, only one of them wired to anything:**

1. **`packages/varuna_chhaya/protocol.py` + `service.py` + `mock.py`** — a
   fully wired, tested (`tests/unit/test_chhaya_mock.py`) design:
   `ChhayaProvider.investigate(scene_path, ais_positions, scene_bbox,
   envelope) -> (List[DarkVesselDetection], LatentFinding)`. The mock
   implementation (`MockChhayaProvider`) computes AIS coverage over the
   scene bbox (`coverage.py::compute_ais_coverage`) and classifies the
   scene into one of `INSUFFICIENT_COVERAGE` /
   `RADAR_CONTACT_WITHOUT_AIS` / `VISIBLE_SOURCES_EXIST_BUT_WEAK`. This is
   **not xView3** — it never opens or reads `scene_path`'s SAR raster; it
   only takes it as a filename to hash into a deterministic detection ID.
   It is an **AIS-coverage-gap heuristic**, not a SAR detector.

2. **`packages/varuna_chhaya/model/factory.py::create_chhaya_model()` +
   `config.py::ChhayaModelConfig`** — a genuine PyTorch `nn.LSTM`
   (`input_dim=4, hidden_dim=128, num_layers=3, output_dim=2, seq_len=72`).
   Its `forward(x)` signature is `(batch, time, input_dim) ->
   (batch, time, output_dim)` — a sequence regressor. Given
   `output_dim=2`, this is shaped for **lon/lat trajectory prediction**,
   i.e. "given a vessel's recent AIS track, predict where it goes next."
   **Nothing calls `create_chhaya_model()`.** It is unreferenced by
   `service.py`, `mock.py`, `trainer.py`, or `inference.py`.

3. **`packages/varuna_chhaya/training/{trainer.py,evaluator.py}`** — the
   same fabrication pattern found in NETRA: `ChhayaTrainer.train()` has a
   `for epoch in range(...): pass` loop and `ChhayaEvaluator` returns
   hardcoded literals (`mean_distance_km=2.5`, `rmse_lon=0.01`,
   `rmse_lat=0.01`). These metrics are trajectory-forecast metrics
   (distance/RMSE against a predicted position), consistent with (2), not
   with (1)'s detection-confidence framing. **This training path has never
   trained anything and is not connected to (1).**

So the accurate framing is: **the integrated, tested, evidence-envelope-
aware path (1) is an AIS-coverage-gap dark-vessel heuristic. The
orphaned, untrained, disconnected path (2)+(3) is an AIS trajectory
predictor.** Neither is a literal xView3 SAR pixel-detector CNN — no such
model exists anywhere in this codebase today.

## Options

### A. AllenAI xView3 SAR vessel detector (as project documentation states)

Would replace (1)'s heuristic with a real CNN operating on the SAR raster
(VV/VH + ancillary channels), predicting per-pixel vessel presence,
length, and "is_fishing"/"is_dark" (vessel present but no matching AIS).
This is the architecture xView3's reference model and paper describe.

**Requires:**
- The xView3-SAR dataset (`data/raw/xview3/` — currently empty,
  `status: missing` in the catalog). ~900GB per the xView3 challenge specs
  (SAR scenes + labels + ancillary bathymetry/wind layers).
- A detector architecture (xView3's reference implementation is a
  multi-head CNN, not a drop-in from this repo's existing components).
- Reworking `ChhayaProvider.investigate()`'s signature — it would need to
  read `scene_path` as an actual raster, not a filename.
- A genuinely new training pipeline; nothing in `packages/varuna_chhaya/`
  today is reusable for this path except the `EvidenceEnvelope`
  integration in `service.py`.
- Comparable GPU/data investment to NETRA — this is a second full
  ML-training program, not an incremental addition.

### B. AIS trajectory forecasting (as `model/factory.py` implements)

Would connect (2)+(3) into `service.py`, replacing the coverage-gap
heuristic with an LSTM predicting where a vessel with a known recent track
is likely to be. Repositions CHHAYA from "detect dark vessels" to "forecast
vessel motion" — a materially different mission from what
`LatentFinding.RADAR_CONTACT_WITHOUT_AIS` implies today.

**Requires:**
- Real AIS data with dense enough per-vessel history to train a sequence
  model (see `docs/datasets/AIS_ACQUISITION_SPEC.md` — AIS is currently
  absent).
- Reconciling that trajectory forecasting is **already PRAVAAH's stated
  job** (`packages/varuna_pravaah` — forward drift/forecast). Two engines
  independently forecasting future position is a scope collision, not a
  complementary pair, unless CHHAYA's forecast target is specifically
  "next AIS-visible waypoint of a *known* vessel" (route continuation)
  versus PRAVAAH's "future position of an *oil slick*" (physical
  advection) — a distinction worth stating explicitly if B is chosen, so
  the two engines don't silently duplicate effort.
- Training data volume: AIS trajectory models typically need dense
  per-MMSI histories across many vessels; the acquisition spec's
  MarineCadastre recommendation would need to be scaled well past a
  30-day sample.

### C. Keep the current AIS-coverage-gap heuristic (path 1), formalize it

Accept that (1) is not xView3 and not a trajectory model — it is a
lightweight, already-integrated, already-tested "AIS silence in a
covered area is suspicious" classifier. Retire the disconnected
(2)+(3) LSTM/training code rather than build toward it, and document (1)
as CHHAYA's actual architecture.

**Requires:**
- No new data acquisition, no new training program.
- Explicit documentation update (this ADR) reconciling stated docs with
  actual code, so the discrepancy stops being an audit finding.
- A decision on `model/factory.py`, `model/config.py`,
  `training/trainer.py`, `training/evaluator.py` — either delete them (out
  of scope for this reconciliation pass; raw/derived data immutability
  doesn't apply to unused source code, but deletion needs explicit
  operator sign-off since it is not this document's call to make) or
  leave them clearly marked orphaned/not-in-use pending a real decision.
- Coverage-gap detection is fundamentally weaker evidence than either A or
  B — it flags *absence* of AIS, which conflates "vessel is deliberately
  dark" with "AIS receiver coverage gap," "vessel type doesn't carry AIS,"
  or "AIS was lost to a data quality issue" (`ais_cleaner.py`'s own gap
  classes). It should be framed as a screening signal, not standalone
  attribution evidence.

## Recommendation

**C, with a staged path to A.**

Reasoning:

1. **A (xView3) is the only option that matches "dark vessel detection"
   as the term is normally understood** — actual SAR-based vessel
   detection independent of AIS. It is also the only option consistent
   with what the project's documentation promises. But it is a second
   full ML-training program (~900GB of data, a new architecture, GPU time
   comparable to NETRA) and NETRA is already the active, resourced
   training effort. Committing to A now would either contend with NETRA
   for the same GPU/disk/attention or silently stall.

2. **B (trajectory forecasting) duplicates PRAVAAH's stated mission** and
   requires AIS data this project does not have and has not prioritized
   acquiring (the acquisition spec explicitly treats bulk AIS as optional
   for the current Arabian Sea / Bay of Bengal target domain). Building B
   now means training a second forecasting model against a mission
   PRAVAAH already owns.

3. **C costs nothing new and stops the documentation/code drift today.**
   The coverage-gap heuristic is real, tested, and already flows through
   `EvidenceEnvelope`/`derive()` correctly. It is honest about being weak
   evidence (`LatentFinding` already has three explicit states rather than
   a binary detect/no-detect), which is the right posture for something
   this simple to feed into NYAYA's Bayesian attribution rather than act
   as a standalone verdict.

**Staged path:** adopt C now. Revisit A only after (a) NETRA's baseline is
complete and validated, freeing GPU/attention budget, and (b) xView3-SAR
data acquisition is explicitly resourced as its own project phase — not
folded into a data-reconciliation pass. Until then, mark `model/factory.py`
and `training/{trainer,evaluator}.py` in their module docstrings as
**not currently in use — see this ADR** rather than silently leaving them
to be mistaken for an active training path (the same silent-drift problem
NETRA's fabricated-metrics finding illustrates).

## Non-decisions (explicitly out of scope for this ADR)

- Deleting or rewriting `model/factory.py` / `training/*.py` — flagged for
  a follow-up decision, not performed here (raw data immutability does not
  extend to unused source code, but removing code is a judgment call for
  whoever owns that decision, not implied by a reconciliation pass).
- Committing to a timeline for revisiting option A.
- Any change to `packages/varuna_pravaah` — B's overlap with PRAVAAH is
  flagged, not resolved, since PRAVAAH is out of this ADR's scope.
