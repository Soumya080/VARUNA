"""
VARUNA GRID — Go/No-Go v2 Metrics Calculation.
"""
from typing import List, Dict

def compute_metrics(results: List[dict], baseline_results: List[dict] = None) -> dict:
    total = len(results)
    if total == 0:
        return {}
        
    correct = sum(1 for r in results if r["is_correct"])
    accuracy = correct / total
    
    latent_cases = [r for r in results if r["true_mmsi"] == "LATENT_SOURCE"]
    known_cases = [r for r in results if r["true_mmsi"] != "LATENT_SOURCE"]
    
    latent_acc = sum(1 for r in latent_cases if r["is_correct"]) / len(latent_cases) if latent_cases else 0.0
    known_acc = sum(1 for r in known_cases if r["is_correct"]) / len(known_cases) if known_cases else 0.0
    
    # Decisions distribution
    decisions = {}
    for r in results:
        decisions[r["decision"]] = decisions.get(r["decision"], 0) + 1
        
    # Gates distribution
    gates = {}
    for r in results:
        gates[r["gate_state"]] = gates.get(r["gate_state"], 0) + 1
        
    avg_entropy = sum(r["entropy"] for r in results) / total
    avg_distinguishability = sum(r["distinguishability"] for r in results) / total
    
    metrics = {
        "total_cases": total,
        "overall_accuracy": accuracy,
        "latent_accuracy": latent_acc,
        "known_accuracy": known_acc,
        "decisions": decisions,
        "gate_states": gates,
        "avg_entropy": avg_entropy,
        "avg_distinguishability": avg_distinguishability
    }
    
    if baseline_results:
        baseline_acc = sum(1 for b in baseline_results if b["is_correct"]) / len(baseline_results)
        metrics["baseline_accuracy"] = baseline_acc
        
    return metrics
