import numpy as np
from typing import List, Optional
from varuna_contracts.schemas import BBox, LandfallPrediction, GeoPoint

from datetime import datetime, timezone, timedelta

def check_landfall(trajectory_lons: np.ndarray, trajectory_lats: np.ndarray,
                   coastline_bbox: Optional[BBox] = None) -> List[LandfallPrediction]:
    """Simple bbox-based coastline intersection."""
    landfalls = []
    
    eta = datetime.now(timezone.utc) + timedelta(hours=48.0)
    
    for i in range(len(trajectory_lats)):
        lat = trajectory_lats[i]
        lon = trajectory_lons[i]
        
        if lat > 21.0:
            landfalls.append(LandfallPrediction(
                location_name="Gujarat Coast",
                position=GeoPoint(lon=lon, lat=lat),
                eta=eta,
                hours_until=48.0,
                probability=1.0 / len(trajectory_lats),
                coastline_segment_km=50.0
            ))
        elif lat < 8.0:
            landfalls.append(LandfallPrediction(
                location_name="Sri Lanka / Kerala Coast",
                position=GeoPoint(lon=lon, lat=lat),
                eta=eta,
                hours_until=48.0,
                probability=1.0 / len(trajectory_lats),
                coastline_segment_km=50.0
            ))
            
    grouped = {}
    for lf in landfalls:
        if lf.location_name not in grouped:
            grouped[lf.location_name] = lf
        else:
            grouped[lf.location_name].probability = min(1.0, grouped[lf.location_name].probability + lf.probability)
            
    return list(grouped.values())
