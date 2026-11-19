"""
VARUNA GRID v2 -- Track 2 Phases 5 & 8: production Validity Gate + real
analytical chain (real AIS + real ERA5 + real CMEMS + production Phi ->
NYAYA -> ValidityGate).

Loads the production-scale PhiField (with a real, non-fabricated
SensitivityBlock) written by scripts/mc20_production_phi_sensitivity.py,
sources REAL AIS tracks through packages/varuna_integration/ais_source.py's
EventAISAdapter (per router-datasets-ca -- delegates rather than
duplicating), runs the existing NyayaService.attribute() and
ValidityService.evaluate() unmodified, and records the exact real gate
result and reasons. No threshold or scoring logic is touched.

Read-only. Does not touch NETRA.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"
sys.path.insert(0, str(REPO_ROOT / "packages"))


def main():
    from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
    from varuna_contracts.phi import PhiField
    from varuna_source_adapters.protocol import SourceQuery, fetch_with_mode
    from varuna_contracts.schemas import BBox
    from varuna_integration.ais_source import AISJoinStatus, EventAISAdapter, load_event_tracks
    from varuna_integration.stage import StageStatus
    from varuna_nyaya.services import NyayaService, ValidityService

    phi_json = json.loads((REPO_ROOT / "reports" / "mc20_production_phi_field.json").read_text(encoding="utf-8"))
    phi = PhiField.model_validate(phi_json)

    manifest = json.loads((GOLD_DIR / "manifest.json").read_text(encoding="utf-8"))
    sar_bbox = manifest["modalities"]["sar"]["bbox"]
    sar_time = datetime.fromisoformat(manifest["modalities"]["sar"]["timestamp"])
    if sar_time.tzinfo is None:
        sar_time = sar_time.replace(tzinfo=UTC)

    result = {"generated_at": datetime.now(UTC).isoformat(), "phi_id": phi.phi_id}

    # ---- Real AIS via EventAISAdapter (delegating, not duplicating) ----
    join_path = GOLD_DIR / "ais" / "event_ais_join.json"
    adapter = EventAISAdapter(join_path)
    query = SourceQuery(
        bbox=BBox(**sar_bbox), time_start=sar_time, time_end=sar_time,
        product_id="mc20_v0_1_ais",
    )
    ais_result = load_event_tracks(adapter, query, status=AISJoinStatus.TEMPORALLY_MATCHED, limit=5)
    result["ais_stage"] = {
        "status": ais_result.status.value,
        "evidence_mode": ais_result.evidence_mode.value if ais_result.evidence_mode else None,
        "reason": ais_result.reason,
        "detail": ais_result.detail,
    }

    if ais_result.status is not StageStatus.PRODUCED:
        # Fall back to spatially-matched-only, explicitly reported as a
        # weaker evidentiary claim -- never silently treated as temporal
        # evidence.
        ais_result_fallback = load_event_tracks(
            adapter, query, status=AISJoinStatus.SPATIALLY_MATCHED_ONLY, limit=5
        )
        result["ais_stage_fallback_to_spatial_only"] = {
            "status": ais_result_fallback.status.value,
            "evidence_mode": ais_result_fallback.evidence_mode.value if ais_result_fallback.evidence_mode else None,
            "reason": ais_result_fallback.reason,
            "detail": ais_result_fallback.detail,
        }
        ais_result = ais_result_fallback

    if ais_result.status is not StageStatus.PRODUCED:
        result["status"] = "BLOCKED_AT_AIS"
        (REPO_ROOT / "reports" / "mc20_production_validity_gate.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        print("BLOCKED at AIS stage:", result["ais_stage"])
        return result

    tracks = ais_result.value
    tracks_envelope = EvidenceEnvelope(
        artifact_id="mc20-ais-production", produced_by="mc20_production_validity_gate",
        provenance=Provenance(
            source_id=adapter.source_id,
            notes=f"{len(tracks)} real AIS tracks via EventAISAdapter, status={ais_result.detail.get('requested_status')}",
        ),
        mode=ais_result.evidence_mode,
    )

    npz = np.load(phi.data_path)
    slick_lons = np.array([sar_bbox["min_lon"] + sar_bbox["max_lon"]]) / 2 * np.ones(1)
    slick_lats = np.array([sar_bbox["min_lat"] + sar_bbox["max_lat"]]) / 2 * np.ones(1)

    nyaya = NyayaService()
    attribution = nyaya.attribute(
        phi=phi, tracks=tracks, case_id=phi.case_id,
        slick_lons=slick_lons, slick_lats=slick_lats,
        tracks_envelope=tracks_envelope,
    )
    result["attribution"] = {
        "decision_state": attribution.decision_state.value,
        "n_candidates_screened": attribution.n_candidates_screened,
        "n_candidates_scored": attribution.n_candidates_scored,
        "top_posterior": attribution.top_posterior,
        "top_gap": attribution.top_gap,
        "latent_probability": attribution.latent_probability,
        "latent_finding": attribution.latent_finding.value,
        "distinguishability": attribution.distinguishability,
        "posterior_entropy": attribution.posterior_entropy,
        "envelope_mode": attribution.envelope.mode.value,
    }

    validity = ValidityService()
    gate = validity.evaluate(phi=phi, attribution=attribution)
    result["validity_gate"] = {
        "state": gate.state.value,
        "allows_operational_action": gate.allows_operational_action,
        "source_trust": gate.source_trust.value,
        "blocking_reasons": gate.blocking_reasons,
        "officer_visible_caveats": gate.officer_visible_caveats,
        "checks": [
            {
                "name": c.name, "passed": c.passed, "observed": c.observed,
                "threshold": c.threshold, "detail": c.detail,
                "reason_code": c.reason_code.value if c.reason_code else None,
            }
            for c in gate.checks
        ],
        "envelope_mode": gate.envelope.mode.value,
    }
    result["status"] = "SUCCESS"

    out_path = REPO_ROOT / "reports" / "mc20_production_validity_gate.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Written {out_path}")
    print(f"Gate state: {gate.state.value}, allows_operational_action={gate.allows_operational_action}")
    print(f"Blocking reasons: {gate.blocking_reasons}")
    return result


if __name__ == "__main__":
    main()
