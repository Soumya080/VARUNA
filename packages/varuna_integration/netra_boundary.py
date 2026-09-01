"""
Phase 2 - NETRA inference boundary (dependency-injected).

    event SAR tile  ->  preprocess  ->  FROZEN model  ->  SlickDetection

Why this lives outside `packages/varuna_netra/`
-----------------------------------------------
`NetraProvider` is an ABC, so an implementation can live anywhere. NETRA's own
package is being actively written by the training session; this boundary is
orchestration, not model code, so keeping it here means Track 4 never edits a
file a live training run depends on.

The freeze gate is the point of this module
-------------------------------------------
Real inference is permitted ONLY against a checkpoint that has been explicitly
frozen: a sidecar `<checkpoint>.frozen.json` recording the sha256 of the exact
bytes, when it was frozen, and the metrics it was frozen on. The gate then
re-hashes the file and compares.

That is deliberately strict, because the failure it prevents is the expensive
one: reading a `_last.pt` that a training process is still rewriting produces
detections that are irreproducible and silently wrong. A checkpoint mid-training
has no freeze record, so `resolve_netra_boundary()` reports NOT_YET_PRODUCED -
it does not quietly fall back to a mock and call the result a detection.

`SimulatedSlickProvider` exists for integration testing and is always stamped
`EvidenceMode.SIMULATED`. It must be requested explicitly by the caller; no
config value, env var, or fallback path can select it implicitly, and nothing
downstream can promote its output back to REAL.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.schemas import BBox, GeoPoint, SlickClass, SlickDetection
from varuna_integration.stage import StageResult, StageStatus
from varuna_netra.protocol import NetraProvider

# Approximate metres per degree of latitude; used only to convert a pixel count
# into an area figure for SlickDetection.area_km2. Longitude is scaled by
# cos(lat). This is geometry, not science, and is the same flat-earth
# approximation the tiling code already assumes at 512px scale.
_M_PER_DEG_LAT = 111_320.0


# --------------------------------- freeze gate ---------------------------------

@dataclass(frozen=True)
class FreezeRecord:
    """The sidecar that makes a checkpoint eligible for real inference."""

    checkpoint_sha256: str
    frozen_at: datetime
    model_version: str
    metrics: dict[str, Any]
    notes: str = ""
    # Top-level sidecar fields, kept first-class rather than buried in `metrics`
    # so callers cannot miss them. `scientific_status` in particular must travel
    # with every result the model produces.
    model_spec: dict[str, Any] = field(default_factory=dict)
    scientific_status: str = "UNKNOWN"
    dataset_version: str | None = None
    experiment_id: str | None = None

    @staticmethod
    def sidecar_path(checkpoint: Path) -> Path:
        return checkpoint.with_suffix(checkpoint.suffix + ".frozen.json")

    @classmethod
    def load(cls, checkpoint: Path) -> "FreezeRecord | None":
        p = cls.sidecar_path(checkpoint)
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            checkpoint_sha256=raw["checkpoint_sha256"],
            frozen_at=datetime.fromisoformat(raw["frozen_at"]),
            model_version=raw["model_version"],
            metrics=raw.get("metrics", {}),
            notes=raw.get("notes", ""),
            model_spec=raw.get("model_spec", {}) or {},
            scientific_status=raw.get("scientific_status", "UNKNOWN"),
            dataset_version=raw.get("dataset_version"),
            experiment_id=raw.get("experiment_id"),
        )


def sha256_of(path: Path, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class CheckpointFreezeStatus:
    frozen: bool
    reason: str
    record: FreezeRecord | None = None
    actual_sha256: str | None = None


def check_checkpoint_frozen(checkpoint: Path, *, verify_hash: bool = True) -> CheckpointFreezeStatus:
    """Is this checkpoint safe to run real, reproducible inference against?

    Fails closed at every step. A missing sidecar is the expected answer while
    training is still running - it is a status, not an error.
    """
    if not checkpoint.exists():
        return CheckpointFreezeStatus(False, f"CHECKPOINT_MISSING: {checkpoint}")
    record = FreezeRecord.load(checkpoint)
    if record is None:
        return CheckpointFreezeStatus(
            False,
            "CHECKPOINT_NOT_FROZEN: no freeze record at "
            f"{FreezeRecord.sidecar_path(checkpoint).name}. A checkpoint that a "
            "training run may still be rewriting must not be used for inference.",
        )
    if not verify_hash:
        return CheckpointFreezeStatus(True, "FROZEN (hash verification skipped)", record)
    actual = sha256_of(checkpoint)
    if actual != record.checkpoint_sha256:
        return CheckpointFreezeStatus(
            False,
            "CHECKPOINT_HASH_MISMATCH: freeze record says "
            f"{record.checkpoint_sha256[:16]}... but file hashes to {actual[:16]}...; "
            "the checkpoint changed after it was frozen.",
            record,
            actual,
        )
    return CheckpointFreezeStatus(True, "FROZEN", record, actual)


# ----------------------------- model specification (DI) -----------------------------

@dataclass(frozen=True)
class NetraModelSpec:
    """Everything needed to rebuild the architecture, injected by the caller.

    No checkpoint path is hardcoded anywhere in business logic - the caller
    supplies this, which is what makes the boundary testable without a GPU and
    swappable between the lab checkpoint and any future registry-served one.
    """

    checkpoint_path: Path
    architecture: str = "unet"
    encoder_name: str = "resnet34"
    in_channels: int = 2
    classes: int = 2
    oil_class_index: int = 1
    device: str = "cpu"
    model_version: str = "netra-unknown"
    # UNCALIBRATED DEFAULT, not a tuned operating point. Training logs metrics at
    # a fixed 0.5 and no best-F1 PR sweep has been persisted, so this number has
    # no validation behind it - confirmed with the training owner. Replace it
    # with a swept threshold before any detection is reported as calibrated, and
    # do not describe results produced at this value as calibrated.
    decision_threshold: float = 0.5
    # Minimum connected-mask area before a detection is emitted at all. Also
    # uncalibrated; it exists to suppress single-pixel noise, not to set a
    # detection-size policy.
    min_slick_pixels: int = 64


# --------------------------------- providers ---------------------------------

class FrozenCheckpointNetraProvider(NetraProvider):
    """Real inference against a frozen checkpoint. Constructed only via
    `resolve_netra_boundary()`, which enforces the freeze gate first."""

    def __init__(self, spec: NetraModelSpec, freeze: CheckpointFreezeStatus):
        if not freeze.frozen:
            raise ValueError(
                "refusing to build a real NETRA provider on an unfrozen "
                f"checkpoint: {freeze.reason}"
            )
        self.spec = spec
        self.freeze = freeze
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        import segmentation_models_pytorch as smp
        import torch

        if self.spec.architecture.lower() != "unet":
            raise NotImplementedError(
                f"architecture {self.spec.architecture!r} is not built by this "
                "boundary; extend NetraModelSpec rather than guessing one."
            )
        model = smp.Unet(
            encoder_name=self.spec.encoder_name,
            encoder_weights=None,   # weights come from the checkpoint, never a download
            in_channels=self.spec.in_channels,
            classes=self.spec.classes,
        )
        blob = torch.load(self.spec.checkpoint_path, map_location=self.spec.device,
                          weights_only=False)
        state = blob.get("model_state_dict", blob) if isinstance(blob, dict) else blob
        model.load_state_dict(state)
        model.eval()
        model.to(self.spec.device)
        self._model = model
        return model

    def detect(self, scene_path: str, wind_path: Optional[str],
               envelope: EvidenceEnvelope) -> List[SlickDetection]:
        """`scene_path` is a Gold `.npy` tile of shape (2, H, W), already
        normalized by the frozen Gold v0.2 statistics - the same tensor the
        training dataset yields. No per-tile renormalization happens here."""
        import torch

        tile = np.load(scene_path)
        if tile.ndim != 3 or tile.shape[0] != self.spec.in_channels:
            raise ValueError(
                f"{scene_path}: expected ({self.spec.in_channels}, H, W), got {tile.shape}"
            )
        model = self._load()
        with torch.no_grad():
            x = torch.from_numpy(tile.astype(np.float32)).unsqueeze(0).to(self.spec.device)
            logits = model(x)
            probs = torch.softmax(logits, dim=1)[0, self.spec.oil_class_index].cpu().numpy()
        # Record the peak activation even when nothing is detected. Without
        # this the "no detection" outcome is indistinguishable from an
        # out-of-domain one: a model that ALMOST fired and a model whose
        # activations are five orders of magnitude flat both return []. The
        # OOD assessor (varuna_integration.intelligence) needs the number to
        # tell those apart, and this is the only place it exists.
        tile_max = float(probs.max()) if probs.size else 0.0
        self.last_max_probability = (tile_max if self.last_max_probability is None
                                     else max(self.last_max_probability, tile_max))
        mask = probs >= self.spec.decision_threshold
        if int(mask.sum()) < self.spec.min_slick_pixels:
            return []
        return [_detection_from_mask(
            mask=mask, probs=probs, tile_path=Path(scene_path),
            model_version=self.spec.model_version,
        )]

    # Peak oil-class probability seen across every tile of the current
    # detect_tiles() sweep. None until at least one tile has been scored.
    last_max_probability: float | None = None

    def get_model_version(self) -> str:
        return self.spec.model_version


class SimulatedSlickProvider(NetraProvider):
    """An explicitly-labelled stand-in for a real detection.

    Every detection it emits is stamped SIMULATED by the boundary. It exists so
    the seams downstream of NETRA can be exercised while the real model trains;
    it is never selected implicitly.
    """

    MODEL_VERSION = "SIMULATED-no-model"

    def __init__(self, centroid: GeoPoint, bbox: BBox, *, area_km2: float = 10.0,
                 observation_time: datetime | None = None, scene_id: str = "simulated-scene"):
        self.centroid = centroid
        self.bbox = bbox
        self.area_km2 = area_km2
        self.observation_time = observation_time or datetime.now(timezone.utc)
        self.scene_id = scene_id

    def detect(self, scene_path: str, wind_path: Optional[str],
               envelope: EvidenceEnvelope) -> List[SlickDetection]:
        return [SlickDetection(
            slick_id=f"sim-{uuid.uuid4().hex[:8]}",
            scene_id=self.scene_id,
            observation_time=self.observation_time,
            classification=SlickClass.AMBIGUOUS,   # a placeholder must not assert OIL
            confidence=0.0,                        # no model ran; there is no confidence
            mask_path="",
            centroid=self.centroid,
            bbox=self.bbox,
            area_km2=self.area_km2,
            perimeter_km=4.0 * (self.area_km2 ** 0.5),
            elongation=1.0,
            orientation_deg=0.0,
            age_prior_mean_hours=24.0,
            age_prior_std_hours=12.0,
            netra_model_version=self.MODEL_VERSION,
        )]

    def get_model_version(self) -> str:
        return self.MODEL_VERSION


# ----------------------------- the boundary itself -----------------------------

class NetraDetectionBoundary:
    """Runs a `NetraProvider` over event tiles and returns a `StageResult`.

    Never raises for an inference failure: a provider blowing up becomes
    `StageStatus.BLOCKED` with the exception text as the reason, so the caller
    can record an honest "detection unavailable" rather than crash the case.
    """

    def __init__(self, provider: NetraProvider, evidence_mode: EvidenceMode,
                 *, source_id: str, notes: str = "",
                 scientific_status: str = "UNKNOWN", model_metrics: dict | None = None):
        if evidence_mode is EvidenceMode.REAL and isinstance(provider, SimulatedSlickProvider):
            raise ValueError(
                "SimulatedSlickProvider may never be labelled REAL - that is "
                "exactly the provenance upgrade the evidence model forbids."
            )
        self.provider = provider
        self.evidence_mode = evidence_mode
        self.source_id = source_id
        self.notes = notes
        # Travels with every detection this boundary emits. A first baseline
        # must not be presented as a validated model just because it is REAL.
        self.scientific_status = scientific_status
        self.model_metrics = model_metrics or {}

    def envelope(self, case_id: str) -> EvidenceEnvelope:
        return EvidenceEnvelope(
            artifact_id=f"netra-{case_id}",
            produced_by="netra",
            provenance=Provenance(source_id=self.source_id, notes=self.notes),
            mode=self.evidence_mode,
        )

    def detect_tiles(self, tile_paths: list[Path], case_id: str,
                     wind_path: str | None = None) -> StageResult:
        import time

        if not tile_paths:
            return StageResult(
                stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
                reason="NO_SAR_TILES: the event carries no SAR tiles to run inference on.",
            )
        parent = self.envelope(case_id)
        # Reset so the reported peak belongs to THIS sweep, not a prior one.
        if hasattr(self.provider, "last_max_probability"):
            self.provider.last_max_probability = None
        detections: list[SlickDetection] = []
        failures: list[str] = []
        t0 = time.perf_counter()
        for p in tile_paths:
            try:
                detections.extend(self.provider.detect(str(p), wind_path, parent))
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                failures.append(f"{p.name}: {type(exc).__name__}: {exc}")
        runtime = time.perf_counter() - t0

        if failures and not detections:
            return StageResult(
                stage="netra_detection", status=StageStatus.BLOCKED,
                reason="NETRA_INFERENCE_FAILED on every tile: " + "; ".join(failures[:3]),
                runtime_seconds=runtime,
                detail={"n_tiles": len(tile_paths), "failures": failures},
            )
        if not detections:
            return StageResult(
                stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
                reason=(
                    "NO_SLICK_DETECTED: the model ran on "
                    f"{len(tile_paths)} tile(s) and returned no detection above "
                    "threshold. This is a valid scientific outcome, not an error."
                ),
                runtime_seconds=runtime,
                detail={
                    "n_tiles": len(tile_paths),
                    "model_version": self.provider.get_model_version(),
                    "scientific_status": self.scientific_status,
                    "model_metrics": self.model_metrics,
                    "decision_threshold": getattr(
                        getattr(self.provider, "spec", None), "decision_threshold", None),
                    # Peak activation across the sweep. Distinguishes "nearly
                    # fired" from "no representation for this input at all".
                    "max_probability": getattr(self.provider, "last_max_probability", None),
                },
            )
        return StageResult(
            stage="netra_detection", status=StageStatus.PRODUCED,
            value=detections, evidence_mode=self.evidence_mode,
            runtime_seconds=runtime,
            detail={
                "n_tiles": len(tile_paths), "n_detections": len(detections),
                "model_version": self.provider.get_model_version(),
                "scientific_status": self.scientific_status,
                "model_metrics": self.model_metrics,
                "failures": failures,
            },
        )


def _apply_frozen_calibration(spec: NetraModelSpec,
                              freeze: CheckpointFreezeStatus) -> NetraModelSpec:
    """Let the frozen checkpoint's own calibration override the spec defaults.

    Calibration belongs to the model, not to orchestration config. When the
    freeze record carries a swept `best_f1_threshold`, it wins over this
    module's uncalibrated 0.5 placeholder — otherwise every caller would have to
    remember to pass the right number, and the one that forgot would silently
    run at an untuned operating point.

    Architecture fields are NOT silently overridden: a mismatch between the
    caller's spec and the checkpoint's own `model_spec` is a real inconsistency,
    so it raises rather than being papered over.
    """
    import dataclasses

    if freeze.record is None:
        return spec

    ms = freeze.record.model_spec

    for field, expected in (("in_channels", spec.in_channels),
                            ("classes", spec.classes),
                            ("oil_class_index", spec.oil_class_index),
                            ("encoder_name", spec.encoder_name)):
        actual = ms.get(field)
        if actual is not None and actual != expected:
            raise ValueError(
                f"NetraModelSpec.{field}={expected!r} disagrees with the frozen "
                f"checkpoint's own model_spec.{field}={actual!r}. Refusing to run "
                f"inference against a architecture the checkpoint was not trained "
                f"with — fix the spec rather than overriding it here."
            )

    threshold = freeze.record.metrics.get("best_f1_threshold")
    if threshold is None:
        return spec
    return dataclasses.replace(spec, decision_threshold=float(threshold))


def resolve_netra_boundary(
    spec: NetraModelSpec | None,
    *,
    allow_simulated: bool = False,
    simulated_provider: SimulatedSlickProvider | None = None,
    verify_hash: bool = True,
) -> tuple[NetraDetectionBoundary | None, str]:
    """The single decision point for "can we run real NETRA inference?".

    Returns `(boundary, reason)`. `boundary` is None when neither a frozen real
    model nor an explicitly-permitted simulated stand-in is available - the
    caller then records NOT_YET_PRODUCED. `allow_simulated` must be passed
    explicitly by a caller that knows it is running an integration smoke test;
    there is no environment variable or config key that can set it, which is
    what stops a demo from silently becoming "real".
    """
    if spec is not None:
        freeze = check_checkpoint_frozen(spec.checkpoint_path, verify_hash=verify_hash)
        if freeze.frozen:
            spec = _apply_frozen_calibration(spec, freeze)
            provider = FrozenCheckpointNetraProvider(spec, freeze)
            status = freeze.record.scientific_status if freeze.record else None
            return (
                NetraDetectionBoundary(
                    provider, EvidenceMode.REAL,
                    source_id=f"netra.frozen:{spec.model_version}",
                    scientific_status=status or "UNKNOWN",
                    model_metrics=dict(freeze.record.metrics) if freeze.record else {},
                    notes=(
                        "frozen checkpoint sha256="
                        f"{freeze.record.checkpoint_sha256[:16] if freeze.record else '?'}"
                        f"...; decision_threshold={spec.decision_threshold}"
                        + (f"; scientific_status={status}" if status else "")
                    ),
                ),
                f"REAL: {freeze.reason}",
            )
        unfrozen_reason = freeze.reason
    else:
        unfrozen_reason = "NO_MODEL_SPEC_PROVIDED"

    if not allow_simulated:
        return None, unfrozen_reason
    if simulated_provider is None:
        return None, (
            f"{unfrozen_reason}; allow_simulated=True but no simulated_provider "
            "was supplied - this boundary will not invent slick geometry."
        )
    return (
        NetraDetectionBoundary(
            simulated_provider, EvidenceMode.SIMULATED,
            source_id="netra.simulated_placeholder",
            notes=(
                "NOT a NETRA detection. Explicitly-requested simulated slick "
                f"geometry standing in for real inference because: {unfrozen_reason}"
            ),
        ),
        f"SIMULATED (explicitly requested): {unfrozen_reason}",
    )


# --------------------------- mask -> SlickDetection ---------------------------

def _detection_from_mask(*, mask: np.ndarray, probs: np.ndarray, tile_path: Path,
                         model_version: str) -> SlickDetection:
    """Geometry only. Every field is measured off the predicted mask and the
    tile's own georeferencing; nothing is defaulted to a nice-looking number."""
    meta = _tile_geometry(tile_path)
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    bb = meta["bbox"]
    lon_span = bb["max_lon"] - bb["min_lon"]
    lat_span = bb["max_lat"] - bb["min_lat"]

    def to_lon(px):
        return bb["min_lon"] + (px + 0.5) / w * lon_span

    def to_lat(py):
        return bb["max_lat"] - (py + 0.5) / h * lat_span

    centroid = GeoPoint(lon=float(to_lon(xs.mean())), lat=float(to_lat(ys.mean())))
    min_lon, max_lon = float(to_lon(xs.min())), float(to_lon(xs.max()))
    min_lat, max_lat = float(to_lat(ys.max())), float(to_lat(ys.min()))
    # A single-pixel-wide detection yields a degenerate box; nudge by one pixel
    # rather than emit one that fails BBox's own validator.
    if max_lon <= min_lon:
        max_lon = min_lon + lon_span / w
    if max_lat <= min_lat:
        max_lat = min_lat + lat_span / h

    px_lat_m = lat_span / h * _M_PER_DEG_LAT
    px_lon_m = lon_span / w * _M_PER_DEG_LAT * float(np.cos(np.radians(centroid.lat)))
    area_km2 = float(mask.sum()) * px_lat_m * px_lon_m / 1e6

    return SlickDetection(
        slick_id=f"netra-{tile_path.stem}-{uuid.uuid4().hex[:6]}",
        scene_id=meta["parent_scene_id"],
        observation_time=meta["observation_time"],
        classification=SlickClass.OIL,
        confidence=float(probs[mask].mean()),
        mask_path=str(tile_path),
        centroid=centroid,
        bbox=BBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat),
        area_km2=max(area_km2, 1e-6),
        perimeter_km=float(_perimeter_km(mask, px_lat_m, px_lon_m)),
        elongation=float(_elongation(ys, xs)),
        orientation_deg=float(_orientation_deg(ys, xs)),
        age_prior_mean_hours=24.0,
        age_prior_std_hours=12.0,
        netra_model_version=model_version,
    )


