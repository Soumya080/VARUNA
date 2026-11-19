from typing import List, Any
from datetime import datetime
import hashlib

from .manifest import DatasetManifest, DataQualityReport, SampleRef
from .splitter import DatasetSplitter

class DatasetPipeline:
    """
    Validation Pipeline stub for M5.
    raw -> schema -> guard -> normalise -> preprocess -> deduplicate -> quality -> split -> manifest
    """
    
    @classmethod
    def process(cls, raw_samples: List[Any], dataset_name: str, version: str) -> DatasetManifest:
        validated = cls._schema_validate(raw_samples)
        guarded = cls._data_guard_check(validated)
        normalised = cls._normalise(guarded)
        preprocessed = cls._preprocess(normalised)
        deduplicated = cls._deduplicate(preprocessed)
        quality_checked, report = cls._quality_check(deduplicated)
        
        # Simple geographic split stub
        region_map = {s.sample_id: getattr(s, "region", "unknown") for s in quality_checked}
        test_regions = ["test_region"]
        val_regions = ["val_region"]
        
        split = DatasetSplitter.geographic_split(quality_checked, region_map, test_regions, val_regions)
        
        manifest = cls._build_manifest(dataset_name, version, quality_checked, split, report)
        return manifest
        
    @classmethod
    def _schema_validate(cls, samples: List[Any]) -> List[Any]:
        return samples
        
    @classmethod
    def _data_guard_check(cls, samples: List[Any]) -> List[Any]:
        return samples
        
    @classmethod
    def _normalise(cls, samples: List[Any]) -> List[Any]:
        return samples
        
    @classmethod
    def _preprocess(cls, samples: List[Any]) -> List[Any]:
        return samples
        
    @classmethod
    def _deduplicate(cls, samples: List[Any]) -> List[Any]:
        seen = set()
        unique = []
        for s in samples:
            if s.sample_id not in seen:
                seen.add(s.sample_id)
                unique.append(s)
        return unique
        
    @classmethod
    def _quality_check(cls, samples: List[Any]) -> tuple[List[Any], DataQualityReport]:
        valid_samples = len(samples)
        report = DataQualityReport(
            total_samples=valid_samples,
            valid_samples=valid_samples,
            rejected_samples=0,
            class_distribution={},
            region_distribution={},
            temporal_range=(datetime.min, datetime.max),
            duplicate_count=0,
            anomaly_count=0
        )
        return samples, report
        
    @classmethod
    def _build_manifest(cls, name: str, version: str, samples: List[Any], split: Any, report: DataQualityReport) -> DatasetManifest:
        sample_refs = [
            SampleRef(sample_id=s.sample_id, content_hash=hashlib.sha256(s.sample_id.encode()).hexdigest()) 
            for s in samples
        ]
        
        # content hash is hash of all sample hashes
        combined = "".join(sr.content_hash for sr in sample_refs)
        content_hash = hashlib.sha256(combined.encode()).hexdigest()
        
        return DatasetManifest(
            manifest_id=f"manifest-{version}",
            dataset_name=name,
            version=version,
            created_at=datetime.utcnow(),
            git_commit="unknown",
            content_hash=content_hash,
            samples=sample_refs,
            splits=split,
            quality_report=report
        )
