"""
VARUNA GRID v2 — Zenodo Part I Gold Dataset Builder.

Executes complete Data Engineering pipeline to generate ML-ready Gold tensors:
- Reads Zenodo GeoTIFFs using ZenodoAdapter
- Runs DataGuard, Dedup, Hash-Random Splitting (DEVELOPMENT split)
- Performs spatial tiling (512x512) and train-split channel normalization
- Emits ML tensors to data/gold/netra/
- Emits manifest
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

# Add repo root and packages to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
packages_dir = REPO_ROOT / "packages"
if str(packages_dir) not in sys.path:
    sys.path.insert(0, str(packages_dir))

from varuna_data_eng.pipeline.full_pipeline import FullPipeline
from varuna_data_eng.pipeline.array_provider import RealZenodoArrayProvider
from varuna_data_eng.varuna_source_adapters.zenodo_adapter import ZenodoAdapter
from varuna_data_eng.schemas.quality import QualityVerdict

def check_determinism(sar_list, mask_list):
    """Run pipeline twice on a small deterministic subset to ensure identical outputs."""
    print("--- Running Determinism Check (Phase 15) ---")
    subset_sar = sar_list[:3]
    subset_mask = mask_list[:3]
    
    pipeline1 = FullPipeline(
        seed=42,
        synthetic_mode=False,
        split_strategy="hash_random",
        tile_size=512,
        array_provider=RealZenodoArrayProvider()
    )
    manifest1 = pipeline1.process_raw_dataset(
        dataset_id="zenodo_part1_det",
        dataset_version="det_check",
        sar_list=subset_sar,
        mask_list=subset_mask
    )
    
    pipeline2 = FullPipeline(
        seed=42,
        synthetic_mode=False,
        split_strategy="hash_random",
        tile_size=512,
        array_provider=RealZenodoArrayProvider()
    )
    manifest2 = pipeline2.process_raw_dataset(
        dataset_id="zenodo_part1_det",
        dataset_version="det_check",
        sar_list=subset_sar,
        mask_list=subset_mask
    )
    
    assert manifest1.content_hash == manifest2.content_hash, "Determinism check failed: Manifest hashes differ"
    print("[PASS] Determinism check passed.")

def build_zenodo_gold(data_dir: str, tile_size: int = 512, limit: int = None):
    print("=" * 70)
    print(" VARUNA GRID v2 — ZENODO PART I GOLD DATASET GENERATION")
    print("=" * 70)
    
    base_dir = REPO_ROOT
    gold_netra = base_dir / "data" / "gold" / "netra"
    manifest_dir = base_dir / "data" / "manifests"
    report_dir = base_dir / "reports"
    
    for d in [gold_netra, manifest_dir, report_dir]:
        d.mkdir(parents=True, exist_ok=True)
        
    print("[INFO] Discovering Zenodo dataset...")
    adapter = ZenodoAdapter(data_dir)
    sar_list, mask_list = adapter.discover(limit=limit)
    print(f"[INFO] Discovered {len(sar_list)} image-mask pairs.")
    
    # 4. PILOT-FIRST
    if limit is None and len(sar_list) >= 5:
        print("\n--- Running Pilot Pass (3-5 scenes) ---")
        pilot_sar = sar_list[:5]
        pilot_mask = mask_list[:5]
        
        pilot_pipeline = FullPipeline(
            seed=42,
            synthetic_mode=False,
            split_strategy="hash_random",
            tile_size=tile_size,
            array_provider=RealZenodoArrayProvider()
        )
        pilot_manifest = pilot_pipeline.process_raw_dataset(
            dataset_id="zenodo_part1",
            dataset_version="NETRA-GOLD-v0.1-pilot",
            sar_list=pilot_sar,
            mask_list=pilot_mask
        )
        print(f"[PASS] Pilot generation complete. {len(pilot_manifest.samples)} samples accepted.")
        
        check_determinism(pilot_sar, pilot_mask)
        
    print("\n--- Running Full Dataset Processing ---")
    pipeline = FullPipeline(
        seed=42,
        synthetic_mode=False,
        split_strategy="hash_random",
        tile_size=tile_size,
        array_provider=RealZenodoArrayProvider()
    )
    manifest = pipeline.process_raw_dataset(
        dataset_id="zenodo_part1",
        dataset_version="NETRA-GOLD-v0.1",
        sar_list=sar_list,
        mask_list=mask_list
    )
    
    # Analyze results
    accepted = len(manifest.samples)
    total = len(sar_list)
    quarantined = total - accepted
    
    report = manifest.quality_report
    rejected = report.rejected
    # Duplicates are the difference between (total - rejected) and accepted
    duplicates = total - rejected - accepted
    
    print(f"\n[REPORT] Full Processing Results:")
    print(f"  Total Pairs  : {total}")
    print(f"  Accepted     : {accepted}")
    print(f"  Quarantined  : {quarantined} (Quality Rejected: {rejected}, Duplicates: {duplicates})")
    
    # Write quality report
    q_report_data = {
        "total_pairs": total,
        "accepted": accepted,
        "quarantined": quarantined,
        "quality_rejected": rejected,
        "duplicates": duplicates
    }
    with open(report_dir / "zenodo_part1_quality.json", "w") as f:
        json.dump(q_report_data, f, indent=2)
    with open(report_dir / "zenodo_part1_quality.txt", "w") as f:
        for k, v in q_report_data.items():
            f.write(f"{k}: {v}\n")
            
    # Generate GOLD tiles
    print(f"\n[INFO] Generating GOLD tiles on disk at {gold_netra}...")
    import rasterio
    
    tiles_written = 0
    norm_stats = manifest.normalization_stats
    
    mask_map = {m.scene_id: m for m in mask_list}
    
    train_tiles, val_tiles, test_tiles = 0, 0, 0
    
    for entry in manifest.samples:
        sar = next(s for s in sar_list if s.scene_id == entry.scene_id)
        mask_obj = mask_map[entry.scene_id]
        
        provider = RealZenodoArrayProvider()
        channels = provider.load_channels(sar)
        
        vv = channels["VV"]
        vh = channels["VH"]
        
        vv_norm = pipeline.normalizer.apply(vv, "VV", norm_stats)
        vh_norm = pipeline.normalizer.apply(vh, "VH", norm_stats)
        
        img_full = np.stack([vv_norm, vh_norm], axis=0)
        
        with rasterio.open(mask_obj.mask_path) as m_src:
            mask_full = m_src.read(1).astype(np.uint8)
            
        h, w = mask_full.shape
        stride = tile_size
        
        for y in range(0, h - tile_size + 1, stride):
            for x in range(0, w - tile_size + 1, stride):
                img_tile = img_full[:, y:y+tile_size, x:x+tile_size]
                mask_tile = mask_full[y:y+tile_size, x:x+tile_size]
                
                tile_id = f"{entry.scene_id}_{entry.split}_{x}_{y}"
                img_path = gold_netra / f"{tile_id}_img.npy"
                m_path = gold_netra / f"{tile_id}_mask.npy"
                
                np.save(img_path, img_tile)
                np.save(m_path, mask_tile)
                tiles_written += 1
                
                if entry.split == "train":
                    train_tiles += 1
                elif entry.split == "val":
                    val_tiles += 1
                else:
                    test_tiles += 1
                    
    print(f"[PASS] Emitted {tiles_written} GOLD tile pairs.")
    print(f"       Train: {train_tiles} | Val: {val_tiles} | Test: {test_tiles}")

    # Write Manifest
    manifest_out = manifest_dir / "zenodo_part1_manifest.json"
    manifest_out.write_text(manifest.model_dump_json(indent=2))
    print(f"[PASS] Saved manifest to {manifest_out}")

    print("=" * 70)
    print(" ZENODO GOLD PIPELINE COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, default="data/raw/zenodo/extracted/part1")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    
    build_zenodo_gold(data_dir=args.data_dir, limit=args.limit)
