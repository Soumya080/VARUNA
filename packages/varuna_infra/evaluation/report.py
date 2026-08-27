from typing import Dict, Any

def generate_report(metrics: Dict[str, Any], output_path: str) -> None:
    # Stub for generating evaluation reports
    with open(output_path, "w") as f:
        f.write(str(metrics))
