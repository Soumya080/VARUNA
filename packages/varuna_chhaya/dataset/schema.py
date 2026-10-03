from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Dict, Any

class ChhayaSample(BaseModel):
    sample_id: str
    trajectory_id: str
    trajectory_path: str   # path to saved ndarray [T, 4]
    start_time: datetime
    end_time: datetime
    metadata: Dict[str, Any]
    
    model_config = ConfigDict(extra="forbid")

class ChhayaPrediction(BaseModel):
    sample_id: str
    predicted_trajectory: Any     # ndarray [T, 2] (lon, lat)
    confidence_radius_km: Any     # ndarray [T]
    model_version: str
    
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

class ChhayaEvaluation(BaseModel):
    experiment_id: str
    model_version: str
    dataset_version: str
    split: str
    mean_distance_km: float
    max_distance_km: float
    rmse_lon: float
    rmse_lat: float
    
    model_config = ConfigDict(extra="forbid")
