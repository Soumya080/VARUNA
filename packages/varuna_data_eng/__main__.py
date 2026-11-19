import sys
from varuna_data_eng.fixtures.synthetic_case_generator import SyntheticCaseGenerator
from varuna_data_eng.pipeline.full_pipeline import FullPipeline

def main():
    print("VARUNA GRID v2 — Data Engineering CLI (M6)")
    generator = SyntheticCaseGenerator()
    case = generator.generate_case("CLI-TEST-001")
    print(f"Generated synthetic case: {case.case_id} at {case.input.observation_time}")
    
    pipeline = FullPipeline()
    print("Data Engineering Pipeline ready.")
    
if __name__ == "__main__":
    main()
