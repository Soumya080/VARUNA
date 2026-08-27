"""P1-6: NETRA's inference path must actually consume the shared
NormalizationRecord + normalize_sar_tile() function the data-engineering
pipeline defines, not recompute its own statistics or ignore normalization
entirely.
"""
import numpy as np
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from varuna_contracts.evidence import EvidenceEnvelope, Provenance
from varuna_domain.model_registry import InMemoryModelRegistry, ModelStatus
from varuna_infra.model_loader import ModelLoader
from varuna_netra.inference import NetraInferenceService
from varuna_data_eng.schemas.normalization import NormalizationRecord, ChannelStats


def _approved_loader():
    registry = InMemoryModelRegistry()
    registry.register("netra", "v1", "path/to/model", "dsv1", {}, "commit1")
    registry.update_status("netra", "v1", ModelStatus.EVALUATED)
    registry.update_status("netra", "v1", ModelStatus.APPROVED, approved_by="user1")
    return ModelLoader(registry)


def _norm_record():
    return NormalizationRecord(
        dataset_version="v1",
        sensor="SENTINEL_1",
        channels={
            "VV": ChannelStats(mean=0.0, std=1.0, min=-1.0, max=1.0, p2=-0.9, p98=0.9),
            "VH": ChannelStats(mean=0.0, std=1.0, min=-1.0, max=1.0, p2=-0.9, p98=0.9),
        },
        method="standard_p2_p98",
        computed_from_split="train",
        n_samples=100,
        computed_at=datetime.now(timezone.utc),
        checksum="abc123",
    )


def test_netra_uses_shared_normalization_when_arrays_available():
    temp_dir = Path(tempfile.gettempdir()) / "varuna_tests"
    temp_dir.mkdir(parents=True, exist_ok=True)
    scene_path = str(temp_dir / "gold_scene.tif")
    np.savez(f"{scene_path}.npz", vv=np.random.randn(8, 8).astype(np.float32),
             vh=np.random.randn(8, 8).astype(np.float32))

    service = NetraInferenceService(_approved_loader(), "v1", normalization_record=_norm_record())

    envelope = EvidenceEnvelope(
        artifact_id="art1", produced_by="test_runner", provenance=Provenance(source_id="test")
    )
    detections = service.detect(scene_path, None, envelope)

    assert len(detections) == 1
    # The shared normalize_sar_tile() path must have actually run.
    assert service.last_normalized_input is not None
    assert service.last_normalized_input.shape == (3, 8, 8)
    assert service.last_normalized_input.min() >= 0.0
    assert service.last_normalized_input.max() <= 1.0


def test_netra_without_normalization_record_is_unaffected():
    """Backward compatibility: omitting normalization_record must not break
    existing callers or force normalization to run."""
    service = NetraInferenceService(_approved_loader(), "v1")
    envelope = EvidenceEnvelope(
        artifact_id="art1", produced_by="test_runner", provenance=Provenance(source_id="test")
    )
    detections = service.detect("scene_without_sidecar.tif", None, envelope)
    assert len(detections) == 1
    assert service.last_normalized_input is None
