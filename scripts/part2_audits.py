import os
import sys
import json
import hashlib
import rasterio
import numpy as np
from pathlib import Path

def compute_sha256(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def audit_representative(category, path, is_mask=False):
    print(f"\nAuditing {category} ({'Mask' if is_mask else 'Image'}): {path.name}")
    try:
        with rasterio.open(path) as src:
            data = src.read()
            has_nan = np.isnan(data).any()
            has_inf = np.isinf(data).any()
            unique_vals = np.unique(data).tolist() if is_mask else None
            
            info = {
                "width": src.width,
                "height": src.height,
                "bands": src.count,
                "dtype": str(data.dtype),
                "crs": src.crs.to_string() if src.crs else None,
                "transform": [float(x) for x in src.transform],
                "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
                "resolution": src.res,
                "nodata": src.nodata,
                "has_nan": bool(has_nan),
                "has_inf": bool(has_inf),
                "unique_values": unique_vals
            }
            print(json.dumps(info, indent=2))
            return info
    except Exception as e:
        print(f"Error auditing {path}: {e}")
        return None

def main():
    repo_root = Path("d:/ROUTER(DATASETS)/VARUNA")
    extracted_dir = repo_root / "data" / "raw" / "zenodo" / "extracted" / "part2"
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    categories = {
        "Lookalike": ("Lookalike", "Mask_lookalike"),
        "No_Oil": ("No_oil", "Mask_no_oil")
    }
    
    print("=== PHASE 5 & 6: REPRESENTATIVE AUDITS ===")
    audit_results = {}
    for cat, (img_sub, mask_sub) in categories.items():
        img_dir = extracted_dir / cat / img_sub
        mask_dir = extracted_dir / cat / mask_sub
        
        audit_results[cat] = {"images": [], "masks": []}
        
        # Images
        if img_dir.exists():
            img_files = list(img_dir.glob("*.tif"))[:3]
            for f in img_files:
                audit_results[cat]["images"].append(audit_representative(f"{cat}_image", f, is_mask=False))
                
        # Masks
        if mask_dir.exists():
            mask_files = list(mask_dir.glob("*.tif"))[:3]
            for f in mask_files:
                audit_results[cat]["masks"].append(audit_representative(f"{cat}_mask", f, is_mask=True))
                
    with open(reports_dir / "zenodo_part2_representative_audit.json", "w") as f:
        json.dump(audit_results, f, indent=2)

    print("\n=== PHASE 9-12: HASH FORENSICS ===")
    image_hashes = {}
    mask_hashes = {}
    pair_hashes = {}
    
    for cat, (img_sub, mask_sub) in categories.items():
        img_dir = extracted_dir / cat / img_sub
        mask_dir = extracted_dir / cat / mask_sub
        
        if not img_dir.exists():
            continue
            
        img_files = list(img_dir.glob("*.tif"))
        for i, img_path in enumerate(img_files):
            if i % 100 == 0:
                print(f"Hashing {cat}: {i}/{len(img_files)}")
                
            scene_id = img_path.stem
            img_hash = compute_sha256(img_path)
            
            if img_hash not in image_hashes:
                image_hashes[img_hash] = []
            image_hashes[img_hash].append(f"{cat}/{scene_id}")
            
            mask_path = mask_dir / f"{scene_id}.tif"
            if mask_path.exists():
                mask_hash = compute_sha256(mask_path)
                if mask_hash not in mask_hashes:
                    mask_hashes[mask_hash] = []
                mask_hashes[mask_hash].append(f"{cat}_mask/{scene_id}")
                
                pair_id = f"{img_hash}_{mask_hash}"
                if pair_id not in pair_hashes:
                    pair_hashes[pair_id] = []
                pair_hashes[pair_id].append(f"{cat}/{scene_id}")
                
    # Save reports
    with open(reports_dir / "zenodo_part2_image_hash_audit.json", "w") as f:
        json.dump({k: v for k, v in image_hashes.items() if len(v) > 1}, f, indent=2)
        
    with open(reports_dir / "zenodo_part2_mask_hash_audit.json", "w") as f:
        json.dump({k: v for k, v in mask_hashes.items() if len(v) > 1}, f, indent=2)
        
    with open(reports_dir / "zenodo_part2_pair_hash_audit.json", "w") as f:
        json.dump({k: v for k, v in pair_hashes.items() if len(v) > 1}, f, indent=2)
        
    print("Forensics complete.")

if __name__ == "__main__":
    main()
