"""
VARUNA GRID — NYAYA Scientific Service Boundaries.

Clean interfaces between scientific computation and application layer.
These services accept domain inputs and return contract types.
They do NOT call FastAPI, Postgres, Redis, or MinIO.
"""
import numpy as np
from typing import List
from datetime import datetime, timezone

from varuna_contracts.schemas import VesselTrack
from varuna_contracts.decision import (
    AttributionResultV2, CandidateScore, DecisionState,
    LatentFinding, PriorContribution,
)
from varuna_contracts.evidence import (
    EvidenceEnvelope, TrustState, ValidityState, Provenance,
)
from varuna_contracts.phi import PhiField

from varuna_prativartan.config import PratiConfig
from varuna_prativartan.current_field import SyntheticModelCurrentField, SyntheticWindField
from varuna_prativartan.ensemble import run_backward_ensemble
from varuna_prativartan.phi_builder import build_phi_field

from varuna_nyaya.likelihoods import compute_density_likelihoods
from varuna_nyaya.prior import compute_prior
from varuna_nyaya.posterior import compute_posterior
from varuna_nyaya.validity_gate import evaluate_validity_gate
from varuna_geospatial.utils import haversine_km_vec


class PrativartanService:
    """Runs backward ensemble advection and builds PhiField."""

    def reconstruct_origin(
        self,
        slick_lons: np.ndarray,
        slick_lats: np.ndarray,
        obs_time_hours: float,
        case_id: str,
        slick_id: str,
        age_prior_mean_hours: float = 36.0,
        age_prior_std_hours: float = 24.0,
        n_particles: int = 500,
        n_ensemble: int = 20,
        seed: int = 42,
    ) -> PhiField:
        config = PratiConfig(
            n_particles=n_particles,
            n_ensemble=n_ensemble,
            backward_duration_hours=age_prior_mean_hours + 2.0 * age_prior_std_hours,
            seed=seed,
        )
        base_env = EvidenceEnvelope(
            artifact_id=case_id,
            produced_by="prativartan_service",
            provenance=Provenance(source_id="synthetic"),
        )
        current = SyntheticModelCurrentField()
        wind = SyntheticWindField()

        ensemble_res = run_backward_ensemble(
            obs_lons=slick_lons, obs_lats=slick_lats,
            obs_time_hours=obs_time_hours,
            current=current, wind=wind, config=config,
        )
        phi = build_phi_field(
            ensemble_results=ensemble_res,
            case_id=case_id, slick_id=slick_id,
            input_envelope=base_env,
            obs_time_hours=obs_time_hours,
            age_prior_mean_hours=age_prior_mean_hours,
            age_prior_std_hours=age_prior_std_hours,
            config=config,
        )
        return phi


class NyayaService:
    """Runs attribution: density likelihoods -> priors -> posterior."""

    def attribute(
        self,
        phi: PhiField,
        tracks: List[VesselTrack],
        case_id: str,
        slick_lons: np.ndarray,
        slick_lats: np.ndarray,
        corridor_width_km: float = 5.0,
        latent_prior: float = 0.5,
    ) -> AttributionResultV2:
        phi_npz = np.load(phi.data_path)
        densities, rho_0, diag = compute_density_likelihoods(
            phi_data=phi_npz["phi"],
            lon_edges=phi_npz["lon_edges"],
            lat_edges=phi_npz["lat_edges"],
            time_edges=phi_npz["time_edges"],
            tracks=tracks,
            corridor_width_km=corridor_width_km,
        )

        priors_dict = {}
        prior_contribs = {}
        for track in tracks:
            prior = compute_prior(track, phi)
            priors_dict[track.mmsi] = prior.combined
            prior_contribs[track.mmsi] = prior

        posterior, distinguish, decision, entropy = compute_posterior(
            densities=densities,
            latent_density=rho_0,
            priors=priors_dict,
            latent_prior=latent_prior,
        )

        slick_center_lon = float(np.mean(slick_lons))
        slick_center_lat = float(np.mean(slick_lats))
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

        raw_candidates = []
        for mmsi in posterior:
            if mmsi == "LATENT_SOURCE":
                continue
            L_k = diag["raw_masses"].get(mmsi, 0.0)
            prior = prior_contribs[mmsi]
            track = next(t for t in tracks if t.mmsi == mmsi)
            min_dist = float("inf")
            closest_time = 0.0
            for pt in track.points:
                d = haversine_km_vec(
                    np.array([pt.lon]), np.array([pt.lat]),
                    slick_center_lon, slick_center_lat,
                )[0]
                if d < min_dist:
                    min_dist = d
                    closest_time = (pt.timestamp - base_time).total_seconds() / 3600.0

            raw_candidates.append({
                "mmsi": mmsi, "vessel_type": track.vessel_type,
                "path_integral": L_k, "prior": prior,
                "likelihood": L_k, "posterior": posterior[mmsi],
                "closest_approach_km": min_dist,
                "time_at_closest_hours": closest_time,
                "phi_mass_explained": L_k,
            })

        raw_candidates.sort(key=lambda c: c["posterior"], reverse=True)
        candidate_scores = [CandidateScore(rank=i+1, **rc) for i, rc in enumerate(raw_candidates)]

        latent_prob = posterior.get("LATENT_SOURCE", 0.0)
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
            artifact_id=f"attr-{case_id}", produced_by="nyaya_service",
        )

        return AttributionResultV2(
            case_id=case_id, slick_id=phi.slick_id, phi_id=phi.phi_id,
            decision_state=decision, candidates=candidate_scores,
            latent_probability=latent_prob, latent_finding=latent_finding,
            top_posterior=top_post, top_gap=top_gap_val,
            distinguishability=distinguish, posterior_entropy=entropy,
            n_candidates_screened=len(tracks),
            n_candidates_scored=len(candidate_scores),
            envelope=attr_env,
        )


class ValidityService:
    """Evaluates the validity gate on attribution results."""

    def evaluate(self, phi: PhiField, attribution: AttributionResultV2) -> dict:
        from varuna_nyaya.validity_gate import evaluate_validity_gate
        result = evaluate_validity_gate(
            phi=phi, attribution=attribution,
            source_trust=TrustState.TRUSTED,
        )
        return {
            "state": result.state.value,
            "checks": [{"name": c.name, "passed": c.passed} for c in result.checks],
            "blocking_reasons": result.blocking_reasons,
            "caveats": result.officer_visible_caveats,
            "allows_action": result.allows_operational_action,
        }
