"""
VARUNA GRID — NYAYA Scientific Service Boundaries.

Clean interfaces between scientific computation and application layer.
These services accept domain inputs and return contract types.
They do NOT call FastAPI, Postgres, Redis, or MinIO.
"""
import time
from datetime import UTC, datetime

import numpy as np

from varuna_contracts.decision import (
    AttributionResultV2,
    CandidateScore,
    LatentFinding,
    ValidityGateResult,
)
from varuna_contracts.evidence import (
    EvidenceEnvelope,
    EvidenceMode,
    Provenance,
)
from varuna_contracts.phi import PhiField
from varuna_contracts.schemas import VesselTrack
from varuna_geospatial.utils import haversine_km_vec
from varuna_nyaya.likelihoods import compute_density_likelihoods
from varuna_nyaya.posterior import compute_posterior
from varuna_nyaya.prior import compute_prior
from varuna_nyaya.validity_gate import evaluate_validity_gate
from varuna_prativartan.config import PratiConfig
from varuna_prativartan.current_field import (
    AbstractCurrentField,
    AbstractWindField,
    SyntheticModelCurrentField,
    SyntheticWindField,
)
from varuna_prativartan.ensemble import run_backward_ensemble
from varuna_prativartan.phi_builder import build_phi_field


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
        input_envelope: EvidenceEnvelope | None = None,
        current: AbstractCurrentField | None = None,
        wind: AbstractWindField | None = None,
        output_dir: str | None = None,
        forcing_current_source: str | None = None,
        forcing_wind_source: str | None = None,
    ) -> PhiField:
        """
        ADR-0017: `forcing_current_source`/`forcing_wind_source`, when
        given, name what `current`/`wind` actually are (e.g.
        `"cmems.real"`) — omitted, they default to the honest
        `"synthetic_shear_v1"`/`"synthetic_wind_v1"` regardless of what
        `current`/`wind` objects were passed, exactly as before this ADR.
        Passing a real field object without ALSO naming it here would leave
        `PhiField.forcing_current_source` claiming synthetic while real
        forcing was actually used — this makes that mismatch impossible by
        construction rather than something a caller has to remember.

        `input_envelope`, when supplied, carries the real forcing/evidence
        provenance (mode, trust, quality) into the resulting PhiField via
        `.derive()`.

        `current`/`wind`, when supplied, are the real forcing boundary:
        pass a `CubeBackedCurrentField`/`CubeBackedWindField`
        (`packages/varuna_prativartan/cube_field.py`) built from a real
        ForcingCube to run the ensemble against real ERA5/CMEMS data
        instead of the synthetic fields. Both default to `None`, in which
        case the existing `SyntheticModelCurrentField`/`SyntheticWindField`
        are used — every pre-existing call site is unaffected. This is a
        boundary injection point only; `run_backward_ensemble`'s advection
        mathematics are untouched regardless of which field implementation
        is passed in.

        When `current`/`wind` are supplied but `input_envelope` is not, the
        default envelope below still applies (`mode=EvidenceMode.SIMULATED`)
        — passing a real forcing field does not by itself upgrade
        provenance; the caller must also supply an envelope carrying the
        real `mode`, exactly as ADR-0006 requires (mode is never inferred,
        only ever passed through explicitly).

        The `mode=EvidenceMode.SIMULATED` default reflects current systemic
        reality (there is nothing else the fully-default call path could
        honestly be), not a value read from settings or config. It replaces
        the previous unconditional `Provenance(source_id="synthetic")`,
        which asserted synthetic *lineage* but never declared *mode* at all
        — see ADR-0006.
        """
        config = PratiConfig(
            n_particles=n_particles,
            n_ensemble=n_ensemble,
            backward_duration_hours=age_prior_mean_hours + 2.0 * age_prior_std_hours,
            seed=seed,
        )
        if input_envelope is not None:
            base_env = input_envelope
        else:
            base_env = EvidenceEnvelope(
                artifact_id=case_id,
                produced_by="prativartan_service",
                provenance=Provenance(source_id="synthetic"),
                mode=EvidenceMode.SIMULATED,
            )
        current = current if current is not None else SyntheticModelCurrentField()
        wind = wind if wind is not None else SyntheticWindField()

        t0 = time.perf_counter()
        ensemble_res = run_backward_ensemble(
            obs_lons=slick_lons, obs_lats=slick_lats,
            obs_time_hours=obs_time_hours,
            current=current, wind=wind, config=config,
        )
        runtime_seconds = time.perf_counter() - t0

        build_kwargs = dict(
            ensemble_results=ensemble_res,
            case_id=case_id, slick_id=slick_id,
            input_envelope=base_env,
            obs_time_hours=obs_time_hours,
            age_prior_mean_hours=age_prior_mean_hours,
            age_prior_std_hours=age_prior_std_hours,
            config=config,
            runtime_seconds=runtime_seconds,
            output_dir=output_dir,
        )
        if forcing_current_source is not None:
            build_kwargs["forcing_current_source"] = forcing_current_source
        if forcing_wind_source is not None:
            build_kwargs["forcing_wind_source"] = forcing_wind_source
        phi = build_phi_field(**build_kwargs)
        return phi

    def reconstruct_origin_with_sensitivity(
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
        input_envelope: EvidenceEnvelope | None = None,
        current: AbstractCurrentField | None = None,
        wind: AbstractWindField | None = None,
    ) -> PhiField:
        """
        Like `reconstruct_origin`, but additionally runs the real
        sensitivity sweep (ADR-0007) and returns a PhiField with
        `sensitivity` genuinely populated instead of None.

        This is a SEPARATE, explicitly-opt-in method rather than the
        default behavior of `reconstruct_origin` because the sweep costs
        7x the ensemble runtime (1 baseline + 2 age + 2 forcing + 2
        diffusivity real re-runs) — every existing caller of
        `reconstruct_origin` (CaseWorkflow, tests, experiments) is
        completely unaffected by this method's existence and continues to
        get sensitivity=None at the cheap 1-run cost, exactly as before.

        Raises ValueError (propagated from `build_sensitivity_block`) if
        the baseline field is degenerate (zero effective_support_km2) —
        this is not caught and silenced, since a fabricated sensitivity
        would be worse than a raised, visible error.
        """
        from varuna_prativartan.sensitivity import build_sensitivity_block, run_sensitivity_sweep

        config = PratiConfig(
            n_particles=n_particles,
            n_ensemble=n_ensemble,
            backward_duration_hours=age_prior_mean_hours + 2.0 * age_prior_std_hours,
            seed=seed,
        )
        if input_envelope is not None:
            base_env = input_envelope
        else:
            base_env = EvidenceEnvelope(
                artifact_id=case_id,
                produced_by="prativartan_service",
                provenance=Provenance(source_id="synthetic"),
                mode=EvidenceMode.SIMULATED,
            )
        current = current if current is not None else SyntheticModelCurrentField()
        wind = wind if wind is not None else SyntheticWindField()

        sweep = run_sensitivity_sweep(
            slick_lons=slick_lons, slick_lats=slick_lats, obs_time_hours=obs_time_hours,
            case_id=case_id, slick_id=slick_id,
            age_prior_mean_hours=age_prior_mean_hours, age_prior_std_hours=age_prior_std_hours,
            config=config, current=current, wind=wind, input_envelope=base_env,
        )
        block = build_sensitivity_block(sweep)

        phi = sweep.baseline.phi
        phi.sensitivity = block  # PhiField has validate_assignment=True
        return phi


