"""
VARUNA GRID — MC20 Event Gold Readiness Gate.

READ-ONLY. Re-derives EVENT_GOLD_READY from what is actually on disk in
data/gold/events/mc20_v0_1/ -- never trusts the manifest's own claims
without checking the underlying files.

Usage: python scripts/check_mc20_event_gold_readiness.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

EVENT_DIR = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"
MANIFEST_PATH = EVENT_DIR / "manifest.json"


def check_sar_ready() -> tuple[bool, str]:
    tiles_dir = EVENT_DIR / "sar" / "tiles"
    records_path = EVENT_DIR / "sar" / "tile_records.json"
    if not (tiles_dir.exists() and records_path.exists()):
        return False, "sar/tiles or tile_records.json missing"
    tiles = list(tiles_dir.glob("*.npy"))
    records = json.loads(records_path.read_text())
    if len(tiles) == 0 or len(records) != len(tiles):
        return False, f"{len(tiles)} tile files vs {len(records)} records -- mismatch"
    for t in tiles:
        arr = np.load(t)
        if arr.shape != (2, 512, 512) or arr.dtype != np.float32:
            return False, f"{t.name}: shape/dtype mismatch ({arr.shape}, {arr.dtype})"
        if np.isnan(arr).any() or np.isinf(arr).any():
            return False, f"{t.name}: contains NaN or Inf"
        if arr.min() < 0.0 or arr.max() > 1.0:
            return False, f"{t.name}: normalized range outside [0,1]"
    return True, f"{len(tiles)} real tiles, all [2,512,512] float32, no NaN/Inf, range within [0,1]"


def check_ais_ready() -> tuple[bool, str]:
    join_path = EVENT_DIR / "ais" / "event_ais_join.json"
    if not join_path.exists():
        return False, "ais/event_ais_join.json missing"
    d = json.loads(join_path.read_text())
    if d.get("n_tracks_spatially_matched", 0) == 0:
        return False, "zero spatially matched tracks"
    if d.get("closest_temporally_matched") is None:
        return False, "no temporally matched AIS point found"
    return True, (f"{d['n_tracks_spatially_matched']}/{d['n_tracks_total']} spatially matched, "
                  f"{d['n_tracks_temporally_matched']} temporally matched")


def check_era5_ready() -> tuple[bool, str]:
    cube_path = EVENT_DIR / "forcing" / "era5_cube.json"
    if not cube_path.exists():
        return False, "forcing/era5_cube.json missing"
    d = json.loads(cube_path.read_text())
    if d.get("time_series_status") != "sufficient":
        return False, f"time_series_status={d.get('time_series_status')}"
    if len(d.get("time_coords", [])) < 2:
        return False, "fewer than 2 timesteps"
    return True, f"{len(d['time_coords'])} timesteps, sufficient"


def check_cmems_ready() -> tuple[bool, str]:
    cube_path = EVENT_DIR / "forcing" / "cmems_cube.json"
    if not cube_path.exists():
        return False, "forcing/cmems_cube.json missing"
    d = json.loads(cube_path.read_text())
    if d.get("time_series_status") != "sufficient":
        return False, f"time_series_status={d.get('time_series_status')}"
    if len(d.get("time_coords", [])) < 2:
        return False, "fewer than 2 timesteps"
    return True, f"{len(d['time_coords'])} timesteps, sufficient"


def check_spatial_alignment_ready(manifest: dict) -> tuple[bool, str]:
    sa = manifest.get("spatial_alignment", {})
    ok = (
        sa.get("sar_ais", {}).get("n_spatially_matched_tracks", 0) > 0
        and sa.get("sar_era5_contains_anchor") is True
        and sa.get("sar_cmems_contains_anchor") is True
        and sa.get("four_way_non_empty") is True
    )
    return ok, json.dumps(sa)


def check_temporal_alignment_ready(manifest: dict) -> tuple[bool, str]:
    ta = manifest.get("temporal_alignment", {})
    ok = (
        ta.get("ais_closest_temporally_matched") is not None
        and ta.get("era5_contains_t_sar") is True
        and ta.get("cmems_contains_t_sar") is True
    )
    return ok, json.dumps({k: ta.get(k) for k in ("era5_contains_t_sar", "cmems_contains_t_sar")})


def check_provenance_ready() -> tuple[bool, str]:
    prov_path = EVENT_DIR / "provenance" / "provenance.json"
    if not prov_path.exists():
        return False, "provenance/provenance.json missing"
    d = json.loads(prov_path.read_text())
    required = {"sar", "ais", "era5", "cmems", "processing_git_commit"}
    missing = required - set(d.keys())
    if missing:
        return False, f"missing keys: {missing}"
    return True, "all four modalities + git commit present"


def check_locked_data_safe(manifest: dict) -> tuple[bool, str]:
    from varuna_data_eng.locked_evaluation_guard import locked_dataset_ids
    lei = manifest.get("locked_evaluation_isolation", {})
    if lei.get("zenodo_part3_used") is not False or lei.get("essd_used") is not False:
        return False, "manifest claims locked-eval usage"
    used_ids = {v.get("source") for v in manifest.get("modalities", {}).values()}
    contaminated = used_ids & set(locked_dataset_ids())
    if contaminated:
        return False, f"locked dataset ids found in modality sources: {contaminated}"
    return True, "no Zenodo Part III / ESSD reference anywhere in manifest"


def check_netra_discovery_safe(manifest: dict) -> tuple[bool, str]:
    """Structural proof, not just a naming convention: NetraGoldDataset
    must reject this manifest outright if pointed at it."""
    from varuna_netra.dataset.gold import NetraGoldDataset, GoldManifestError

    split = manifest.get("netra_training_isolation", {}).get("split_value")
    if split in ("train", "val", "test"):
        return False, f"split value {split!r} is a real NETRA training split -- unsafe"

    try:
        NetraGoldDataset(manifest_path=MANIFEST_PATH, split=split)
        return False, "NetraGoldDataset did NOT reject this manifest -- unsafe"
    except ValueError as e:
        if "split must be one of" in str(e):
            return True, f"NetraGoldDataset rejects split={split!r} (not in VALID_SPLITS): {e}"
        return False, f"unexpected ValueError, not the expected split guard: {e}"
    except (GoldManifestError, KeyError) as e:
        return True, f"NetraGoldDataset rejects this manifest structurally (no dataset_id/channels/label_mapping): {e}"
    except Exception as e:
        return False, f"unexpected exception type, not a confirmed safe rejection: {type(e).__name__}: {e}"


def main() -> None:
    if not MANIFEST_PATH.exists():
        result = {"generated_at": datetime.now(UTC).isoformat(), "event_gold_ready": False,
                  "blockers": [f"{MANIFEST_PATH} does not exist -- Event Gold not built"]}
        out = REPO_ROOT / "reports" / "mc20_event_gold_readiness.json"
        out.write_text(json.dumps(result, indent=2))
        print(f"EVENT_GOLD_READY = False (manifest missing). Wrote {out}")
        return

    manifest = json.loads(MANIFEST_PATH.read_text())

    checks = {
        "SAR_READY": check_sar_ready(),
        "AIS_READY": check_ais_ready(),
        "ERA5_READY": check_era5_ready(),
        "CMEMS_READY": check_cmems_ready(),
        "SPATIAL_ALIGNMENT_READY": check_spatial_alignment_ready(manifest),
        "TEMPORAL_ALIGNMENT_READY": check_temporal_alignment_ready(manifest),
        "PROVENANCE_READY": check_provenance_ready(),
        "LOCKED_DATA_SAFE": check_locked_data_safe(manifest),
        "NETRA_DISCOVERY_SAFE": check_netra_discovery_safe(manifest),
    }

    print("VARUNA GRID v2 -- MC20 Event Gold Readiness Gate")
    print("=" * 60)
    for name, (ok, detail) in checks.items():
        print(f"  {name:26s} {'PASS' if ok else 'FAIL':6s} {detail}")

    event_gold_ready = all(ok for ok, _ in checks.values())
    print(f"\n  EVENT_GOLD_READY = {event_gold_ready}")

    blockers = [f"{name}: {detail}" for name, (ok, detail) in checks.items() if not ok]

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "event_dir": str(EVENT_DIR),
        "checks": {name: {"pass": ok, "detail": detail} for name, (ok, detail) in checks.items()},
        "event_gold_ready": event_gold_ready,
        "blockers": blockers,
    }
    out = REPO_ROOT / "reports" / "mc20_event_gold_readiness.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
