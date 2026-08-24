"""
VARUNA GRID — Markdown report generator for the Go/No-Go v2 experiment.
"""
import json
import os

def generate_report(results_dir: str = "results_v2"):
    metrics_path = os.path.join(results_dir, "metrics.json")
    if not os.path.exists(metrics_path):
        print("Metrics file not found.")
        return
        
    with open(metrics_path, "r") as f:
        metrics = json.load(f)
        
    report = f"""# VARUNA GRID Go/No-Go v2 Experiment Report

## Overview
This report summarizes the performance of the VARUNA GRID v2 pipeline (PRATIVARTAN + NYAYA) against a simulated set of slick scenarios with known ground truth and hard negative decoy vessels.

## High-Level Metrics
- **Total Cases**: {metrics.get("total_cases", 0)}
- **Overall Accuracy**: {metrics.get("overall_accuracy", 0.0):.2%}
- **Baseline Accuracy**: {metrics.get("baseline_accuracy", 0.0):.2%}
- **Known-Source Accuracy**: {metrics.get("known_accuracy", 0.0):.2%}
- **Latent-Source Accuracy**: {metrics.get("latent_accuracy", 0.0):.2%}

## Diagnostics
- **Average Entropy**: {metrics.get("avg_entropy", 0.0):.3f}
- **Average Distinguishability**: {metrics.get("avg_distinguishability", 0.0):.3f}

### Decision States
```json
{json.dumps(metrics.get("decisions", {}), indent=2)}
```

### Validity Gate States
```json
{json.dumps(metrics.get("gate_states", {}), indent=2)}
```
"""
    with open(os.path.join(results_dir, "report.md"), "w") as f:
        f.write(report)
        
    print(f"Report generated at {os.path.join(results_dir, 'report.md')}")

if __name__ == "__main__":
    generate_report()
