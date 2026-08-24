"""
VARUNA GRID — Posterior normalisation and decision state logic.
"""
import numpy as np
from typing import Dict, Tuple
from varuna_contracts.decision import DecisionState


def compute_posterior(
    likelihoods: Dict[str, float],
    latent_probability_mass: float,
    latent_prior_weight: float = 1.0,
) -> Tuple[Dict[str, float], float, DecisionState, float]:
    """
    Compute normalised posterior, distinguishability, and decision state.

    Returns: (posterior_dict, distinguishability, decision_state, entropy)
    """
    L_0 = latent_probability_mass * latent_prior_weight

    total = sum(likelihoods.values()) + L_0
    if total == 0.0:
        n = max(len(likelihoods), 1)
        posterior = {k: 1.0 / (n + 1) for k in likelihoods}
        posterior["LATENT_SOURCE"] = 1.0 / (n + 1)
        return posterior, 0.0, DecisionState.INCONCLUSIVE, 1.0

    posterior = {k: L / total for k, L in likelihoods.items()}
    posterior["LATENT_SOURCE"] = L_0 / total

    # Sort vessels only (exclude latent)
    sorted_vessels = sorted(
        [(k, v) for k, v in posterior.items() if k != "LATENT_SOURCE"],
        key=lambda x: x[1], reverse=True
    )

    distinguishability = 0.0
    top_gap = 0.0

    if len(sorted_vessels) >= 2:
        p1 = sorted_vessels[0][1]
        p2 = sorted_vessels[1][1]
        top_gap = p1 - p2
        vessel_mass = 1.0 - posterior.get("LATENT_SOURCE", 0.0)
        if vessel_mass > 0:
            distinguishability = top_gap / vessel_mass
    elif len(sorted_vessels) == 1:
        distinguishability = 1.0
        top_gap = sorted_vessels[0][1]

    # Normalised entropy over all posterior entries
    valid_p = np.array([p for p in posterior.values() if p > 0])
    if len(valid_p) > 1:
        entropy = float(-np.sum(valid_p * np.log(valid_p)) / np.log(len(posterior)))
    else:
        entropy = 0.0

    # Clamp entropy to [0, 1] for the contract
    entropy = max(0.0, min(1.0, entropy))
    distinguishability = max(0.0, min(1.0, distinguishability))

    # Decision state
    if posterior.get("LATENT_SOURCE", 0) > 0.5:
        decision = DecisionState.LATENT_SOURCE
    elif entropy > 0.9:
        decision = DecisionState.INCONCLUSIVE
    elif distinguishability < 0.1:
        decision = DecisionState.NOT_DISTINGUISHABLE
    elif top_gap > 0.15:
        decision = DecisionState.STRONG_LEAD
    else:
        decision = DecisionState.WEAK_LEAD

    return posterior, distinguishability, decision, entropy
