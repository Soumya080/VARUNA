import hashlib
from pathlib import Path
from typing import List, Tuple, Dict
from datetime import datetime, timezone
import rasterio

from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization, ChannelMeta
from varuna_data_eng.schemas.oil_mask import OilMask, OilLabelClass
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_contracts.schemas import BBox

class ZenodoAdapter:
    """Discovers and parses Zenodo SAR and OilMask TIFF files into canonical schemas."""
    def __init__(self, raw_dir: str):
        self.raw_dir = Path(raw_dir)
        self.images_dir = self.raw_dir
        self.masks_dir = self.raw_dir / "Mask_oil"
        
    def _compute_sha256(self, path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def discover(self, limit: int = None) -> Tuple[List[CanonicalSAR], List[OilMask]]:
        image_paths = sorted(self.images_dir.glob("*.tif"))
        if limit is not None:
            image_paths = image_paths[:limit]
            
        sar_list = []
        mask_list = []
        
        for img_path in image_paths:
            scene_id = img_path.stem
            mask_path = self.masks_dir / f"{scene_id}.tif"
            
            if not mask_path.exists():
                print(f"[WARN] No mask found for {scene_id}. Skipping.")
                continue
                
            img_checksum = self._compute_sha256(img_path)
            mask_checksum = self._compute_sha256(mask_path)
            
            # Using dummy timestamp but explicitly stating it's unavailable.
            dummy_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
            
            provenance = DataProvenance(
                source_id="zenodo_part1",
                adapter_id="zenodo_adapter",
                license="CC-BY-4.0",
                original_filename=img_path.name
            )
            
            with rasterio.open(img_path) as src:
                width, height = src.width, src.height
                res = src.res[0] if src.res else 0.0000898
                bounds = src.bounds
                min_lon, max_lon = bounds.left, bounds.right
                min_lat, max_lat = bounds.bottom, bounds.top
                
            sar = CanonicalSAR(
                scene_id=f"zenodo_p1_{scene_id}",
                source_dataset="zenodo_part1",
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
                bbox=BBox(min_lon=min_lon, max_lon=max_lon, min_lat=min_lat, max_lat=max_lat),
                channels={
                    "VV": ChannelMeta(name="VV", unit="dB", dtype="float32"),
                    "VH": ChannelMeta(name="VH", unit="dB", dtype="float32")
                },
                data_path=str(img_path),
                file_checksum=img_checksum,
                file_size_bytes=img_path.stat().st_size,
                provenance=provenance,
                metadata={"timestamp_status": "unavailable"}
            )
            
            mask = OilMask(
                mask_id=f"mask_{scene_id}",
                scene_id=f"zenodo_p1_{scene_id}",
                label_class=OilLabelClass.OIL,
                mask_path=str(mask_path),
                mask_crs="EPSG:4326",
                mask_bbox=sar.bbox,
                mask_resolution_m=10.0,
                mask_width_px=width,
                mask_height_px=height,
                annotation_source="zenodo",
                annotation_version="1.0",
                class_counts={"0": 0, "1": 0},
                file_checksum=mask_checksum,
                provenance=provenance
            )
            
            sar_list.append(sar)
            mask_list.append(mask)
            
        return sar_list, mask_list
