"""
VARUNA GRID — Go/No-Go v2 Parameter Sweep.
"""
import json
import os
from tqdm import tqdm
from experiments.go_nogo_v2.config import GoNoGoConfig
from experiments.go_nogo_v2.truth import generate_case
from experiments.go_nogo_v2.harness import run_case
from experiments.go_nogo_v2.baselines import naive_distance_baseline
from experiments.go_nogo_v2.metrics import compute_metrics
from varuna_prativartan.config import PratiConfig

def run_sweep(output_dir: str = "results_v2"):
    os.makedirs(output_dir, exist_ok=True)
    config = GoNoGoConfig()
    
    results = []
    baseline_results = []
    
    print(f"Running sweep with {config.n_cases} cases...")
    
    for i in tqdm(range(config.n_cases), desc="Running Sweep"):
        seed = 42 + i
        is_latent = i < int(config.n_cases * config.latent_source_fraction)
        true_age_hours = 12.0 + (seed % 60) # simple deterministic age
        
        # 1. Generate Truth
        slick_lons, slick_lats, truth_track, decoy_tracks = generate_case(
            seed=seed,
            obs_time_hours=config.obs_time_hours,
            true_age_hours=true_age_hours,
            is_latent=is_latent
        )
        
        tracks = decoy_tracks.copy()
        if not is_latent:
            tracks.append(truth_track)
            
        true_mmsi = "LATENT_SOURCE" if is_latent else truth_track.mmsi
        
        # 2. Run Baseline
        baseline_pred = naive_distance_baseline(
            tracks=tracks,
            slick_lons=slick_lons,
            slick_lats=slick_lats,
            obs_time_hours=config.obs_time_hours
        )
        baseline_results.append({
            "case_id": i,
            "true_mmsi": true_mmsi,
            "pred_mmsi": baseline_pred,
            "is_correct": baseline_pred == true_mmsi
        })
        
        # 3. Run Pipeline
        prati_config = PratiConfig(
            n_particles=config.n_particles,
            n_ensemble=config.n_ensemble,
            backward_duration_hours=true_age_hours, # Set mean to true age
            seed=seed * 100
        )
        
        res = run_case(
            slick_lons=slick_lons,
            slick_lats=slick_lats,
            obs_time_hours=config.obs_time_hours,
            tracks=tracks,
            true_mmsi=true_mmsi,
            config=prati_config
        )
        res["true_age_hours"] = true_age_hours
        results.append(res)
        
    # 4. Compute Metrics
    metrics = compute_metrics(results, baseline_results)
    
    with open(os.path.join(output_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
        
    with open(os.path.join(output_dir, "results.json"), "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"\nSweep complete. Accuracy: {metrics['overall_accuracy']:.2%} (Baseline: {metrics.get('baseline_accuracy', 0):.2%})")
    return metrics

if __name__ == "__main__":
    run_sweep()
