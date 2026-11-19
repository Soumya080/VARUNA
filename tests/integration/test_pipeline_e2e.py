import pytest
from varuna_data_eng.pipeline.full_pipeline import FullPipeline
from varuna_data_eng.fixtures.synthetic_case_generator import SyntheticCaseGenerator

def test_full_pipeline_e2e():
    generator = SyntheticCaseGenerator()
    case = generator.generate_case("CASE-E2E")
    
    sar = case.input.slick_observation
    mask = case.input.slick_mask
    
    # synthetic_mode=True: the fixture's file paths (e.g. "/synth/sar.tif")
    # are synthetic placeholders, not real files on disk. Production mode's
    # real file-existence/checksum checks (DataGuard) would correctly
    # QUARANTINE them, so this test exercises the pipeline the same way the
    # fixture generator itself is meant to be used.
    pipeline = FullPipeline(synthetic_mode=True)

    # Process dataset
    manifest = pipeline.process_raw_dataset(
        dataset_id="E2E-DATASET",
        dataset_version="v1.0",
        sar_list=[sar],
        mask_list=[mask]
    )
    
    assert manifest.dataset_id == "E2E-DATASET"
    assert len(manifest.samples) == 1
    assert manifest.quality_report.total_samples == 1
    assert manifest.quality_report.passed == 1
