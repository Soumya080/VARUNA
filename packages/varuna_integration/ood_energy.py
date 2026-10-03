"""
Energy-score OOD signal (Phase 4B of the VARUNA_PRODUCT_READY hardening
session).

Built from `scripts/build_ood_energy_reference.py` against 200 deterministically
sampled NETRA-GOLD-v0.2 val tiles (seed=42) and the frozen v0.2 checkpoint. No
training, no labeled OOD corpus, no checkpoint modification. See
`data/ood_energy_reference_v0_1.json` for the full provenance record.

This is a genuinely different signal from the pre-existing
`assess_ood_from_detection()` heuristic in `varuna_integration.intelligence`:

- The existing heuristic reads `max_probability` — the winning class's
  post-softmax confidence for OIL specifically. A model that is confidently
  NEGATIVE for oil on a scene it recognizes well produces the same low number
  as a model looking at something genuinely alien to it.
- The energy score reads the pre-softmax logits across ALL classes. It answers
  "does this input's internal representation resemble what the model was
  trained on," independent of which class wins.

These two signals CAN disagree, and when they do, that disagreement is itself
the honest finding — not something to resolve by picking whichever one
confirms an existing narrative. `combine_ood_signals()` below reports both
explicitly rather than silently preferring one.

NOT A CALIBRATED OOD DETECTOR: no labeled out-of-domain corpus was used to
tune a decision boundary, and no false-positive/false-negative rate has been
measured. This is a reference-distribution comparison, presented as such.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_REFERENCE_PATH = Path(__file__).parent / "data" / "ood_energy_reference_v0_1.json"
_reference_cache: dict | None = None


def load_reference() -> dict:
    global _reference_cache
    if _reference_cache is None:
        if not _REFERENCE_PATH.exists():
            raise FileNotFoundError(
                f"OOD energy reference not found at {_REFERENCE_PATH}. "
                "Run scripts/build_ood_energy_reference.py to build it."
            )
        _reference_cache = json.loads(_REFERENCE_PATH.read_text())
    return _reference_cache


@dataclass(frozen=True)
class EnergySignal:
    """One tile-sweep's energy-score reading, positioned against the reference."""
    min_energy: float
    percentile_rank_low: int   # highest reference percentile <= min_energy
    percentile_rank_high: int  # lowest reference percentile >= min_energy
    reference_version: str
    familiar: bool  # True if within [p5, p95] of the in-domain reference


def score_energy(min_energy: float | None) -> EnergySignal | None:
    """Position a tile-sweep's `min_energy` against the reference distribution.

    Returns None if `min_energy` is unavailable (e.g. a provider that does not
    expose it, such as the simulated provider).
    """
    if min_energy is None:
        return None
    ref = load_reference()
    pct = {int(k): v for k, v in ref["percentiles"].items()}
    ordered = sorted(pct.items())
    low, high = ordered[0][0], ordered[-1][0]
    for p, value in ordered:
        if min_energy >= value:
            low = p
        if min_energy <= value:
            high = p
            break
    else:
        high = ordered[-1][0]
    familiar = pct[5] <= min_energy <= pct[95]
    return EnergySignal(
        min_energy=min_energy, percentile_rank_low=low, percentile_rank_high=high,
        reference_version=ref["reference_version"], familiar=familiar,
    )


def combine_ood_signals(
    *, max_probability: float | None, decision_threshold: float | None,
    min_energy: float | None,
) -> tuple[str, str]:
    """
    Combine the class-probability heuristic and the energy-score signal into
    one (ood_risk_str, rationale) pair. `ood_risk_str` is one of
    "in_domain" | "borderline" | "out_of_domain" | "unknown" — the caller maps
    this onto `OODRisk`.

    Deliberately does not collapse a disagreement between the two signals into
    a single confident verdict — the rationale states both readings when they
    conflict, which is the honest representation of what is actually known.
    """
    energy = score_energy(min_energy)

    if max_probability is None and energy is None:
        return "unknown", (
            "Neither the class-probability heuristic nor the energy-score "
            "signal has data for this run; no OOD judgement is possible."
        )

    prob_verdict: str | None = None
    prob_note = ""
    if max_probability is not None and decision_threshold:
        if max_probability < decision_threshold * 0.01:
            prob_verdict = "out_of_domain"
            prob_note = (
                f"Peak oil-class probability {max_probability:.3g} is more than two "
                f"orders of magnitude below the decision threshold "
                f"{decision_threshold:.3g}."
            )
        elif max_probability < decision_threshold:
            prob_verdict = "borderline"
            prob_note = (
                f"Peak oil-class probability {max_probability:.3g} is below the "
                f"decision threshold {decision_threshold:.3g} but not extremely so."
            )
        else:
            prob_verdict = "in_domain"
            prob_note = (
                f"Peak oil-class probability {max_probability:.3g} reached the "
                f"decision threshold {decision_threshold:.3g}."
            )
    prob_note += " HEURISTIC: reflects only the oil-class probability, not overall representation familiarity."

    if energy is None:
        return (prob_verdict or "unknown"), (
            prob_note + " No energy-score signal was available for this run."
        )

    energy_note = (
        f"Energy-score signal (reference {energy.reference_version}, "
        f"NOT a calibrated OOD detector): this tile-sweep's most in-domain-"
        f"confident pixel has energy {energy.min_energy:.3g}, landing between "
        f"the reference's p{energy.percentile_rank_low} and "
        f"p{energy.percentile_rank_high} — "
        + ("within the typical [p5, p95] range of NETRA-GOLD-v0.2 val tiles, "
           "i.e. the underlying representation does NOT look unfamiliar to the model."
           if energy.familiar else
           "outside the typical [p5, p95] range of NETRA-GOLD-v0.2 val tiles, "
           "i.e. the underlying representation looks unusual to the model.")
    )

    if prob_verdict is None:
        return ("in_domain" if energy.familiar else "out_of_domain"), energy_note

    energy_verdict = "in_domain" if energy.familiar else "out_of_domain"
    if prob_verdict == energy_verdict or (prob_verdict == "borderline" and energy.familiar):
        return prob_verdict, prob_note + " " + energy_note

    # Genuine disagreement: report both, do not silently prefer one.
    return "borderline", (
        prob_note + " " + energy_note +
        " These two signals DISAGREE: the class-probability heuristic suggests "
        f"'{prob_verdict}' while the energy-score signal suggests "
        f"'{energy_verdict}'. Reported as borderline pending a resolution that "
        "neither signal alone can provide -- this is the honest state of the "
        "evidence, not an average of the two readings."
    )
