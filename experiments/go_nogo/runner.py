"""Single-trial runner for the fair go/no-go experiment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from experiments.go_nogo.baselines import deterministic_backtrack_rank, nearest_vessel_rank
from experiments.go_nogo.config import ExperimentConfig
from experiments.go_nogo.metrics import TrialMetrics, compute_metrics
from experiments.go_nogo.nyaya import Attribution, attribute
from experiments.go_nogo.prativartan import PhiArtifact, run_prativartan
from experiments.go_nogo.scenario import Scenario, build_scenario


@dataclass(frozen=True)
class TrialResult:
    trial_key: str
    scenario: Scenario
    phi: PhiArtifact
    attribution: Attribution
    metrics: TrialMetrics
    nearest_ranking: list[str]
    deterministic_ranking: list[str]
    truth_leakage_checks: dict[str, bool]

    def to_row(self) -> dict[str, object]:
        guilty = next(c for c in self.scenario.candidates if c.is_guilty)
        top = self.attribution.candidates[0] if self.attribution.candidates else None
        row = {
            "trial_key": self.trial_key,
            "slick_age_hours": self.scenario.truth.slick_age_hours,
            "traffic_density": len(self.scenario.candidates),
            "guilty_mmsi": guilty.mmsi,
            "top_mmsi": top.mmsi if top else None,
            "decision_state": self.attribution.decision_state,
            "latent_probability": self.attribution.latent_probability,
            "top_gap": self.attribution.top_gap,
            "distinguishability": self.attribution.distinguishability,
            "phi_entropy": self.phi.diagnostics["entropy"],
            "contract_status": "available" if self.phi.contract is not None else "unavailable",
            "contract_error": self.phi.contract_error,
            **asdict(self.metrics),
        }
        for key, passed in self.truth_leakage_checks.items():
            row[f"leak_check_{key}"] = passed
        return row


def _truth_leakage_checks(result: TrialResult | None, scenario: Scenario, phi: PhiArtifact) -> dict[str, bool]:
    age_samples_not_true = abs(
        scenario.observed_slick.age_prior_mean_hours - scenario.truth.slick_age_hours
    ) > 1e-6
    phi_covers_truth_time = phi.time_edges[0] <= scenario.truth.release_time_hours <= phi.time_edges[-1]
    candidates_full_envelope = all(
        c.start_time_hours <= scenario.truth.release_time_hours
        and c.end_time_hours >= scenario.truth.observation_time_hours
        for c in scenario.candidates
    )
    return {
        "true_age_not_passed_as_mean": bool(age_samples_not_true),
        "phi_time_domain_covers_truth": bool(phi_covers_truth_time),
        "candidate_tracks_cover_same_envelope": bool(candidates_full_envelope),
    }


def run_trial(
    *,
    slick_age_hours: float,
    traffic_density: int,
    forcing_perturbation: str,
    ais_uncertainty: str,
    trial_id: int,
    config: ExperimentConfig,
    output_dir: Path,
) -> TrialResult:
    trial_key = (
        f"age{int(slick_age_hours)}-n{traffic_density}-{forcing_perturbation}-"
        f"{ais_uncertainty}-{trial_id:04d}"
    )
    scenario = build_scenario(
        trial_key=trial_key,
        slick_age_hours=slick_age_hours,
        traffic_density=traffic_density,
        forcing_perturbation=forcing_perturbation,
        ais_uncertainty=ais_uncertainty,
        config=config,
        trial_index=trial_id
        + int(slick_age_hours * 100)
        + traffic_density * 10_000
        + hash((forcing_perturbation, ais_uncertainty)) % 10_000,
    )
    rng = np.random.default_rng(config.seed + trial_id)
    phi = run_prativartan(
        scenario.observed_slick,
        scenario.inference_forcing,
        config,
        trial_key=trial_key,
        output_dir=output_dir,
        rng=rng,
    )
    attribution = attribute(phi, scenario.candidates, config)
    guilty = next(c for c in scenario.candidates if c.is_guilty)
    varuna_ranking = [c.mmsi for c in attribution.candidates]
    nearest = nearest_vessel_rank(scenario.observed_slick, scenario.candidates)
    deterministic = deterministic_backtrack_rank(
        scenario.observed_slick,
        scenario.candidates,
        scenario.inference_forcing,
        config,
        rng,
    )
    metrics = compute_metrics(
        varuna_ranking,
        nearest,
        deterministic,
        guilty.mmsi,
        attribution.posterior_entropy,
        len(scenario.candidates),
    )
    placeholder = TrialResult(
        trial_key=trial_key,
        scenario=scenario,
        phi=phi,
        attribution=attribution,
        metrics=metrics,
        nearest_ranking=nearest,
        deterministic_ranking=deterministic,
        truth_leakage_checks={},
    )
    return TrialResult(
        trial_key=trial_key,
        scenario=scenario,
        phi=phi,
        attribution=attribution,
        metrics=metrics,
        nearest_ranking=nearest,
        deterministic_ranking=deterministic,
        truth_leakage_checks=_truth_leakage_checks(placeholder, scenario, phi),
    )
