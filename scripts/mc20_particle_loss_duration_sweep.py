"""
VARUNA GRID v2 -- Track 2 follow-up: is MC20 particle loss a function of
backward_duration_hours, or a fixed property of the real CMEMS coastal
land-mask?

router-datasets-ca does not reproduce the ~40-45% loss at
backward_duration_hours=24.0 (their Track 4 default) against the same real
CMEMS field, and hypothesized the difference is duration (this session's
production sensitivity sweep used ~84h, derived from
age_prior_mean_hours + 2*age_prior_std_hours) rather than seed location.

This sweep holds everything else fixed (same real ERA5/CMEMS cubes, same
seed=42, same 550-point placeholder at the SAR footprint centroid -- NOT
the coastline -- so seed-location is deliberately controlled out) and
varies only backward_duration_hours, at a reduced ensemble size (5 members
instead of 20) to keep this cheap. If loss climbs smoothly with duration,
that supports "loss is a horizon effect, tighten the age prior to buy back
convergence" over "loss is a fixed coastal-forcing property."

Read-only. Does not touch NETRA.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"
sys.path.insert(0, str(REPO_ROOT / "packages"))


def main():
    from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
    from varuna_data_eng.schemas.forcing import ForcingCube
    from varuna_prativartan.cube_field import CubeBackedCurrentField, CubeBackedWindField, PHI_EPOCH
    from varuna_source_adapters.forcing_readers import load_era5_wind_arrays, load_cmems_current_arrays
    from varuna_prativartan.config import PratiConfig
    from varuna_prativartan.ensemble import run_backward_ensemble
    from varuna_prativartan.phi_builder import build_phi_field

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

    # Same seed geometry as the production sweep: 550 points at the SAR
    # footprint CENTROID (not the coastline) -- deliberately controls out
    # seed-location as a variable, per router-datasets-ca's own framing.
    rng = np.random.default_rng(42)
    n_slick_points = 550
    clon = (sar_bbox["min_lon"] + sar_bbox["max_lon"]) / 2
    clat = (sar_bbox["min_lat"] + sar_bbox["max_lat"]) / 2
    span_lon = (sar_bbox["max_lon"] - sar_bbox["min_lon"]) * 0.05
    span_lat = (sar_bbox["max_lat"] - sar_bbox["min_lat"]) * 0.05
    slick_lons = clon + rng.normal(0, span_lon, n_slick_points)
    slick_lats = clat + rng.normal(0, span_lat, n_slick_points)

    base_env = EvidenceEnvelope(
        artifact_id="mc20-duration-sweep", produced_by="mc20_particle_loss_duration_sweep",
        provenance=Provenance(source_id="era5.real+cmems.real", notes="duration sweep, forcing real"),
        mode=EvidenceMode.REAL,
    )

    durations = [12.0, 24.0, 36.0, 48.0, 60.0, 72.0, 84.0]
    # Keep every duration's furthest backward excursion inside the forcing
    # overlap window -- clamp obs_time per duration rather than letting a
    # long-duration run silently walk outside real forcing coverage.
    max_duration = max(durations)
    obs_time_clamped = min(max(obs_time_hours, overlap_lo + max_duration + 1.0), overlap_hi - 1.0)

    results = []
    for dur in durations:
        config = PratiConfig(n_particles=500, n_ensemble=5, backward_duration_hours=dur, seed=42)
        t0 = time.perf_counter()
        ensemble_res = run_backward_ensemble(
            obs_lons=slick_lons, obs_lats=slick_lats, obs_time_hours=obs_time_clamped,
            current=current_field, wind=wind_field, config=config,
        )
        runtime = time.perf_counter() - t0
        phi = build_phi_field(
            ensemble_results=ensemble_res, case_id=manifest["event_id"],
            slick_id=f"duration-sweep-{dur}h", input_envelope=base_env,
            obs_time_hours=obs_time_clamped, age_prior_mean_hours=dur / 2,
            age_prior_std_hours=max(dur / 4, 1.0), config=config, runtime_seconds=runtime,
        )
        loss_frac = phi.diagnostics.particles_lost / phi.diagnostics.particles_seeded
        rec = {
            "backward_duration_hours": dur,
            "n_particles": phi.n_particles,
            "n_ensemble": config.n_ensemble,
            "particles_seeded": phi.diagnostics.particles_seeded,
            "particles_lost": phi.diagnostics.particles_lost,
            "particle_loss_fraction": loss_frac,
            "convergence": phi.diagnostics.convergence,
            "convergence_flag": phi.diagnostics.convergence_flag.value,
            "runtime_seconds": runtime,
        }
        results.append(rec)
        print(f"duration={dur:5.1f}h  loss={loss_frac:.4f}  "
              f"({phi.diagnostics.particles_lost}/{phi.diagnostics.particles_seeded})  "
              f"conv={phi.diagnostics.convergence:.4f} flag={phi.diagnostics.convergence_flag.value}  "
              f"runtime={runtime:.1f}s", flush=True)

    # Monotonicity check
    losses = [r["particle_loss_fraction"] for r in results]
    is_monotonic_nondecreasing = all(losses[i] <= losses[i + 1] + 1e-9 for i in range(len(losses) - 1))

    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "hypothesis": "particle loss climbs with backward_duration_hours (horizon effect), "
                      "not solely a fixed property of the coastal CMEMS land mask",
        "seed_geometry": "550 points, SAR footprint centroid (not coastline) -- location held fixed",
        "obs_time_hours": obs_time_clamped,
        "results": results,
        "loss_fraction_sequence": losses,
        "is_monotonic_nondecreasing": is_monotonic_nondecreasing,
        "conclusion": (
            "MONOTONIC: loss increases with duration -- supports the horizon-effect hypothesis; "
            "a tighter age prior would reduce particle loss."
            if is_monotonic_nondecreasing else
            "NOT STRICTLY MONOTONIC -- duration alone does not cleanly explain the loss pattern; "
            "see per-duration figures."
        ),
    }
    out_path = REPO_ROOT / "reports" / "mc20_particle_loss_duration_sweep.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWritten {out_path}")
    print(f"Monotonic non-decreasing: {is_monotonic_nondecreasing}")
    return out


if __name__ == "__main__":
    main()
