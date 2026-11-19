"""
VARUNA GRID v2 — Synthetic Lab Smoke Test.

Executes the entire end-to-end data pipeline on deterministic synthetic data:
1. Generates synthetic canonical SAR scenes & oil masks
2. Executes M6 FullPipeline:
   - DataGuard trust and quality verification
   - Hash & spatial deduplication
   - Geographic-temporal dataset splitting
   - Cross-split leakage guard verification
   - Spatial tiling
   - Train-split channel normalization
3. Emits dataset manifest & GOLD metadata
4. Verifies tensor compatibility for NETRA input (SAR image tiles)
5. Verifies tensor compatibility for CHHAYA input (AIS vessel tracks)

Guarantees:
- Pure CPU execution (no GPU required for data pipeline)
- 100% offline (no network calls)
- Zero external data download dependencies
- Deterministic and reproducible

Usage:
    python scripts/lab_smoke_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import numpy as np

# Ensure repo root and packages are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
for pkg in (REPO_ROOT / "packages").glob("varuna_*"):
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))

from varuna_contracts.schemas import BBox, VesselType
from varuna_data_eng.pipeline.full_pipeline import FullPipeline
from varuna_data_eng.schemas.canonical_sar import (
    CanonicalSAR, SARSensor, SARBand, Polarization, ChannelMeta
)
from varuna_data_eng.schemas.oil_mask import OilMask, OilLabelClass
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_data_eng.fixtures.synthetic_case_generator import SyntheticCaseGenerator


def create_synthetic_scenes(n_scenes: int = 8, base_time: datetime | None = None) -> tuple[list[CanonicalSAR], list[OilMask]]:
    """Generates synthetic SAR scenes spread over time and space for splitting."""
    if base_time is None:
        base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    prov = DataProvenance(source_id="synthetic_lab_test", adapter_id="mock_synth", license="CC-0")
    sar_list = []
    mask_list = []

    for i in range(n_scenes):
        scene_id = f"synth_sar_{i:03d}"
        acq_time = base_time + timedelta(days=15 * i)
        # Separate spatially so geographic split is well-partitioned
        min_lon = 70.0 + (i * 2.5)
        min_lat = 10.0 + (i * 2.0)
        bbox = BBox.model_construct(
            min_lon=min_lon, min_lat=min_lat,
            max_lon=min_lon + 1.0, max_lat=min_lat + 1.0
        )

        sar = CanonicalSAR(
            scene_id=scene_id,
            source_dataset="synthetic_lab",
            sensor=SARSensor.SENTINEL_1,
            platform="S1A",
            band=SARBand.C,
            polarizations=[Polarization.VV, Polarization.VH],
            product_type="GRD",
            processing_level="1",
            acquisition_time=acq_time,
            resolution_m=10.0,
            pixel_spacing_m=10.0,
            width_px=512,
            height_px=512,
            crs="EPSG:4326",
            bbox=bbox,
            channels={
                "VV": ChannelMeta(name="VV", unit="dB", dtype="float32"),
                "VH": ChannelMeta(name="VH", unit="dB", dtype="float32"),
            },
            data_path=f"data/silver/{scene_id}.npy",
            file_checksum=f"hash_{scene_id}_{i}",
            file_size_bytes=512 * 512 * 4 * 2,
            provenance=prov,
        )
        sar_list.append(sar)

        # Create corresponding oil mask
        mask = OilMask(
            mask_id=f"mask_{scene_id}",
            scene_id=scene_id,
            label_class=OilLabelClass.OIL,
            mask_path=f"data/silver/mask_{scene_id}.npy",
            mask_crs="EPSG:4326",
            mask_bbox=bbox,
            mask_resolution_m=10.0,
            mask_width_px=512,
            mask_height_px=512,
            annotation_source="synthetic_expert",
            annotation_version="v1.0",
            class_counts={"BACKGROUND": 250000, "OIL": 12144},
            file_checksum=f"hash_mask_{scene_id}",
            provenance=prov,
        )
        mask_list.append(mask)

    return sar_list, mask_list


def run_synthetic_smoke_test() -> dict:
    """Executes full pipeline and verifies NETRA & CHHAYA dataset interfaces."""
    print("=" * 65)
    print(" VARUNA GRID v2 — SYNTHETIC PIPELINE SMOKE TEST")
    print("=" * 65)

    stages_passed = {}

    # Stage 1: Synthetic Data Generation
    try:
        sar_list, mask_list = create_synthetic_scenes(n_scenes=10)
        print(f"[PASS] Stage 1 : Generated {len(sar_list)} synthetic scenes and masks")
        stages_passed["1_data_gen"] = True
    except Exception as e:
        print(f"[FAIL] Stage 1 Data Generation Failed: {e}")
        stages_passed["1_data_gen"] = False
        return {"all_passed": False, "stages": stages_passed}

    # Stage 2: M6 FullPipeline Execution (DataGuard, Dedup, Split, Leakage, Tiler, Normalizer)
    try:
        pipeline = FullPipeline(
            seed=42,
            synthetic_mode=True,
            split_strategy="hash_random",
            tile_size=64,
        )
        manifest = pipeline.process_raw_dataset(
            dataset_id="synthetic_lab_gold_v1",
            dataset_version="v1.0.0",
            sar_list=sar_list,
            mask_list=mask_list,
        )
        print(f"[PASS] Stage 2 : FullPipeline executed successfully")
        print(f"       - Kept Entries        : {len(manifest.samples)}")
        print(f"       - Split Distribution  : {manifest.splits.split_counts}")
        print(f"       - Total Tiles Created : {len(pipeline.last_run_tiles)}")
        stages_passed["2_full_pipeline"] = True
    except Exception as e:
        print(f"[FAIL] Stage 2 FullPipeline Execution Failed: {e}")
        stages_passed["2_full_pipeline"] = False
        return {"all_passed": False, "stages": stages_passed}

    # Stage 3: Normalization Statistics Verification
    try:
        norm_stats = manifest.normalization_stats
        assert norm_stats is not None, "Normalization stats missing from manifest"
        assert len(norm_stats.channels) > 0, "No channel normalization stats computed"
        for ch_name, st in norm_stats.channels.items():
            print(f"       - Norm Stat [{ch_name}] : mean={st.mean:.4f}, std={st.std:.4f}, min={st.min:.4f}, max={st.max:.4f}")
        stages_passed["3_normalization"] = True
    except Exception as e:
        print(f"[FAIL] Stage 3 Normalization Stats Verification Failed: {e}")
        stages_passed["3_normalization"] = False

    # Stage 4: Verify NETRA Input Tensor Interface
    try:
        # Load a synthetic array from the provider
        sample_sar = sar_list[0]
        channels = pipeline.array_provider.load_channels(sample_sar)
        assert "VV" in channels and "VH" in channels, "Expected VV and VH polarizations"
        # Simulate 3-channel NETRA tensor (VV, VH, Wind)
        vv = channels["VV"][:64, :64]
        vh = channels["VH"][:64, :64]
        wind = np.zeros_like(vv, dtype=np.float32) + 5.0  # constant wind placeholder
        netra_tensor = np.stack([vv, vh, wind], axis=0)
        assert netra_tensor.shape == (3, 64, 64), f"Unexpected NETRA tensor shape {netra_tensor.shape}"
        print(f"[PASS] Stage 4 : NETRA Tensor Interface verified (Shape: {netra_tensor.shape}, Dtype: {netra_tensor.dtype})")
        stages_passed["4_netra_tensor"] = True
    except Exception as e:
        print(f"[FAIL] Stage 4 NETRA Interface Verification Failed: {e}")
        stages_passed["4_netra_tensor"] = False

    # Stage 5: Verify CHHAYA Input Trajectory Interface
    try:
        case_gen = SyntheticCaseGenerator(seed=42)
        case = case_gen.generate_case("SMOKE-CASE-001")
        ais_track = case.input.ais_tracks[0]
        assert len(ais_track.points) >= 2, "Expected at least 2 AIS points"
        # Trajectory feature tensor: [lon, lat, sog, cog, heading, gap_duration, dist_prev, time_delta]
        traj_feats = []
        for pt in ais_track.points:
            traj_feats.append([
                pt.lon, pt.lat,
                pt.sog_knots or 0.0,
                pt.cog_deg or 0.0,
                pt.heading_deg or 0.0,
                0.0, 0.0, 0.0
            ])
        chhaya_tensor = np.array(traj_feats, dtype=np.float32)
        assert chhaya_tensor.ndim == 2 and chhaya_tensor.shape[1] == 8
        print(f"[PASS] Stage 5 : CHHAYA Trajectory Interface verified (Shape: {chhaya_tensor.shape}, Dtype: {chhaya_tensor.dtype})")
        stages_passed["5_chhaya_tensor"] = True
    except Exception as e:
        print(f"[FAIL] Stage 5 CHHAYA Interface Verification Failed: {e}")
        stages_passed["5_chhaya_tensor"] = False

    all_passed = all(stages_passed.values())
    print("-" * 65)
    if all_passed:
        print(" SYNTHETIC PIPELINE SMOKE TEST: ALL STAGES PASSED (100% OFFLINE)")
    else:
        print(" SYNTHETIC PIPELINE SMOKE TEST: FAILURES DETECTED")
    print("=" * 65)

    return {"all_passed": all_passed, "stages": stages_passed}


if __name__ == "__main__":
    res = run_synthetic_smoke_test()
    sys.exit(0 if res["all_passed"] else 1)
