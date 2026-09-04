"""VARUNA GRID v2 - CHHAYA (Dark Vessel Investigation)

Three generations share this package name — see
docs/product/HONESTY_LEDGER.md #15/#33 and Phase 5C of
scalable-coalescing-hammock.md for the full picture:

  - CHHAYA-H (`hypothesis_engine.py`) — REAL, live. Per-CASE source
    hypotheses feeding `OperatorCase.intelligence.hypotheses`. A declared-
    prior Bayesian engine, not a trained model — see that module's own
    docstring.
  - CHHAYA-V (`v2/` subpackage) — REAL, live. Per-TILE vessel evidence over
    real Sentinel-1 SAR, served via `/v1/chhaya/*`. CA-CFAR classical
    detector; xView3 investigated and correctly reported NOT_AVAILABLE
    (`v2/detectors/xview3_frcnn.py` — missing bathymetry input channel).
  - `inference.py` / `model/` / `training/` / `dataset/` (this module and
    its siblings below) — **NOT_IMPLEMENTED**. An LSTM trajectory
    predictor scaffold. `ChhayaInferenceService.forecast()` returns a
    hardcoded literal (`forecast_id="forecast_1"`, `trajectory_path=
    "mock_path"`), not a computation — admitted in its own inline comment.
    Not on any served API path; nothing in `apps/api` imports it. Kept for
    its test coverage and as a real (if unimplemented) roadmap item, not
    wired into anything a judge or operator can reach.

CHHAYA-H and CHHAYA-V answer different questions ("what kind of source?"
then "which vessel?") and are deliberately not merged — see Phase 5C.
"""
from varuna_chhaya.protocol import ChhayaProvider
from varuna_chhaya.service import ChhayaService
