import numpy as np
from typing import Optional

from varuna_data_eng.schemas.normalization import NormalizationRecord

def normalize_sar_tile(vv: np.ndarray, vh: np.ndarray, norm_record: NormalizationRecord) -> np.ndarray:
    """Normalize SAR backscatter to [0,1] range using global stats.

    Args:
        vv: VV-polarization array (float32, dB)
        vh: VH-polarization array (float32, dB)
        norm_record: Global normalization statistics

    Returns:
        3-channel array (VV_norm, VH_norm, VV/VH_ratio) shape (3, H, W)
    """
    def _norm(arr, stats):
        lo, hi = stats.p2, stats.p98
        return np.clip((arr - lo) / (hi - lo + 1e-8), 0, 1).astype(np.float32)
        
    vv_stats = norm_record.channels.get("VV")
    vh_stats = norm_record.channels.get("VH")
    
    if not vv_stats or not vh_stats:
        raise ValueError("NormalizationRecord missing VV or VH stats")
        
    vv_n = _norm(vv, vv_stats)
    vh_n = _norm(vh, vh_stats)
    ratio = np.clip(vv / (vh + 1e-8), 0, 10) / 10.0
    return np.stack([vv_n, vh_n, ratio.astype(np.float32)], axis=0)

def load_vv_vh_arrays(scene_path: Optional[str]) -> Optional[tuple]:
    """Load (vv, vh) arrays for a preprocessed scene from a sidecar .npz file
    (`<scene_path>.npz` with "vv"/"vh" keys).

    Returns None if no sidecar array file exists — callers should treat this
    as "no raw arrays available", not fabricate zeros in their place.
    """
    if scene_path is None:
        return None
    npz_path = scene_path if scene_path.endswith(".npz") else f"{scene_path}.npz"
    import os
    if not os.path.exists(npz_path):
        return None
    data = np.load(npz_path)
    if "vv" not in data or "vh" not in data:
        return None
    return data["vv"], data["vh"]

def extract_wind_speed(wind_path: Optional[str]) -> Optional[float]:
    """Extract mean wind speed from ERA5 .npz file.

    Returns mean wind speed in m/s, or None if no file.
    """
    if wind_path is None:
        return None
    data = np.load(wind_path)
    u10 = data.get("u10", np.zeros(1))
    v10 = data.get("v10", np.zeros(1))
    speed = np.sqrt(u10**2 + v10**2)
    return float(np.mean(speed))
