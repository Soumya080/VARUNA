import numpy as np
from typing import List
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR
from varuna_data_eng.schemas.provenance import TileRecord, PixelWindow

class Tiler:
    """Slices huge canonical products into model-ready, provenance-tagged chunks.

    Tiling must run AFTER a scene has been assigned to a split — a tile's
    `split` field is inherited from its parent scene, never computed
    independently, so a scene can never end up with tiles scattered across
    splits it wasn't assigned to.
    """

    def __init__(self, tile_size: int = 512, stride: int = 512):
        self.tile_size = tile_size
        self.stride = stride

    def _tile_bbox(self, sar: CanonicalSAR, x: int, y: int):
        """Approximate geospatial bbox of a tile via linear interpolation over
        the parent scene's bbox and pixel dimensions. Approximate by
        construction (no per-pixel geotransform is modeled here) — adequate
        for provenance tracing, not for geometric precision.
        """
        bbox = sar.bbox
        lon_span = bbox.max_lon - bbox.min_lon
        lat_span = bbox.max_lat - bbox.min_lat
        min_lon = bbox.min_lon + lon_span * (x / sar.width_px)
        max_lon = bbox.min_lon + lon_span * ((x + self.tile_size) / sar.width_px)
        # Raster row 0 is the top (max_lat) of the scene.
        max_lat = bbox.max_lat - lat_span * (y / sar.height_px)
        min_lat = bbox.max_lat - lat_span * ((y + self.tile_size) / sar.height_px)
        from varuna_contracts.schemas import BBox
        return BBox(
            min_lon=min(min_lon, max_lon), max_lon=max(min_lon, max_lon),
            min_lat=min(min_lat, max_lat), max_lat=max(min_lat, max_lat),
        )

    def tile_array(
        self,
        sar: CanonicalSAR,
        arr: np.ndarray,
        split: str,
        source: str,
    ) -> List[TileRecord]:
        """Tiles a 2D array and returns provenance-aware TileRecords.

        Args:
            sar: parent scene metadata (for provenance + bbox interpolation)
            arr: the 2D array to tile (single channel or a pre-selected band)
            split: the split ("train"/"val"/"test") the parent scene was
                assigned by SplitEngine — must be computed BEFORE tiling
            source: dataset/pipeline source identifier for provenance
        """
        h, w = arr.shape
        tiles = []
        for row_idx, y in enumerate(range(0, h - self.tile_size + 1, self.stride)):
            for col_idx, x in enumerate(range(0, w - self.tile_size + 1, self.stride)):
                tile_data = arr[y:y + self.tile_size, x:x + self.tile_size]
                bbox = None
                try:
                    bbox = self._tile_bbox(sar, x, y)
                except (ZeroDivisionError, ValueError):
                    bbox = None
                tiles.append(TileRecord(
                    tile_id=f"{sar.scene_id}_{split}_{x}_{y}",
                    parent_scene_id=sar.scene_id,
                    split=split,
                    sensor=sar.sensor.value if hasattr(sar.sensor, "value") else sar.sensor,
                    source=source,
                    row=row_idx,
                    column=col_idx,
                    pixel_window=PixelWindow(x_offset=x, y_offset=y, width=self.tile_size, height=self.tile_size),
                    bbox=bbox,
                    provenance=sar.provenance,
                    data=tile_data.tobytes(),
                ))
        return tiles

    def extract_bboxes(self, sar: CanonicalSAR) -> List[str]:
        # Returns mock logical bounds for tracking provenance
        return [f"{sar.scene_id}_tile_0_0"]
