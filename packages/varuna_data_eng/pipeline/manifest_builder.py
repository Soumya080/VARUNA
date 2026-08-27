from typing import List, Dict, Optional
from datetime import datetime, timezone
import hashlib
import json
from varuna_data_eng.schemas.manifest import DatasetManifest, ManifestEntry, SplitManifest, DataQualityReport
from varuna_data_eng.schemas.normalization import NormalizationRecord
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_data_eng.schemas.quality import QualityVerdict

class ManifestBuilder:
    """Aggregates all entries and records into a finalized DatasetManifest."""
    
    def build(
        self,
        dataset_id: str,
        dataset_version: str,
        entries: List[ManifestEntry],
        splits: SplitManifest,
        provenance: DataProvenance,
        normalization_stats: Optional[NormalizationRecord] = None
    ) -> DatasetManifest:
        
        # Calculate quality report
        total = len(entries)
        passed = sum(1 for e in entries if e.quality_state.overall_verdict == QualityVerdict.PASS)
        warned = sum(1 for e in entries if e.quality_state.overall_verdict == QualityVerdict.WARN)
        rejected = sum(1 for e in entries if e.quality_state.overall_verdict == QualityVerdict.REJECT)
        
        report = DataQualityReport(
            total_samples=total,
            passed=passed,
            warned=warned,
            rejected=rejected,
            rejection_reasons={}
        )
        
        content_hash = hashlib.sha256(json.dumps([e.content_hash for e in entries]).encode()).hexdigest()
        
        return DatasetManifest(
            manifest_id=f"manifest_{dataset_id}_{dataset_version}",
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            created_at=datetime.now(timezone.utc),
            git_commit="unknown", # normally injected
            config_version="1.0",
            content_hash=content_hash,
            samples=entries,
            splits=splits,
            normalization_stats=normalization_stats,
            quality_report=report,
            pipeline_version="2.0.0",
            source_datasets=["zenodo.8346860"],
            sensor_distribution={"SENTINEL_1": total},
            license_summary=["CC-BY-4.0"],
            provenance=provenance
        )