def _perimeter_km(mask: np.ndarray, px_lat_m: float, px_lon_m: float) -> float:
    vertical = np.abs(np.diff(mask.astype(np.int8), axis=0)).sum() * px_lon_m
    horizontal = np.abs(np.diff(mask.astype(np.int8), axis=1)).sum() * px_lat_m
    return (vertical + horizontal) / 1000.0


def _elongation(ys: np.ndarray, xs: np.ndarray) -> float:
    if len(xs) < 2:
        return 1.0
    cov = np.cov(np.vstack([xs.astype(float), ys.astype(float)]))
    vals = np.clip(np.linalg.eigvalsh(cov), 1e-12, None)
    return float(np.sqrt(vals[-1] / vals[0]))


def _orientation_deg(ys: np.ndarray, xs: np.ndarray) -> float:
    if len(xs) < 2:
        return 0.0
    cov = np.cov(np.vstack([xs.astype(float), ys.astype(float)]))
    _, vecs = np.linalg.eigh(cov)
    vx, vy = vecs[:, -1]
    return float(np.degrees(np.arctan2(vy, vx)) % 180.0)


def _tile_geometry(tile_path: Path) -> dict:
    """Read the tile's real bbox/scene/time out of the Gold `tile_records.json`
    beside it. Raises if absent - a detection with invented georeferencing is
    worse than no detection."""
    records_path = tile_path.parent.parent / "tile_records.json"
    if not records_path.exists():
        raise FileNotFoundError(
            f"no tile_records.json beside {tile_path}; cannot georeference a detection"
        )
    records = json.loads(records_path.read_text(encoding="utf-8"))
    rec = next((r for r in records if r["tile_id"] == tile_path.stem), None)
    if rec is None:
        raise KeyError(f"tile {tile_path.stem!r} not present in {records_path}")
    obs = rec.get("observation_time") or rec.get("timestamp")
    if obs is None:
        manifest = tile_path.parents[2] / "manifest.json"
        obs = json.loads(manifest.read_text(encoding="utf-8"))["modalities"]["sar"]["timestamp"]
    t = datetime.fromisoformat(obs)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return {"bbox": rec["bbox"], "parent_scene_id": rec["parent_scene_id"],
            "observation_time": t}
