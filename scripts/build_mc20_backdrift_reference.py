"""
VARUNA GRID — real MC20 backward-drift reference build (ADR-0017).

Runs the REAL backward ensemble (`run_backward_ensemble` + `build_phi_field`)
against REAL, already-persisted ERA5/CMEMS forcing cubes
(`data/gold/events/mc20_v0_1/forcing/{era5,cmems}_cube.json`, built by
`build_mc20_event_gold.py`) for the real MC20/Taylor Energy anchor point.

This is a CACHED, ONCE-COMPUTED reference for the replay-fixture path
(`packages/varuna_domain/replay_fixtures.py::_phi()`'s CASE-VALID branch) —
not a live per-request computation. Per the replay-fixtures module's own
house rule ("REPLAY data is never labelled REAL"), the resulting PhiField
stays `EvidenceMode.SIMULATED` when reused as a fixture, even though real
forcing was genuinely used to compute it — labelled honestly via
`forcing_current_source`/`forcing_wind_source` rather than via `mode`,
exactly the same pattern M1/M2 established for `historical_reconstruction`
(real information, structurally never claiming the REAL evidence mode of a
live computation).

Output: data/gold/events/mc20_v0_1/prativartan/{phi.npz, phi_field.json}

Usage: python scripts/build_mc20_backdrift_reference.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance  # noqa: E402
from varuna_data_eng.schemas.forcing import ForcingCube  # noqa: E402
from varuna_prativartan.config import PratiConfig  # noqa: E402
from varuna_prativartan.cube_field import CubeBackedCurrentField, CubeBackedWindField, PHI_EPOCH  # noqa: E402
from varuna_prativartan.ensemble import run_backward_ensemble  # noqa: E402
from varuna_prativartan.phi_builder import build_phi_field  # noqa: E402
from varuna_source_adapters.forcing_readers import (  # noqa: E402
    load_cmems_current_arrays, load_era5_wind_arrays,
)

GOLD_DIR = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"
ERA5_CUBE_JSON = GOLD_DIR / "forcing" / "era5_cube.json"
CMEMS_CUBE_JSON = GOLD_DIR / "forcing" / "cmems_cube.json"
OUT_DIR = GOLD_DIR / "prativartan"

# The real, documented MC20/Taylor Energy platform site — same anchor every
# replay fixture in this repo already uses (see replay_fixtures.py::_ANCHOR).
MC20_LAT, MC20_LON = 28.936, -88.970
CASE_ID = "CASE-VALID"


def main() -> None:
    if not ERA5_CUBE_JSON.exists() or not CMEMS_CUBE_JSON.exists():
        raise SystemExit(
            f"Real forcing cubes not found at {ERA5_CUBE_JSON} / {CMEMS_CUBE_JSON} — "
            "run scripts/build_mc20_event_gold.py first."
        )

    era5_cube = ForcingCube(**json.loads(ERA5_CUBE_JSON.read_text()))
    cmems_cube = ForcingCube(**json.loads(CMEMS_CUBE_JSON.read_text()))
    wind_field = CubeBackedWindField(era5_cube)
    u_w, v_w = load_era5_wind_arrays(era5_cube)
    wind_field.load_arrays(u_w, v_w)
    current_field = CubeBackedCurrentField(cmems_cube)
    u_c, v_c = load_cmems_current_arrays(cmems_cube)
    current_field.load_arrays(u_c, v_c)

    # Same real observation instant every MC20 fixture already uses
    # (replay_fixtures.py::_T_OBS = 2023-01-15T00:02:06Z), expressed in
    # Phi's own epoch-relative coordinate — clamped into the overlap of
    # both cubes' real temporal coverage, exactly like
    # mc20_e2e_seam_validation.py does, so the query never falls outside
    # either cube's real domain (CubeBackedField fails closed on that,
    # by design).
    from datetime import UTC, datetime
    sar_time = datetime(2023, 1, 15, 0, 2, 6, tzinfo=UTC)
    obs_time_hours = (sar_time - PHI_EPOCH).total_seconds() / 3600.0

    era5_lo = (era5_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
    era5_hi = (era5_cube.time_coords[-1] - PHI_EPOCH).total_seconds() / 3600.0
    cmems_lo = (cmems_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
    cmems_hi = (cmems_cube.time_coords[-1] - PHI_EPOCH).total_seconds() / 3600.0
    overlap_lo = max(era5_lo, cmems_lo)
    overlap_hi = min(era5_hi, cmems_hi)
    backward_hours = 24.0
    obs_time_clamped = min(max(obs_time_hours, overlap_lo + backward_hours + 1.0), overlap_hi - 1.0)

    # NOTE (ADR-0017): pushed as high as n_particles=20000/n_ensemble=60
    # while diagnosing test expectations — convergence plateaus at MARGINAL
    # regardless, so the higher cost bought nothing. This is genuine
    # ensemble-member disagreement under real, perturbed forcing (wind
    # drift/diffusivity/current-noise perturbation across members), not a
    # sampling-density artifact — an honest result, not tuned away.
    config = PratiConfig(
        n_particles=4000, n_ensemble=40,
        backward_duration_hours=backward_hours, seed=42,
    )

    forcing_envelope = EvidenceEnvelope(
        artifact_id="mc20-backdrift-forcing", produced_by="build_mc20_backdrift_reference",
        provenance=Provenance(
            source_id="era5.real+cmems.real",
            notes=f"ERA5 cube={era5_cube.cube_id}, CMEMS cube={cmems_cube.cube_id} — "
                  "real Copernicus/ERA5 forcing, cached for the replay-fixture path. "
                  "mode stays SIMULATED per replay_fixtures.py's own house rule "
                  "(REPLAY data is never labelled REAL); the forcing_*_source fields "
                  "are where this artifact's real provenance actually lives.",
        ),
        mode=EvidenceMode.SIMULATED,
    )

    t0 = time.perf_counter()
    ensemble_res = run_backward_ensemble(
        obs_lons=np.array([MC20_LON]), obs_lats=np.array([MC20_LAT]), obs_time_hours=obs_time_clamped,
        current=current_field, wind=wind_field, config=config,
    )
    runtime_seconds = time.perf_counter() - t0
    if not ensemble_res:
        raise SystemExit("Every ensemble member failed against the real forcing cubes.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    phi = build_phi_field(
        ensemble_results=ensemble_res, case_id=CASE_ID, slick_id=f"replay-slick-{CASE_ID}",
        input_envelope=forcing_envelope, obs_time_hours=obs_time_clamped,
        age_prior_mean_hours=24.0, age_prior_std_hours=12.0,
        config=config, runtime_seconds=runtime_seconds,
        output_dir=str(OUT_DIR),
        forcing_current_source=f"cmems.real ({cmems_cube.cube_id}, cached replay)",
        forcing_wind_source=f"era5.real ({era5_cube.cube_id}, cached replay)",
    )

    summary_path = OUT_DIR / "phi_field.json"
    summary_path.write_text(phi.model_dump_json(indent=2))

    print(json.dumps({
        "case_id": CASE_ID,
        "ensemble_members_completed": phi.diagnostics.ensemble_members_completed,
        "ensemble_members_requested": phi.diagnostics.ensemble_members_requested,
        "convergence_flag": phi.diagnostics.convergence_flag.value,
        "n_modes": phi.diagnostics.n_modes,
        "multimodal": phi.diagnostics.multimodal,
        "n_backdrift_path_points": len(phi.backdrift_path or []),
        "data_path": phi.data_path,
        "summary_path": str(summary_path),
        "runtime_seconds": round(runtime_seconds, 3),
    }, indent=2))


if __name__ == "__main__":
    main()
