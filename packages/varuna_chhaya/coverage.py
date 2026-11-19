import math
from typing import List
from varuna_contracts.schemas import AISPoint, BBox

def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371.0
    lat1_r, lon1_r, lat2_r, lon2_r = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_r - lon1_r
    dlat = lat2_r - lat1_r
    a = math.sin(dlat / 2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def compute_ais_coverage(ais_positions: List[AISPoint], scene_bbox: BBox,
                         grid_resolution_deg: float = 0.1) -> float:
    """Fraction of scene bbox cells that have at least one AIS position nearby.

    Returns:
        Coverage ratio in [0, 1].
    """
    if not ais_positions:
        return 0.0

    width = scene_bbox.max_lon - scene_bbox.min_lon
    height = scene_bbox.max_lat - scene_bbox.min_lat
    if width <= 0 or height <= 0:
        return 1.0

    n_cols = max(1, int(width / grid_resolution_deg))
    n_rows = max(1, int(height / grid_resolution_deg))

    grid = [[False for _ in range(n_cols)] for _ in range(n_rows)]

    # Add a generous margin since AIS points cover large areas (e.g. 50km radius)
    margin_cells = 3

    for p in ais_positions:
        col = int((p.lon - scene_bbox.min_lon) / grid_resolution_deg)
        row = int((p.lat - scene_bbox.min_lat) / grid_resolution_deg)

        for r in range(max(0, row - margin_cells), min(n_rows, row + margin_cells + 1)):
            for c in range(max(0, col - margin_cells), min(n_cols, col + margin_cells + 1)):
                grid[r][c] = True

    occupied = sum(sum(1 for cell in row if cell) for row in grid)
    total = n_cols * n_rows
    
    return min(1.0, float(occupied) / total)
