import os
import sys
import json
import hashlib
import subprocess
import shutil
from pathlib import Path

def compute_sha256(filepath):
    print(f"Computing SHA-256 for {filepath.name}...")
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def main():
    repo_root = Path("d:/ROUTER(DATASETS)/VARUNA")
    downloads_dir = repo_root / "data" / "raw" / "zenodo" / "downloads" / "zenodo part 2"
    extracted_dir = repo_root / "data" / "raw" / "zenodo" / "extracted" / "part2"
    
    extracted_dir.mkdir(parents=True, exist_ok=True)
    
    archives = [
        "01_Train_Val_Lookalike_images.7z",
        "01_Train_Val_Lookalike_mask.7z",
        "01_Train_Val_No_Oil_Images.7z",
        "01_Train_Val_No_Oil_mask.7z"
    ]
    
    print("=== PHASE 2: ARCHIVE INTEGRITY ===")
    hashes = {}
    for arc in archives:
        arc_path = downloads_dir / arc
        if arc_path.exists():
            size = arc_path.stat().st_size
            h = compute_sha256(arc_path)
            hashes[arc] = {"size": size, "sha256": h}
            print(f"{arc}: Size={size}, SHA256={h}")
        else:
            print(f"MISSING: {arc}")
            
    print("\n=== PHASE 3: SAFE EXTRACTION ===")
    total, used, free = shutil.disk_usage(extracted_dir)
    print(f"Disk Free Space: {free / (1024**3):.2f} GB")
    
    # We estimate extraction size by a factor of 1.5x of the total archive sizes
    if free < 100 * (1024**3):
        print("WARNING: Disk free space is less than 100GB! Proceeding cautiously...")
    
    # Extraction targets
    targets = {
        "01_Train_Val_Lookalike_images.7z": "Lookalike",
        "01_Train_Val_Lookalike_mask.7z": "Lookalike",
        "01_Train_Val_No_Oil_Images.7z": "No_Oil",
        "01_Train_Val_No_Oil_mask.7z": "No_Oil"
    }
    
    for arc, target_folder in targets.items():
        arc_path = downloads_dir / arc
        target_path = extracted_dir / target_folder
        if not arc_path.exists():
            continue
            
        # check if it already has files
        if target_path.exists() and ("mask" in arc.lower() and (target_path / "labels").exists() or "image" in arc.lower() and (target_path / "images").exists() or len(list(target_path.rglob("*.tif"))) > 0):
            # Wait, the zip structure might extract to images/labels. Let's just blindly extract and accept everything, or check if it's already extracted.
            # If the folder has .tif files, we might just assume it's extracted, but since Lookalike and No_Oil masks/images are split across two archives, we should probably just extract with -aos (skip existing).
            pass
            
        print(f"Extracting {arc} to {target_folder}...")
        target_path.mkdir(exist_ok=True)
        # Use -aos to skip existing files to avoid re-extracting the already extracted Lookalike images
        cmd = ["7z", "x", f"-o{target_path}", str(arc_path), "-y", "-aos"]
        try:
            subprocess.run(cmd, check=True)
            print(f"Done extracting {arc}.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to extract {arc}: {e}")
            
    print("\n=== PHASE 4: COMPLETE DATASET INVENTORY ===")
    inventory = {}
    for target_folder in set(targets.values()):
        target_path = extracted_dir / target_folder
        if target_path.exists():
            files = list(target_path.rglob("*.tif"))
            total_size = sum(f.stat().st_size for f in files)
            inventory[target_folder] = {
                "count": len(files),
                "total_size_bytes": total_size
            }
            print(f"{target_folder}: {len(files)} files, {total_size / (1024**3):.2f} GB")
            
    # Save discovery report
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    with open(reports_dir / "zenodo_part2_discovery.json", "w") as f:
        json.dump({"hashes": hashes, "inventory": inventory}, f, indent=2)
        
    print("Discovery complete.")

if __name__ == "__main__":
    main()
