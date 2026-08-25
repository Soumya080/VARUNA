"""
VARUNA GRID — Posterior normalisation and decision state logic.

Accepts density-based likelihoods and proper Bayesian priors.
The latent prior is a probability (not a scaling hack).
"""
import numpy as np
from typing import Dict, Tuple
from varuna_contracts.decision import DecisionState


def compute_posterior(
    densities: Dict[str, float],
    latent_density: float,
    priors: Dict[str, float],
    latent_prior: float = 0.5,
) -> Tuple[Dict[str, float], float, DecisionState, float]:
    """
    Compute normalised posterior via Bayes theorem with density likelihoods.

    P(H_k | E) = rho_k * pi_k / Z
    P(H_0 | E) = rho_0 * pi_0 / Z

    Args:
        densities: {mmsi: rho_k} — per-vessel Phi density
        latent_density: rho_0 — background Phi density
        priors: {mmsi: weight} — unnormalized vessel priors
        latent_prior: pi_0 — prior probability of latent source [0, 1]

    Returns: (posterior_dict, distinguishability, decision_state, entropy)
    """
    # 1. Normalize priors: vessel priors share (1 - latent_prior)
    latent_prior = max(0.001, min(0.999, latent_prior))
    vessel_prior_budget = 1.0 - latent_prior

    total_vessel_prior = sum(priors.values())
    if total_vessel_prior > 0:
        pi_k = {k: vessel_prior_budget * v / total_vessel_prior
                for k, v in priors.items()}
    else:
        n = max(len(densities), 1)
        pi_k = {k: vessel_prior_budget / n for k in densities}
    pi_0 = latent_prior

    # 2. Unnormalized posteriors
    unnorm = {k: densities.get(k, 0.0) * pi_k.get(k, 0.0) for k in densities}
    unnorm_latent = latent_density * pi_0

    # 3. Normalize
    Z = sum(unnorm.values()) + unnorm_latent
    if Z == 0.0:
        n = max(len(densities), 1)
        posterior = {k: 1.0 / (n + 1) for k in densities}
        posterior["LATENT_SOURCE"] = 1.0 / (n + 1)
        return posterior, 0.0, DecisionState.INCONCLUSIVE, 1.0

    posterior = {k: v / Z for k, v in unnorm.items()}
    posterior["LATENT_SOURCE"] = unnorm_latent / Z

    # 4. Distinguishability
    sorted_vessels = sorted(
        [(k, v) for k, v in posterior.items() if k != "LATENT_SOURCE"],
        key=lambda x: x[1], reverse=True,
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

    # 5. Entropy
    valid_p = np.array([p for p in posterior.values() if p > 0])
    if len(valid_p) > 1:
        entropy = float(-np.sum(valid_p * np.log(valid_p)) / np.log(len(posterior)))
    else:
        entropy = 0.0
    entropy = max(0.0, min(1.0, entropy))
    distinguishability = max(0.0, min(1.0, distinguishability))

    # 6. Decision state
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
