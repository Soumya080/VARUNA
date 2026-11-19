import numpy as np
from typing import Dict, Any
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR
from varuna_data_eng.schemas.oil_mask import OilMask

class LabelAlignment:
    """Aligns canonical SAR and OilMask into unified tensors/geometries."""
    
    def align(self, sar: CanonicalSAR, mask: OilMask) -> Dict[str, Any]:
        """
        Validates projection match and returns unified sample dict.
        In full implementation, this uses rasterio/xarray to resample the mask
        if crs/resolution don't exactly match.
        """
        if sar.crs != mask.mask_crs:
            raise ValueError(f"CRS mismatch: SAR={sar.crs}, Mask={mask.mask_crs}")
        if sar.resolution_m != mask.mask_resolution_m:
            raise ValueError(f"Resolution mismatch: SAR={sar.resolution_m}, Mask={mask.mask_resolution_m}. Explicit resampling required.")
        if sar.width_px != mask.mask_width_px or sar.height_px != mask.mask_height_px:
            raise ValueError(f"Dimension mismatch: SAR={sar.width_px}x{sar.height_px}, Mask={mask.mask_width_px}x{mask.mask_height_px}")
            
        return {
            "sar_id": sar.scene_id,
            "mask_id": mask.mask_id,
            "aligned": True
        }