class NyayaService:
    """Runs attribution: density likelihoods -> priors -> posterior."""

    def attribute(
        self,
        phi: PhiField,
        tracks: list[VesselTrack],
        case_id: str,
        slick_lons: np.ndarray,
        slick_lats: np.ndarray,
        corridor_width_km: float = 5.0,
        latent_prior: float = 0.5,
        tracks_envelope: EvidenceEnvelope | None = None,
    ) -> AttributionResultV2:
        """
        `tracks_envelope`, when supplied, carries the AIS source's own
        provenance/mode into the merged output via `.derive(also_from=...)`
        — e.g. REAL Phi + SIMULATED AIS -> SIMULATED, never the reverse. No
        real AIS adapter exists yet (Tranche 3), so `VesselTrack` itself
        carries no per-track envelope today and every current call site
        omits this parameter; the result's mode is then simply phi's own,
        unchanged from before this parameter existed.
        """
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
        base_time = datetime(2026, 1, 1, tzinfo=UTC)

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
            also_from=[tracks_envelope] if tracks_envelope is not None else (),
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

    def evaluate(self, phi: PhiField, attribution: AttributionResultV2) -> ValidityGateResult:
        """
        Returns the typed `ValidityGateResult` contract directly — this used
        to hardcode `source_trust=TrustState.TRUSTED` regardless of input and
        return an untyped dict, discarding reason codes, the envelope, and
        anything DataGuard might have actually determined upstream. Trust is
        now read from `attribution.envelope.trust`, the real value produced
        by whatever built that envelope (today, still TRUSTED by default
        because no source has ever marked it otherwise — see ADR-0006 on why
        that is a starting condition to close in a later tranche, not a
        promotion of this call site).
        """
        return evaluate_validity_gate(
            phi=phi, attribution=attribution,
            source_trust=attribution.envelope.trust,
        )
