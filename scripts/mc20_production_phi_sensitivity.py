"""
VARUNA GRID v2 -- Track 2 Phase 4: PRODUCTION-SCALE Phi sensitivity sweep.

Runs the real, ratified ADR-0007 sensitivity sweep (run_sensitivity_sweep() +
build_sensitivity_block(), packages/varuna_prativartan/sensitivity.py) at
production scale (n_particles=500, n_ensemble=20) against the REAL MC20
ERA5/CMEMS ForcingCubes -- 7 total ensemble executions (1 baseline + 2 age +
2 forcing + 2 diffusivity), using the existing configured perturbation
ranges (PratiConfig.current_noise_range / diffusivity_range,
age_prior_std_hours) -- no new perturbation parameters invented.

Slick geometry: MC20 has no real NETRA detection yet (separate Training
Track still investigating the domain/preprocessing gap), so per Phase 8's
explicit instruction this uses the SAME bounded, explicitly-labelled
SIMULATED placeholder point cluster as the prior seam-validation pass
(scripts/mc20_e2e_seam_validation.py) -- never substituted for a real
detection, never reported as REAL. Forcing is REAL; the combined envelope
is SIMULATED throughout by the existing monotonic-derive() rule.

Read-only against data/raw, data/bronze, data/gold. Does not touch NETRA.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"
sys.path.insert(0, str(REPO_ROOT / "packages"))


def main():
    from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
    from varuna_data_eng.schemas.forcing import ForcingCube
    from varuna_prativartan.cube_field import (
        CubeBackedCurrentField, CubeBackedWindField, PHI_EPOCH,
    )
    from varuna_source_adapters.forcing_readers import (
        load_era5_wind_arrays, load_cmems_current_arrays,
    )
    from varuna_prativartan.config import PratiConfig
    from varuna_prativartan.sensitivity import run_sensitivity_sweep, build_sensitivity_block

    manifest = json.loads((GOLD_DIR / "manifest.json").read_text(encoding="utf-8"))
    sar_bbox = manifest["modalities"]["sar"]["bbox"]

    era5_cube = ForcingCube(**json.loads((GOLD_DIR / "forcing" / "era5_cube.json").read_text(encoding="utf-8")))
    cmems_cube = ForcingCube(**json.loads((GOLD_DIR / "forcing" / "cmems_cube.json").read_text(encoding="utf-8")))

    wind_field = CubeBackedWindField(era5_cube)
    u_w, v_w = load_era5_wind_arrays(era5_cube)
    wind_field.load_arrays(u_w, v_w)

    current_field = CubeBackedCurrentField(cmems_cube)
    u_c, v_c = load_cmems_current_arrays(cmems_cube)
    current_field.load_arrays(u_c, v_c)

    era5_t_lo = (era5_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
    era5_t_hi = (era5_cube.time_coords[-1] - PHI_EPOCH).total_seconds() / 3600.0
    cmems_t_lo = (cmems_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
    cmems_t_hi = (cmems_cube.time_coords[-1] - PHI_EPOCH).total_seconds() / 3600.0
    overlap_lo, overlap_hi = max(era5_t_lo, cmems_t_lo), min(era5_t_hi, cmems_t_hi)

    sar_time = datetime.fromisoformat(manifest["modalities"]["sar"]["timestamp"])
    if sar_time.tzinfo is None:
        sar_time = sar_time.replace(tzinfo=UTC)
    obs_time_hours = (sar_time - PHI_EPOCH).total_seconds() / 3600.0
    age_prior_std_hours = 12.0
    # Keep the full backward window + both age perturbation extremes inside
    # the forcing overlap -- same clamp rationale as the seam-validation
    # pass, just re-derived here since the sweep needs headroom on both
    # sides of obs_time for the age +/- runs, not just the baseline.
    margin = age_prior_std_hours + 2.0
    obs_time_clamped = min(max(obs_time_hours, overlap_lo + margin), overlap_hi - margin)
    clamped = obs_time_clamped != obs_time_hours

    rng = np.random.default_rng(42)
    # n_particles=500 in PratiConfig only takes effect if the observation
    # mask actually has >=500 points -- run_backward_ensemble() does
    # min(config.n_particles, n_obs), so a smaller placeholder silently caps
    # the particle count regardless of what config says. Match the point
    # count to the configured particle budget so "500 particles" is real,
    # not accidentally truncated by an undersized synthetic mask.
    n_slick_points = 550
    clon = (sar_bbox["min_lon"] + sar_bbox["max_lon"]) / 2
    clat = (sar_bbox["min_lat"] + sar_bbox["max_lat"]) / 2
    span_lon = (sar_bbox["max_lon"] - sar_bbox["min_lon"]) * 0.05
    span_lat = (sar_bbox["max_lat"] - sar_bbox["min_lat"]) * 0.05
    slick_lons = clon + rng.normal(0, span_lon, n_slick_points)
    slick_lats = clat + rng.normal(0, span_lat, n_slick_points)

    forcing_envelope = EvidenceEnvelope(
        artifact_id="mc20-forcing-production", produced_by="mc20_production_phi_sensitivity",
        provenance=Provenance(
            source_id="era5.real+cmems.real",
            notes=f"ERA5 cube={era5_cube.cube_id}, CMEMS cube={cmems_cube.cube_id}",
        ),
        mode=EvidenceMode.REAL,
    )
    slick_envelope = EvidenceEnvelope(
        artifact_id="mc20-slick-placeholder-production", produced_by="mc20_production_phi_sensitivity",
        provenance=Provenance(
            source_id="track2_validation_placeholder",
            notes="Bounded synthetic point cluster at the real SAR footprint centroid -- "
                  "NOT a NETRA detection (Training Track has not produced one for this case). "
                  "Used only to exercise Track-2 infrastructure at production ensemble scale; "
                  "never reported as REAL.",
        ),
        mode=EvidenceMode.SIMULATED,
    )
    base_env = forcing_envelope.derive(
        artifact_id="mc20-reconstruction-input-production", produced_by="mc20_production_phi_sensitivity",
        also_from=[slick_envelope],
    )

    config = PratiConfig(n_particles=500, n_ensemble=20, backward_duration_hours=24.0, seed=42)

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case": "MC20 / Taylor Energy (mc20_v0_1)",
        "scale": {"n_particles": config.n_particles, "n_ensemble": config.n_ensemble, "seed": config.seed},
        "obs_time_hours": obs_time_clamped,
        "obs_time_clamped_from_real_sar_timestamp": clamped,
        "forcing": {
            "era5_cube_id": era5_cube.cube_id, "cmems_cube_id": cmems_cube.cube_id,
            "era5_time_series_status": era5_cube.time_series_status.value,
            "cmems_time_series_status": cmems_cube.time_series_status.value,
        },
        "envelope_modes": {
            "forcing": forcing_envelope.mode.value,
            "slick_placeholder": slick_envelope.mode.value,
            "combined_input": base_env.mode.value,
        },
    }

    print(f"Starting production sweep: n_particles={config.n_particles}, "
          f"n_ensemble={config.n_ensemble}, 7 runs, obs_time_hours={obs_time_clamped:.1f}",
          flush=True)
    t0 = time.perf_counter()
    try:
        sweep = run_sensitivity_sweep(
            slick_lons=slick_lons, slick_lats=slick_lats, obs_time_hours=obs_time_clamped,
            case_id=manifest["event_id"], slick_id="mc20-production-sensitivity-0",
            age_prior_mean_hours=24.0, age_prior_std_hours=age_prior_std_hours,
            config=config, current=current_field, wind=wind_field, input_envelope=base_env,
        )
        total_runtime = time.perf_counter() - t0
        print(f"Sweep complete in {total_runtime:.1f}s", flush=True)

        block = build_sensitivity_block(sweep)

        def run_record(label, run):
            phi = run.phi
            return {
                "label": label,
                "phi_id": phi.phi_id,
                "particle_count": phi.n_particles,
                "ensemble_count": phi.n_ensemble,
                "ensemble_members_completed": phi.diagnostics.ensemble_members_completed,
                "ensemble_members_requested": phi.diagnostics.ensemble_members_requested,
                "runtime_seconds": phi.diagnostics.runtime_seconds,
                "particles_lost": phi.diagnostics.particles_lost,
                "particles_seeded": phi.diagnostics.particles_seeded,
                "convergence": phi.diagnostics.convergence,
                "convergence_flag": phi.diagnostics.convergence_flag.value,
                "n_modes": phi.diagnostics.n_modes,
                "centroid_lon": run.centroid_lon,
                "centroid_lat": run.centroid_lat,
                "effective_support_km2": phi.diagnostics.effective_support_km2,
            }

        result["runs"] = {
            "baseline": run_record("baseline", sweep.baseline),
            "age_minus": run_record("age_minus", sweep.age_minus),
            "age_plus": run_record("age_plus", sweep.age_plus),
            "forcing_minus": run_record("forcing_minus", sweep.forcing_minus),
            "forcing_plus": run_record("forcing_plus", sweep.forcing_plus),
            "diffusivity_minus": run_record("diffusivity_minus", sweep.diffusivity_minus),
            "diffusivity_plus": run_record("diffusivity_plus", sweep.diffusivity_plus),
        }
        result["centroid_shifts_km"] = {
            "age": sweep.age_centroid_shift_km,
            "forcing": sweep.forcing_centroid_shift_km,
            "diffusivity": sweep.diffusivity_centroid_shift_km,
        }
        from varuna_prativartan.sensitivity import effective_radius_km
        radius_km = effective_radius_km(sweep.baseline.phi)
        result["effective_radius_km"] = radius_km
        result["sensitivity_block"] = {
            "age_sensitivity": block.age_sensitivity,
            "forcing_sensitivity": block.forcing_sensitivity,
            "diffusivity_sensitivity": block.diffusivity_sensitivity,
            "weathering_sensitivity": block.weathering_sensitivity,
            "dominant_assumption": block.dominant_assumption,
        }
        result["total_runtime_seconds"] = total_runtime
        result["status"] = "SUCCESS"

        # Attach the real sensitivity block to the baseline PhiField, exactly
        # as PrativartanService.reconstruct_origin_with_sensitivity() does,
        # so Phase 5/8 can feed this same object into NYAYA/ValidityGate.
        phi_with_sensitivity = sweep.baseline.phi
        phi_with_sensitivity.sensitivity = block
        np.savez(
            REPO_ROOT / "reports" / "mc20_production_phi_baseline.npz",
            **dict(np.load(phi_with_sensitivity.data_path)),
        )
        result["baseline_phi_npz_saved_to"] = "reports/mc20_production_phi_baseline.npz"
        # Persist the full PhiField (with sensitivity) as JSON for Phase 5 to reload.
        (REPO_ROOT / "reports" / "mc20_production_phi_field.json").write_text(
            phi_with_sensitivity.model_dump_json(indent=2), encoding="utf-8"
        )
        result["baseline_phi_field_json_saved_to"] = "reports/mc20_production_phi_field.json"

    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()
        result["total_runtime_seconds"] = time.perf_counter() - t0
        print(f"SWEEP FAILED: {result['error']}", flush=True)

    out_path = REPO_ROOT / "reports" / "mc20_production_phi_sensitivity.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Written {out_path}", flush=True)
    return result


if __name__ == "__main__":
    main()
