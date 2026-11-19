import hashlib
from pathlib import Path
from typing import List, Tuple
from datetime import datetime, timezone
import rasterio

from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization, ChannelMeta
from varuna_data_eng.schemas.oil_mask import OilMask, OilLabelClass
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_contracts.schemas import BBox

class ZenodoPart2Adapter:
    """Discovers and parses Zenodo Part 2 SAR and OilMask TIFF files into canonical schemas."""
    def __init__(self, raw_dir: str):
        self.extracted_dir = Path(raw_dir)
        self.categories = {
            "Lookalike": ("Lookalike", "Mask_lookalike"),
            "No_Oil": ("No_oil", "Mask_no_oil")
        }
        
    def _compute_sha256(self, path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def discover(self, limit: int = None) -> Tuple[List[CanonicalSAR], List[OilMask]]:
        sar_list = []
        mask_list = []
        
        for cat, (img_sub, mask_sub) in self.categories.items():
            img_dir = self.extracted_dir / cat / img_sub
            mask_dir = self.extracted_dir / cat / mask_sub
            
            if not img_dir.exists():
                continue
                
            image_paths = sorted(img_dir.glob("*.tif"))
            
            for img_path in image_paths:
                if limit is not None and len(sar_list) >= limit:
                    break
                    
                scene_id = img_path.stem
                mask_path = mask_dir / f"{scene_id}.tif"
                
                if not mask_path.exists():
                    print(f"[WARN] No mask found for {cat}/{scene_id}. Skipping.")
                    continue
                    
                img_checksum = self._compute_sha256(img_path)
                mask_checksum = self._compute_sha256(mask_path)
                
                dummy_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
                
                provenance = DataProvenance(
                    source_id="zenodo_part2",
                    adapter_id="zenodo_part2_adapter",
                    license="CC-BY-4.0",
                    original_filename=f"{cat}/{img_path.name}"
                )
                
                with rasterio.open(img_path) as src:
                    width, height = src.width, src.height
                    res = src.res[0] if src.res else 0.0000898
                    bounds = src.bounds
                    
                sar = CanonicalSAR(
                    scene_id=f"zenodo_p2_{cat}_{scene_id}",
                    source_dataset="zenodo_part2",
                    sensor=SARSensor.SENTINEL_1,
                    platform="SENTINEL-1",
                    band=SARBand.C,
                    polarizations=[Polarization.VV, Polarization.VH],
                    product_type="GRD",
                    processing_level="1",
                    acquisition_time=dummy_time,
                    resolution_m=10.0,
                    pixel_spacing_m=10.0,
                    width_px=width,
                    height_px=height,
                    crs="EPSG:4326",
                    bbox=BBox(min_lon=bounds.left, max_lon=bounds.right, min_lat=bounds.bottom, max_lat=bounds.top),
                    channels={
                        "VV": ChannelMeta(name="VV", unit="dB", dtype="float32"),
                        "VH": ChannelMeta(name="VH", unit="dB", dtype="float32")
                    },
                    data_path=str(img_path),
                    file_checksum=img_checksum,
                    file_size_bytes=img_path.stat().st_size,
                    provenance=provenance,
                    metadata={"timestamp_status": "unavailable", "original_category": cat}
                )
                
                mask = OilMask(
                    mask_id=f"mask_{cat}_{scene_id}",
                    scene_id=f"zenodo_p2_{cat}_{scene_id}",
                    label_class=OilLabelClass.OIL,  # Will map all pixels to 0 downstream since it's Lookalike/No_Oil
                    mask_path=str(mask_path),
                    mask_crs="EPSG:4326",
                    mask_bbox=sar.bbox,
                    mask_resolution_m=10.0,
                    mask_width_px=width,
                    mask_height_px=height,
                    annotation_source="zenodo",
                    annotation_version="1.0",
                    class_counts={"0": width * height, "1": 0},
                    file_checksum=mask_checksum,
                    provenance=provenance
                )
                
                sar_list.append(sar)
                mask_list.append(mask)
                
        return sar_list, mask_list
