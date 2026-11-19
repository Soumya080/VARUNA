import pytest
from varuna_data_eng.fixtures.synthetic_case_generator import SyntheticCaseGenerator
from varuna_data_eng.schemas.attribution_case import AttributionCase

def test_synthetic_case_generator():
    generator = SyntheticCaseGenerator()
    case = generator.generate_case("CASE-TEST")
    
    assert isinstance(case, AttributionCase)
    assert case.case_id == "CASE-TEST"
    assert case.input.slick_observation.scene_id == "synth_s1"
    assert len(case.input.ais_tracks) == 1
    assert case.input.ais_tracks[0].mmsi == "123456789"
    assert case.truth.true_source_mmsi == "123456789"
