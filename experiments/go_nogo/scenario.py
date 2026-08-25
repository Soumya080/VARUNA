"""Scenario assembly for one fair synthetic trial."""

from __future__ import annotations

from dataclasses import dataclass

from experiments.go_nogo.candidates import CandidateTrack, generate_candidates
from experiments.go_nogo.config import ExperimentConfig
from experiments.go_nogo.forcing import (
    StructuredForcing,
    make_inference_forcing,
    make_truth_forcing,
)
from experiments.go_nogo.slick import ObservedSlick
from experiments.go_nogo.truth import ReleaseTruth, generate_slick, generate_truth

import numpy as np


@dataclass(frozen=True)
class Scenario:
    trial_key: str
    truth: ReleaseTruth
    observed_slick: ObservedSlick
    truth_forcing: StructuredForcing
    inference_forcing: StructuredForcing
    candidates: list[CandidateTrack]


def build_scenario(
    *,
    trial_key: str,
    slick_age_hours: float,
    traffic_density: int,
    forcing_perturbation: str,
    ais_uncertainty: str,
    config: ExperimentConfig,
    trial_index: int,
) -> Scenario:
    scenario_rng = np.random.default_rng(config.scenario_seed + trial_index)
    forcing_rng_seed = config.forcing_seed + trial_index
    candidate_rng = np.random.default_rng(config.candidate_seed + trial_index)
    slick_rng = np.random.default_rng(config.seed + 10_000 + trial_index)

    truth = generate_truth(trial_key, slick_age_hours, config, scenario_rng)
    truth_forcing = make_truth_forcing(forcing_rng_seed, truth.lon, truth.lat)
    inference_forcing = make_inference_forcing(
        truth_forcing,
        forcing_perturbation,
        forcing_rng_seed + 50_000,
    )
    observed_slick = generate_slick(trial_key, truth, truth_forcing, config, slick_rng)
    candidates = generate_candidates(
        truth,
        traffic_density,
        ais_uncertainty,
        config,
        candidate_rng,
    )
    return Scenario(
        trial_key=trial_key,
        truth=truth,
        observed_slick=observed_slick,
        truth_forcing=truth_forcing,
        inference_forcing=inference_forcing,
        candidates=candidates,
    )
