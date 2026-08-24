"""
VARUNA GRID — Go/No-Go v2 Experiment Harness.
"""
import uuid
from typing import List, Dict
from datetime import datetime, timezone
import numpy as np
from varuna_contracts.schemas import VesselTrack
from varuna_contracts.decision import (
    AttributionResultV2, CandidateScore, DecisionState, 
    LatentFinding, PriorContribution
)
from varuna_contracts.evidence import (
    EvidenceEnvelope, TrustState, ValidityState, Provenance
)
from varuna_prativartan.config import PratiConfig
from varuna_prativartan.current_field import SyntheticModelCurrentField, SyntheticWindField
from varuna_prativartan.ensemble import run_backward_ensemble
from varuna_prativartan.phi_builder import build_phi_field
from varuna_nyaya.scorer import compute_path_integral
from varuna_nyaya.prior import compute_prior
from varuna_nyaya.latent import compute_latent_probability
from varuna_nyaya.posterior import compute_posterior
from varuna_nyaya.validity_gate import evaluate_validity_gate
from varuna_geospatial.utils import haversine_km_vec

def run_case(
    slick_lons: np.ndarray,
    slick_lats: np.ndarray,
    obs_time_hours: float,
    tracks: List[VesselTrack],
    true_mmsi: str,
    config: PratiConfig,
) -> dict:
    """
    Run a single case through the pipeline.
    """
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    slick_id = f"slick-{uuid.uuid4().hex[:8]}"
    
    # 1. Base Envelope
    base_env = EvidenceEnvelope(
        artifact_id=case_id,
        produced_by="go_nogo_v2_harness",
        provenance=Provenance(source_id="synthetic_go_nogo_v2"),
    )
    
    # 2. PRATIVARTAN
    current = SyntheticModelCurrentField()
    wind = SyntheticWindField()
    
    age_prior_mean = config.backward_duration_hours
    age_prior_std = 24.0
    
    ensemble_res = run_backward_ensemble(
        obs_lons=slick_lons,
        obs_lats=slick_lats,
        obs_time_hours=obs_time_hours,
        current=current,
        wind=wind,
        config=config
    )
    
    phi = build_phi_field(
        ensemble_results=ensemble_res,
        case_id=case_id,
        slick_id=slick_id,
        input_envelope=base_env,
        obs_time_hours=obs_time_hours,
        age_prior_mean_hours=age_prior_mean,
        age_prior_std_hours=age_prior_std,
        config=config
    )
    
    # 3. NYAYA — compute likelihoods + priors
    likelihoods = {}
    priors = {}
    for track in tracks:
        L_k = compute_path_integral(track, phi)
        prior = compute_prior(track, phi)
        likelihoods[track.mmsi] = L_k * prior.combined
        priors[track.mmsi] = (L_k, prior)
        
    # Load phi data once for latent computation
    phi_npz = np.load(phi.data_path)
    L_0 = compute_latent_probability(
        phi_data=phi_npz['phi'],
        lon_edges=phi_npz['lon_edges'],
        lat_edges=phi_npz['lat_edges'],
        time_edges=phi_npz['time_edges'],
        tracks=tracks,
        corridor_width_km=5.0
    )
    
    posterior, distinguish, decision, entropy = compute_posterior(
        likelihoods=likelihoods,
        latent_probability_mass=L_0,
        latent_prior_weight=1.0
    )
    
    # Build CandidateScore list sorted by posterior descending
    slick_center_lon = float(np.mean(slick_lons))
    slick_center_lat = float(np.mean(slick_lats))
    
    # Collect raw candidate data first
    raw_candidates = []
    for mmsi in posterior:
        if mmsi == "LATENT_SOURCE":
            continue
        L_k, prior = priors[mmsi]
        
        # Compute closest approach for the candidate
        track = next(t for t in tracks if t.mmsi == mmsi)
        min_dist = float('inf')
        min_time = 0.0
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for pt in track.points:
            d = haversine_km_vec(
                np.array([pt.lon]), np.array([pt.lat]),
                slick_center_lon, slick_center_lat
            )[0]
            if d < min_dist:
                min_dist = d
                min_time = (pt.timestamp - base_time).total_seconds() / 3600.0
                
        raw_candidates.append({
            "mmsi": mmsi,
            "vessel_type": track.vessel_type,
            "path_integral": L_k,
            "prior": prior,
            "likelihood": L_k * prior.combined,
            "posterior": posterior[mmsi],
            "closest_approach_km": min_dist,
            "time_at_closest_hours": min_time,
            "phi_mass_explained": posterior[mmsi],
        })
    
    # Sort by posterior descending BEFORE constructing pydantic objects
    raw_candidates.sort(key=lambda c: c["posterior"], reverse=True)
    
    candidate_scores = []
    for i, rc in enumerate(raw_candidates):
        candidate_scores.append(CandidateScore(
            rank=i + 1,
            **rc,
        ))
    
    latent_prob = posterior.get("LATENT_SOURCE", 0.0)
    
    # Determine latent finding
    if latent_prob > 0.5:
        latent_finding = LatentFinding.NO_PLAUSIBLE_VISIBLE_SOURCE
    elif latent_prob > 0.2:
        latent_finding = LatentFinding.VISIBLE_SOURCES_EXIST_BUT_WEAK
    else:
        latent_finding = LatentFinding.INSUFFICIENT_COVERAGE
    
    top_post = candidate_scores[0].posterior if candidate_scores else 0.0
    top_gap_val = 0.0
    if len(candidate_scores) >= 2:
        top_gap_val = candidate_scores[0].posterior - candidate_scores[1].posterior
    elif len(candidate_scores) == 1:
        top_gap_val = candidate_scores[0].posterior
    
    attr_env = phi.envelope.derive(
        artifact_id=f"attr-{case_id}",
        produced_by="nyaya_attribution"
    )
    
    attribution = AttributionResultV2(
        case_id=case_id,
        slick_id=slick_id,
        phi_id=phi.phi_id,
        decision_state=decision,
        candidates=candidate_scores,
        latent_probability=latent_prob,
        latent_finding=latent_finding,
        top_posterior=top_post,
        top_gap=top_gap_val,
        distinguishability=distinguish,
        posterior_entropy=entropy,
        n_candidates_screened=len(tracks),
        n_candidates_scored=len(candidate_scores),
        envelope=attr_env,
    )
    
    # 4. Validity Gate
    gate_result = evaluate_validity_gate(
        phi=phi,
        attribution=attribution,
        source_trust=TrustState.TRUSTED
    )
    
    pred_mmsi = candidate_scores[0].mmsi if candidate_scores else "LATENT_SOURCE"
    if latent_prob > 0.5:
        pred_mmsi = "LATENT_SOURCE"
    
    return {
        "case_id": case_id,
        "true_mmsi": true_mmsi,
        "pred_mmsi": pred_mmsi,
        "is_correct": pred_mmsi == true_mmsi,
        "posterior": {k: v for k, v in posterior.items()},
        "decision": decision.value,
        "gate_state": gate_result.state.value,
        "entropy": entropy,
        "distinguishability": distinguish,
        "latent_prob": latent_prob
    }
