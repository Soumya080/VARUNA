from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Dict, Any
import numpy as np

class NetraSample(BaseModel):
    sample_id: str
    scene_id: str          # parent Sentinel-1 scene
    tile_path: str         # path to 512x512 .npz (VV, VH, wind)
    mask_path: str         # path to 512x512 .png (0=bg, 1=oil, 2=lookalike)
    region: str            # geographic region for split integrity
    acquisition_date: datetime
    wind_speed_ms: float
    metadata: Dict[str, Any]
    
    model_config = ConfigDict(extra="forbid")

class NetraPrediction(BaseModel):
    sample_id: str
    segmentation_mask: Any       # ndarray [H, W] - 0/1/2
    class_probabilities: Any     # ndarray [3, H, W]
    tile_confidence: float
    ood_score: float
    model_version: str
    
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

class NetraEvaluation(BaseModel):
    experiment_id: str
    model_version: str
    dataset_version: str
    split: str             # "val" | "test"
    iou_oil: float
    iou_lookalike: float
    dice_oil: float
    f1_oil: float
    precision_oil: float
    recall_oil: float
    fp_rate_lookalike: float    # KEY METRIC - reported separately
    ood_auroc: float
    calibration_ece: float
    per_region_iou: Dict[str, float]
    per_wind_bin_fp: Dict[str, float]
    confusion_matrix: Any       # ndarray
    
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
