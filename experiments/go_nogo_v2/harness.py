"""
VARUNA GRID — Go/No-Go v2 Experiment Harness.
"""
import time
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
    EvidenceEnvelope, EvidenceMode, TrustState, ValidityState, Provenance
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
        mode=EvidenceMode.SIMULATED,
    )
    
    # 2. PRATIVARTAN
    current = SyntheticModelCurrentField()
    wind = SyntheticWindField()
    
    age_prior_mean = config.backward_duration_hours
    age_prior_std = 24.0
    
    _t0 = time.perf_counter()
    ensemble_res = run_backward_ensemble(
        obs_lons=slick_lons,
        obs_lats=slick_lats,
        obs_time_hours=obs_time_hours,
        current=current,
        wind=wind,
        config=config
    )
    _runtime_seconds = time.perf_counter() - _t0

    phi = build_phi_field(
        ensemble_results=ensemble_res,
        case_id=case_id,
        slick_id=slick_id,
        input_envelope=base_env,
        obs_time_hours=obs_time_hours,
        age_prior_mean_hours=age_prior_mean,
        age_prior_std_hours=age_prior_std,
        config=config,
        runtime_seconds=_runtime_seconds,
    )
    
    # 3. NYAYA — compute density likelihoods + priors + posterior
    from varuna_nyaya.services import NyayaService
    nyaya = NyayaService()
    attribution = nyaya.attribute(
        phi=phi,
        tracks=tracks,
        case_id=case_id,
        slick_lons=slick_lons,
        slick_lats=slick_lats,
    )
    decision = attribution.decision_state
    candidate_scores = attribution.candidates
    latent_prob = attribution.latent_probability
    distinguish = attribution.distinguishability
    entropy = attribution.posterior_entropy
    posterior = {c.mmsi: c.posterior for c in candidate_scores}
    posterior["LATENT_SOURCE"] = latent_prob
    
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
