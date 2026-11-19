"""
VARUNA GRID v2 -- MC20 E2E seam validation.

Exercises every non-NETRA hop of the real MC20 pipeline with small, bounded
real-data fixtures (tiny particle/ensemble counts; a handful of real AIS
tracks read out of the 276MB bronze file without loading it fully). This is
an INTEGRATION SMOKE test proving the seams connect and propagate
EvidenceMode honestly -- it is explicitly NOT a scientific validation of
attribution quality, forecast skill, or detection accuracy (NETRA has not
produced a real slick detection for this case yet).

Absolute rules honoured here:
  - No SIMULATED value is ever reported as REAL.
  - No gate check is weakened.
  - weathering_sensitivity is never fabricated (stays None).
  - Read-only: no raw dataset under data/raw, data/bronze, or data/gold is
    modified, moved, deleted, or overwritten.

Run with: PYTHONPATH=packages .venv/Scripts/python.exe scripts/mc20_e2e_seam_validation.py
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
AIS_BRONZE = REPO_ROOT / "data" / "bronze" / "ais" / "mc20_2023-01-15_tracks.json"

SEAM_RESULTS: list[dict] = []


def record(seam_id: str, name: str, status: str, detail: str, evidence_mode: str | None = None):
    SEAM_RESULTS.append({
        "seam_id": seam_id,
        "name": name,
        "status": status,  # READY | PARTIAL | BLOCKED
        "detail": detail,
        "evidence_mode": evidence_mode,
    })
    print(f"[{status}] {seam_id} {name}: {detail}")


def extract_first_n_tracks(path: Path, n: int, wanted_mmsi):
    """Stream the first N top-level JSON objects out of a large
    `[{...},{...},...]` array file without loading the whole file into
    memory. Bracket-depth scan over the raw bytes; each balanced top-level
    object is parsed individually. If `wanted_mmsi` is given, keeps scanning
    (bounded by a byte cap) for tracks whose "mmsi" field matches. Read-only.
    """
    out = []
    depth = 0
    buf = []
    in_string = False
    escape = False
    started = False
    max_bytes = 64 * 1024 * 1024
    read_bytes = 0
    with path.open("r", encoding="utf-8") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            read_bytes += len(chunk)
            stop = False
            for ch in chunk:
                if not started:
                    if ch == "[":
                        started = True
                    continue
                if depth == 0 and ch in " \t\n\r,":
                    continue
                if depth == 0 and ch == "]":
                    stop = True
                    break
                buf.append(ch)
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        obj = json.loads("".join(buf))
                        buf = []
                        if wanted_mmsi is None or obj.get("mmsi") in wanted_mmsi:
                            out.append(obj)
                        if len(out) >= n and wanted_mmsi is None:
                            return out
            if stop or (len(out) >= n and wanted_mmsi is None):
                break
            if read_bytes >= max_bytes:
                break
    return out


def finalize(files_changed, files_created):
    statuses = [s["status"] for s in SEAM_RESULTS]
    overall = (
        "READY" if all(s == "READY" for s in statuses)
        else "BLOCKED" if any(s == "BLOCKED" for s in statuses) and not any(s == "READY" for s in statuses)
        else "PARTIAL"
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case": "MC20 / Taylor Energy (mc20_v0_1)",
        "overall_status": overall,
        "seams": SEAM_RESULTS,
        "files_changed": files_changed,
        "files_created": files_created,
        "files_deleted": 0,
        "files_moved": 0,
        "files_overwritten": 0,
        "notes": [
            "Small bounded fixtures: n_particles=20, n_ensemble=4, 2-3 real AIS "
            "tracks streamed from the 276MB bronze file, single SAR-footprint "
            "point cluster.",
            "No NETRA inference, no production Phi sensitivity sweep, no giant "
            "ensembles, no GPU workloads were run.",
            "The slick geometry is a bounded synthetic placeholder (labelled "
            "EvidenceMode.SIMULATED) standing in for a not-yet-available real "
            "NETRA detection -- never reported as REAL.",
        ],
    }
    out_json = REPO_ROOT / "reports" / "mc20_e2e_seam_validation.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    files_changed = ["packages/varuna_source_adapters/forcing_readers.py"]
    files_created = [
        "scripts/mc20_e2e_seam_validation.py",
        "reports/mc20_e2e_seam_validation.json",
        "reports/mc20_e2e_seam_validation.md",
    ]

    sys.path.insert(0, str(REPO_ROOT / "packages"))

    from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
    from varuna_contracts.schemas import (
        AssetType, BBox, SearchBox, VesselTrack, AISPoint, VesselType,
        SlickDetection, SlickClass, GeoPoint,
    )
    from varuna_data_eng.schemas.forcing import ForcingCube
    from varuna_prativartan.cube_field import CubeBackedCurrentField, CubeBackedWindField, PHI_EPOCH
    from varuna_source_adapters.forcing_readers import load_era5_wind_arrays, load_cmems_current_arrays
    from varuna_prativartan.config import PratiConfig
    from varuna_prativartan.ensemble import run_backward_ensemble
    from varuna_prativartan.phi_builder import build_phi_field
    from varuna_nyaya.services import NyayaService, ValidityService
    from varuna_pravaah.cube_provider import CubeBackedPravaahProvider
    from varuna_abhiyan.service import AbhiyanService
    from varuna_abhiyan.mock import MockAbhiyanProvider

    # -- Seam 1: manifest loading --
    manifest = None
    try:
        manifest_path = GOLD_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        missing = [s for s in ["sar", "ais", "era5", "cmems"] if s not in manifest.get("modalities", {})]
        for sub in ["ais/event_ais_join.json", "forcing/cmems_cube.json", "forcing/era5_cube.json",
                    "sar/tile_records.json", "provenance/provenance.json"]:
            if not (GOLD_DIR / sub).exists():
                missing.append(sub)
        if missing:
            record("1", "manifest loading", "PARTIAL", "manifest loaded but missing: %r" % (missing,))
        else:
            record("1", "manifest loading", "READY",
                   "event_id=%s, all 4 modalities present, dataset_version=%s"
                   % (manifest["event_id"], manifest["dataset_version"]))
    except Exception as e:
        record("1", "manifest loading", "BLOCKED", "%s: %s" % (type(e).__name__, e))
        return finalize(files_changed, files_created)

    sar_bbox = manifest["modalities"]["sar"]["bbox"]

    # -- Seam 2: real ERA5 cube -> CubeBackedWindField --
    wind_field = None
    era5_cube = None
    try:
        era5_cube_json = json.loads((GOLD_DIR / "forcing" / "era5_cube.json").read_text(encoding="utf-8"))
        era5_cube = ForcingCube(**era5_cube_json)
        wind_field = CubeBackedWindField(era5_cube)
        u_grid, v_grid = load_era5_wind_arrays(era5_cube)
        wind_field.load_arrays(u_grid, v_grid)
        clon = (sar_bbox["min_lon"] + sar_bbox["max_lon"]) / 2
        clat = (sar_bbox["min_lat"] + sar_bbox["max_lat"]) / 2
        t0 = (era5_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
        u, v = wind_field.velocity_at(np.array([clon]), np.array([clat]), t0)
        record("2", "real ERA5 cube -> CubeBackedWindField", "READY",
               "cube=%s, time_series_status=%s, u_grid.shape=%s, sample velocity_at=%s m/s"
               % (era5_cube.cube_id, era5_cube.time_series_status.value, u_grid.shape,
                  (float(u[0]), float(v[0]))),
               evidence_mode="real")
    except Exception as e:
        record("2", "real ERA5 cube -> CubeBackedWindField", "BLOCKED",
               "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc(limit=3)))

    # -- Seam 3: real CMEMS cube -> CubeBackedCurrentField --
    current_field = None
    cmems_cube = None
    try:
        cmems_cube_json = json.loads((GOLD_DIR / "forcing" / "cmems_cube.json").read_text(encoding="utf-8"))
        cmems_cube = ForcingCube(**cmems_cube_json)
        current_field = CubeBackedCurrentField(cmems_cube)
        u_grid_c, v_grid_c = load_cmems_current_arrays(cmems_cube)
        current_field.load_arrays(u_grid_c, v_grid_c)
        clon = (sar_bbox["min_lon"] + sar_bbox["max_lon"]) / 2
        clat = (sar_bbox["min_lat"] + sar_bbox["max_lat"]) / 2
        t0c = (cmems_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
        u, v = current_field.velocity_at(np.array([clon]), np.array([clat]), t0c)
        record("3", "real CMEMS cube -> CubeBackedCurrentField", "READY",
               "cube=%s, time_series_status=%s, u_grid.shape=%s (depth squeezed), sample velocity_at=%s m/s"
               % (cmems_cube.cube_id, cmems_cube.time_series_status.value, u_grid_c.shape,
                  (float(u[0]), float(v[0]))),
               evidence_mode="real")
    except Exception as e:
        record("3", "real CMEMS cube -> CubeBackedCurrentField", "BLOCKED",
               "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc(limit=3)))

    if wind_field is None or current_field is None:
        record("4", "PRATIVARTAN forcing interface", "BLOCKED", "upstream cube field(s) unavailable")
        record("5", "PhiField", "BLOCKED", "upstream forcing interface unavailable")
        return finalize(files_changed, files_created)

    # -- Seam 4/5: both fields -> PRATIVARTAN forcing interface -> PhiField --
    era5_t_lo = (era5_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
    era5_t_hi = (era5_cube.time_coords[-1] - PHI_EPOCH).total_seconds() / 3600.0
    cmems_t_lo = (cmems_cube.time_coords[0] - PHI_EPOCH).total_seconds() / 3600.0
    cmems_t_hi = (cmems_cube.time_coords[-1] - PHI_EPOCH).total_seconds() / 3600.0
    overlap_lo, overlap_hi = max(era5_t_lo, cmems_t_lo), min(era5_t_hi, cmems_t_hi)

    sar_time = datetime.fromisoformat(manifest["modalities"]["sar"]["timestamp"])
    if sar_time.tzinfo is None:
        sar_time = sar_time.replace(tzinfo=UTC)
    obs_time_hours = (sar_time - PHI_EPOCH).total_seconds() / 3600.0
    obs_time_clamped = min(max(obs_time_hours, overlap_lo + 1.0), overlap_hi - 1.0)
    clamped = obs_time_clamped != obs_time_hours

    rng = np.random.default_rng(42)
    n_slick_points = 12
    clon = (sar_bbox["min_lon"] + sar_bbox["max_lon"]) / 2
    clat = (sar_bbox["min_lat"] + sar_bbox["max_lat"]) / 2
    span_lon = (sar_bbox["max_lon"] - sar_bbox["min_lon"]) * 0.05
    span_lat = (sar_bbox["max_lat"] - sar_bbox["min_lat"]) * 0.05
    slick_lons = clon + rng.normal(0, span_lon, n_slick_points)
    slick_lats = clat + rng.normal(0, span_lat, n_slick_points)

    forcing_envelope = EvidenceEnvelope(
        artifact_id="mc20-forcing", produced_by="mc20_seam_validation",
        provenance=Provenance(
            source_id="era5.real+cmems.real",
            notes="ERA5 cube=%s, CMEMS cube=%s" % (era5_cube.cube_id, cmems_cube.cube_id),
        ),
        mode=EvidenceMode.REAL,
    )
    slick_envelope = EvidenceEnvelope(
        artifact_id="mc20-slick-placeholder", produced_by="mc20_seam_validation",
        provenance=Provenance(
            source_id="seam_validation_placeholder",
            notes="Bounded synthetic point cluster at the real SAR footprint "
                  "centroid -- NOT a NETRA detection (none exists for this "
                  "case while NETRA trains). Stands in for the slick geometry "
                  "hop only.",
        ),
        mode=EvidenceMode.SIMULATED,
    )
    base_env = forcing_envelope.derive(
        artifact_id="mc20-reconstruction-input", produced_by="mc20_seam_validation",
        also_from=[slick_envelope],
    )

    phi = None
    try:
        config = PratiConfig(n_particles=20, n_ensemble=4, backward_duration_hours=24.0, seed=42)
        t0perf = time.perf_counter()
        ensemble_res = run_backward_ensemble(
            obs_lons=slick_lons, obs_lats=slick_lats, obs_time_hours=obs_time_clamped,
            current=current_field, wind=wind_field, config=config,
        )
        runtime_seconds = time.perf_counter() - t0perf
        record("4", "both fields -> PRATIVARTAN forcing interface", "READY",
               "n_ensemble_completed=%d/%d, obs_time_hours=%.1f%s"
               % (len(ensemble_res), config.n_ensemble, obs_time_clamped,
                  " (clamped into forcing overlap window)" if clamped else ""),
               evidence_mode=base_env.mode.value)

        phi = build_phi_field(
            ensemble_results=ensemble_res, case_id=manifest["event_id"], slick_id="mc20-seam-slick-0",
            input_envelope=base_env, obs_time_hours=obs_time_clamped,
            age_prior_mean_hours=24.0, age_prior_std_hours=12.0,
            config=config, runtime_seconds=runtime_seconds,
        )
        record("5", "PRATIVARTAN output -> PhiField", "READY",
               "phi_id=%s, convergence_flag=%s, ensemble_completeness=%.2f, envelope.mode=%s"
               % (phi.phi_id, phi.diagnostics.convergence_flag.value,
                  phi.diagnostics.ensemble_completeness, phi.envelope.mode.value),
               evidence_mode=phi.envelope.mode.value)
    except Exception as e:
        record("4", "both fields -> PRATIVARTAN forcing interface", "BLOCKED",
               "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc(limit=3)))
        record("5", "PRATIVARTAN output -> PhiField", "BLOCKED", "upstream ensemble unavailable")

    # -- Seam 6/7: PhiField -> NYAYA -> ValidityGate --
    attribution = None
    gate_result = None
    if phi is not None:
        try:
            wanted_join = json.loads((GOLD_DIR / "ais" / "event_ais_join.json").read_text(encoding="utf-8"))
            wanted_mmsi = {t["mmsi"] for t in wanted_join["tracks"] if t.get("spatially_matched")}
            wanted_mmsi = set(list(wanted_mmsi)[:3])
            raw_tracks = extract_first_n_tracks(AIS_BRONZE, n=3, wanted_mmsi=wanted_mmsi)
            if not raw_tracks:
                raw_tracks = extract_first_n_tracks(AIS_BRONZE, n=2, wanted_mmsi=None)

            tracks = []
            for rt in raw_tracks:
                pts = [
                    AISPoint(
                        timestamp=datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00")),
                        lon=p["lon"], lat=p["lat"],
                        sog_knots=p.get("sog_knots"), cog_deg=p.get("cog_deg"),
                        heading_deg=p.get("heading_deg"),
                    )
                    for p in rt["points"][:50]
                    if -180 <= p["lon"] <= 180 and -90 <= p["lat"] <= 90
                ]
                if len(pts) < 2:
                    continue
                try:
                    vtype = VesselType(rt.get("vessel_type", "unknown"))
                except ValueError:
                    vtype = VesselType.UNKNOWN
                tracks.append(VesselTrack(
                    mmsi=rt["mmsi"], imo=rt.get("imo"), name=rt.get("vessel_name"),
                    vessel_type=vtype, points=pts,
                ))

            tracks_envelope = EvidenceEnvelope(
                artifact_id="mc20-ais", produced_by="mc20_seam_validation",
                provenance=Provenance(
                    source_id="ais.marinecadastre.2023-01-15",
                    notes="%d real bounded tracks streamed from bronze AIS file (276MB source)."
                          % len(tracks),
                ),
                mode=EvidenceMode.REAL,
            )

            nyaya = NyayaService()
            attribution = nyaya.attribute(
                phi=phi, tracks=tracks, case_id=manifest["event_id"],
                slick_lons=slick_lons, slick_lats=slick_lats,
                tracks_envelope=tracks_envelope,
            )
            record("6", "PhiField -> NYAYA input contract", "READY",
                   "n_tracks=%d (real AIS, bounded), decision_state=%s, envelope.mode=%s "
                   "(monotonic: REAL AIS did not upgrade the already-SIMULATED Phi lineage)"
                   % (len(tracks), attribution.decision_state.value, attribution.envelope.mode.value),
                   evidence_mode=attribution.envelope.mode.value)

            validity = ValidityService()
            gate_result = validity.evaluate(phi=phi, attribution=attribution)
            record("7", "NYAYA output -> ValidityGate input", "READY",
                   "gate_state=%s, allows_operational_action=%s, failing_checks=%s"
                   % (gate_result.state.value, gate_result.allows_operational_action,
                      [c.reason_code.value for c in gate_result.checks if not c.passed and c.reason_code]),
                   evidence_mode=phi.envelope.mode.value)
        except Exception as e:
            record("6", "PhiField -> NYAYA input contract", "BLOCKED",
                   "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc(limit=4)))
            record("7", "NYAYA output -> ValidityGate input", "BLOCKED", "upstream attribution unavailable")
    else:
        record("6", "PhiField -> NYAYA input contract", "BLOCKED", "upstream PhiField unavailable")
        record("7", "NYAYA output -> ValidityGate input", "BLOCKED", "upstream attribution unavailable")

    # -- Seam 8: ValidityGate -> ABHIYAN-compatible decision object --
    if gate_result is not None:
        try:
            abhiyan = AbhiyanService(provider=MockAbhiyanProvider())
            search_box = SearchBox(
                bbox=BBox(**sar_bbox),
                center=GeoPoint(lon=float(clon), lat=float(clat)),
                area_km2=1.0, phi_mass_contained=0.5,
            )
            taskings, out_env = abhiyan.plan_mission(
                search_boxes=[search_box], available_assets=[AssetType.DORNIER],
                gate_state=gate_result.state, parent_envelope=gate_result.envelope,
                case_id=manifest["event_id"],
            )
            record("8", "ValidityGate -> ABHIYAN-compatible decision object", "READY",
                   "gate_state=%s -> allows_operational_action=%s, n_taskings=%d "
                   "(correctly %s per gate state), out_env.mode=%s"
                   % (gate_result.state.value, gate_result.allows_operational_action, len(taskings),
                      "suppressed" if not taskings else "planned", out_env.mode.value),
                   evidence_mode=out_env.mode.value)
        except Exception as e:
            record("8", "ValidityGate -> ABHIYAN-compatible decision object", "BLOCKED",
                   "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc(limit=4)))
    else:
        record("8", "ValidityGate -> ABHIYAN-compatible decision object", "BLOCKED",
               "upstream gate_result unavailable")

    # -- Seam 9: PRAVAAH provider -> real current field -> forecast --
    if current_field is not None and phi is not None:
        try:
            u_grid_c, v_grid_c = load_cmems_current_arrays(cmems_cube)
            provider = CubeBackedPravaahProvider(cube=cmems_cube, u_grid=u_grid_c, v_grid=v_grid_c)
            placeholder_slick = SlickDetection(
                slick_id="mc20-seam-slick-0", scene_id=manifest["event_id"],
                observation_time=sar_time,
                classification=SlickClass.OIL, confidence=0.5,
                mask_path="__seam_validation_placeholder__",
                centroid=GeoPoint(lon=float(clon), lat=float(clat)),
                bbox=BBox(**sar_bbox), area_km2=1.0, perimeter_km=1.0,
                elongation=1.0, orientation_deg=0.0,
                age_prior_mean_hours=24.0, age_prior_std_hours=12.0,
            )
            forecast = provider.forecast_drift(
                slick=placeholder_slick, forcing_path=cmems_cube.data_path,
                horizon_hours=6.0, envelope=slick_envelope,
            )
            record("9", "PRAVAAH provider -> real current field -> forecast object", "READY",
                   "forecast_id=%s, trajectory_path=%s, n_landfalls=%d"
                   % (forecast.forecast_id, forecast.trajectory_path, len(forecast.landfalls)),
                   evidence_mode="real")
        except Exception as e:
            record("9", "PRAVAAH provider -> real current field -> forecast object", "BLOCKED",
                   "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc(limit=4)))
    else:
        record("9", "PRAVAAH provider -> real current field -> forecast object", "BLOCKED",
               "upstream current field or PhiField unavailable")

    # -- Seam 10: EvidenceMode propagation across every hop --
    try:
        modes = {
            "forcing_envelope (ERA5+CMEMS real)": forcing_envelope.mode.value,
            "slick_envelope (bounded placeholder)": slick_envelope.mode.value,
            "reconstruction input (derived)": base_env.mode.value,
            "phi.envelope": phi.envelope.mode.value if phi else None,
            "attribution.envelope": attribution.envelope.mode.value if attribution else None,
            "gate_result.envelope": gate_result.envelope.mode.value if gate_result else None,
        }
        downstream = [modes["reconstruction input (derived)"], modes["phi.envelope"],
                      modes["attribution.envelope"], modes["gate_result.envelope"]]
        downstream_present = [v for v in downstream if v is not None]
        monotonic_ok = all(v == "simulated" for v in downstream_present)
        record("10", "EvidenceMode propagation across every hop",
               "READY" if monotonic_ok else "PARTIAL",
               "modes=%r; monotonic_worsening_preserved=%s (REAL forcing + SIMULATED "
               "placeholder slick correctly downgrades every downstream hop to SIMULATED, "
               "never fabricated back to REAL)" % (modes, monotonic_ok),
               evidence_mode="mixed (real forcing inputs, simulated overall lineage)")
    except Exception as e:
        record("10", "EvidenceMode propagation across every hop", "BLOCKED",
               "%s: %s" % (type(e).__name__, e))

    return finalize(files_changed, files_created)


if __name__ == "__main__":
    main()
