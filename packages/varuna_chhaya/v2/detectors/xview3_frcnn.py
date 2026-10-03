"""xView3 pretrained Faster R-CNN (multihead) vessel detector — NOT_CONFIGURED.

This module intentionally does NOT run inference. It exists to record, in
executable and testable form, exactly what was investigated in Phase 1 of the
CHHAYA v2 benchmark and exactly why it is not wired into the live pipeline —
see `reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md` for the full writeup.

WHAT WAS VERIFIED (2026-09-02, this session):
  - Candidate: AI2/Skylight's xView3-challenge submission
    (github.com/allenai/sar_vessel_detect for weights + license;
    github.com/DIUx-xView/xView3_fourth_place for the matching, complete
    source under `src/xview3/models/frcnn_multihead.py`).
  - Weights downloaded and inspected directly: `model.pth`, 220,622,737 bytes,
    sha256 9ced010739c61f3a64c632dd2889fc11fbb0ed68e589185f23c89b8b5ab8cb70.
    Not committed to this repository (weights do not belong in git; refetch
    from the URL above if this detector is ever completed).
  - Architecture CONFIRMED by exact state_dict key/shape match against
    `xview3.models.frcnn_multihead.FasterRCNNMultihead`: a torchvision
    `FasterRCNN` (ResNet50+FPN backbone, standard torchvision module naming,
    4 classes) for box proposals, PLUS a second bare ResNet50 backbone feeding
    a small conv head (`pred_layer` -> `pred_length`/`pred_confidence`/
    `pred_fishing`/`pred_vessel`) for per-detection attribute prediction.
    License: Apache-2.0.
  - BLOCKING finding: the model's own training config
    (`data/configs/final.txt`, `initial.txt`, `xval1b...txt` — all three
    checked, all agree) specifies `Channels = vh,vv,bathymetry` — i.e. the
    3rd of 3 input channels (`conv1` is a `Conv2d(3, 64, ...)`, confirmed from
    the checkpoint) is a per-scene bathymetry raster
    (`xview3/infer/inference.py`: `'bathymetry': 'bathymetry.tif'`, "We always
    load bathymetry so we can eliminate detections on land."), shipped
    alongside VH/VV in the xView3 dataset's own per-scene folders.

WHY THIS IS NOT_CONFIGURED, NOT A BUG TO FIX QUIETLY:
  VARUNA does not currently ingest per-scene bathymetry rasters anywhere in
  its data pipeline (checked: no bathymetry adapter under
  `data/raw/`/`packages/varuna_data_eng/varuna_source_adapters/`). Feeding
  this model zeros, a duplicate VH channel, or any other stand-in for the
  missing 3rd channel would silently change its trained behavior in an
  unverifiable way and produce detections that could not be honestly
  described as "the xView3 pretrained model's output." Per this task's own
  non-goals ("do not fabricate detection scores"), the correct action is to
  report this candidate unavailable, not to approximate it.

  A secondary, softer finding: even the confirmed-correct 3-channel path
  relies on `ImageMean=0.5,0.5,0.5` / `ImageStd=0.1,0.1,0.1` and default
  (unconfigured) RPN anchor sizes recovered from the one training config
  variant checked — plausible, but not independently validated against the
  original team's held-out metrics anywhere in this pass, since the ~1.4
  gigapixel xView3 validation imagery was not fetched (well outside this
  task's compute/time budget). Even with bathymetry available, this detector
  should be benchmarked against ground truth before being trusted, not
  wired in on architecture-match confidence alone.

TO COMPLETE THIS INTEGRATION LATER (tracked, not automatic):
  1. Add a bathymetry ingestion adapter (GEBCO or equivalent), co-registered
     per scene — this is a live-data acquisition task, not a CHHAYA task.
  2. Re-download the weights from the URL above, verify the sha256 given here.
  3. Reconstruct `FasterRCNNMultihead` (torchvision `FasterRCNN` + the small
     attribute head) exactly per `frcnn_multihead.py`, load this state_dict.
  4. Validate against a real held-out scene with known vessels before
     enabling `is_available() -> True`.
"""
from __future__ import annotations

import numpy as np

from varuna_chhaya.v2.detectors.protocol import (
    RawDetection,
    VesselDetector,
    VesselDetectorUnavailable,
)

XVIEW3_WEIGHTS_URL = (
    "https://ai2-prior-sarfish.s3.us-west-2.amazonaws.com/public/"
    "sarfish-models/xview3-nov20-combo8/model.pth"
)
XVIEW3_WEIGHTS_SHA256 = "9ced010739c61f3a64c632dd2889fc11fbb0ed68e589185f23c89b8b5ab8cb70"
XVIEW3_WEIGHTS_SIZE_BYTES = 220_622_737
XVIEW3_REQUIRED_CHANNELS = ("vh", "vv", "bathymetry")


class XView3FasterRCNNMultihead(VesselDetector):
    detector_id = "xview3_frcnn_multihead"
    detector_mode = "pretrained_neural"

    def __init__(self, bathymetry_provider=None):
        # `bathymetry_provider`: a callable (scene_id) -> np.ndarray, or None.
        # Accepted as a constructor argument so a future session can wire one
        # in without changing this class's public shape — but VARUNA has no
        # real implementation of one today, so the default is honestly None.
        self._bathymetry_provider = bathymetry_provider

    def is_available(self) -> bool:
        # Available only if a real bathymetry source has been wired in AND
        # (not attempted here) the reconstructed architecture has been
        # validated. Today: always False, for the documented reason above.
        return self._bathymetry_provider is not None

    def get_model_version(self) -> str:
        return f"{self.detector_id}@{XVIEW3_WEIGHTS_SHA256[:12]} (NOT_CONFIGURED)"

    def detect(self, vh: np.ndarray, vv: np.ndarray | None = None) -> list[RawDetection]:
        if not self.is_available():
            raise VesselDetectorUnavailable(
                "xview3_frcnn_multihead requires a 3rd input channel "
                "(bathymetry) that VARUNA does not currently ingest. See "
                "reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md and this "
                "module's docstring. Refusing to fabricate a substitute "
                "channel rather than silently degrading detection quality."
            )
        raise NotImplementedError("bathymetry_provider path is not implemented in this pass")
