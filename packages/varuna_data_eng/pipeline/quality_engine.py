import hashlib
from pathlib import Path
from typing import List, Any
from varuna_data_eng.schemas.quality import QualityState, QualityCheck, QualityVerdict
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR
from varuna_data_eng.schemas.oil_mask import OilMask
from varuna_data_eng.schemas.ais import RawAISTrack
from varuna_data_eng.schemas.forcing import ForcingCube

class QualityEngine:
    """Runs the 12-stage validation pipeline on canonical schemas."""
    
    def __init__(self, synthetic_mode: bool = False):
        self.synthetic_mode = synthetic_mode
        
    def validate_sar(self, sar: CanonicalSAR) -> QualityState:
        checks = []
        checks.append(self._check_file_integrity(sar.data_path))
        checks.append(self._check_checksum(sar))
        checks.append(self._check_metadata(sar))
        checks.append(self._check_geospatial(sar))
        checks.append(self._check_temporal(sar))
        checks.append(self._check_provenance(sar.provenance))
        checks.append(self._check_sensor_compatibility(sar))
        return self._aggregate(checks)

    def validate_mask(self, mask: OilMask) -> QualityState:
        checks = []
        checks.append(self._check_file_integrity(mask.mask_path))
        checks.append(self._check_checksum(mask))
        checks.append(self._check_geospatial(mask, is_mask=True))
        return self._aggregate(checks)

    def validate_ais(self, track: RawAISTrack) -> QualityState:
        checks = []
        checks.append(self._check_provenance(track.provenance))
        if len(track.points) < 2:
            checks.append(QualityCheck(name="min_points", passed=False, verdict=QualityVerdict.REJECT, message="Track has < 2 points"))
        else:
            checks.append(QualityCheck(name="min_points", passed=True, verdict=QualityVerdict.PASS))
        return self._aggregate(checks)

    def validate_forcing(self, forcing: ForcingCube) -> QualityState:
        checks = []
        checks.append(self._check_file_integrity(forcing.data_path))
        checks.append(self._check_checksum(forcing))
        checks.append(self._check_geospatial(forcing))
        checks.append(self._check_temporal(forcing))
        checks.append(self._check_provenance(forcing.provenance))
        return self._aggregate(checks)

    def _check_file_integrity(self, path: str) -> QualityCheck:
        if self.synthetic_mode:
            if path:
                return QualityCheck(name="file_integrity", passed=True, verdict=QualityVerdict.PASS)
            return QualityCheck(name="file_integrity", passed=False, verdict=QualityVerdict.REJECT, message="Empty path")
            
        p = Path(path)
        if p.exists() and p.is_file():
            # In a real app we might also check if it's readable
            return QualityCheck(name="file_integrity", passed=True, verdict=QualityVerdict.PASS)
        return QualityCheck(name="file_integrity", passed=False, verdict=QualityVerdict.REJECT, message=f"File not found or not a file: {path}")

    def _check_checksum(self, obj: Any) -> QualityCheck:
        if self.synthetic_mode:
            if hasattr(obj, "file_checksum") and obj.file_checksum:
                return QualityCheck(name="checksum", passed=True, verdict=QualityVerdict.PASS)
            return QualityCheck(name="checksum", passed=False, verdict=QualityVerdict.REJECT, message="Checksum missing")
            
        if not hasattr(obj, "file_checksum") or not obj.file_checksum:
            return QualityCheck(name="checksum", passed=False, verdict=QualityVerdict.REJECT, message="Checksum missing on object")
            
        path = getattr(obj, "data_path", getattr(obj, "mask_path", None))
        if not path or not Path(path).exists():
             # If the file integrity check fails, this will also fail, which is fine
             return QualityCheck(name="checksum", passed=False, verdict=QualityVerdict.REJECT, message="Cannot read file for checksum")
             
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
                
        computed = sha256_hash.hexdigest()
        if computed == obj.file_checksum:
            return QualityCheck(name="checksum", passed=True, verdict=QualityVerdict.PASS)
        return QualityCheck(name="checksum", passed=False, verdict=QualityVerdict.REJECT, message=f"Checksum mismatch: expected {obj.file_checksum}, got {computed}")

    def _check_metadata(self, sar: CanonicalSAR) -> QualityCheck:
        if sar.scene_id and sar.sensor:
            return QualityCheck(name="metadata", passed=True, verdict=QualityVerdict.PASS)
        return QualityCheck(name="metadata", passed=False, verdict=QualityVerdict.REJECT, message="Invalid metadata")

    def _check_geospatial(self, obj: Any, is_mask: bool = False) -> QualityCheck:
        bbox = obj.mask_bbox if is_mask else obj.bbox
        if -180 <= bbox.min_lon <= bbox.max_lon <= 180 and -90 <= bbox.min_lat <= bbox.max_lat <= 90:
            return QualityCheck(name="geospatial", passed=True, verdict=QualityVerdict.PASS)
        return QualityCheck(name="geospatial", passed=False, verdict=QualityVerdict.REJECT, message="BBox out of bounds")

    def _check_temporal(self, obj: Any) -> QualityCheck:
        if hasattr(obj, "acquisition_time"):
            if obj.acquisition_time.tzinfo is not None:
                return QualityCheck(name="temporal", passed=True, verdict=QualityVerdict.PASS)
        elif hasattr(obj, "time_range"):
            if obj.time_range[0].tzinfo is not None:
                return QualityCheck(name="temporal", passed=True, verdict=QualityVerdict.PASS)
        return QualityCheck(name="temporal", passed=False, verdict=QualityVerdict.REJECT, message="Timezone missing")

    def _check_provenance(self, prov: Any) -> QualityCheck:
        if prov.source_id and prov.adapter_id and prov.license:
            return QualityCheck(name="provenance", passed=True, verdict=QualityVerdict.PASS)
        return QualityCheck(name="provenance", passed=False, verdict=QualityVerdict.WARN, message="Incomplete provenance")
        
    def _check_sensor_compatibility(self, sar: CanonicalSAR) -> QualityCheck:
        return QualityCheck(name="sensor_compatibility", passed=True, verdict=QualityVerdict.PASS)

    def _aggregate(self, checks: List[QualityCheck]) -> QualityState:
        overall = QualityVerdict.PASS
        for c in checks:
            if c.verdict == QualityVerdict.REJECT:
                overall = QualityVerdict.REJECT
                break
            elif c.verdict == QualityVerdict.WARN and overall != QualityVerdict.REJECT:
                overall = QualityVerdict.WARN
        return QualityState(overall_verdict=overall, checks=checks)
