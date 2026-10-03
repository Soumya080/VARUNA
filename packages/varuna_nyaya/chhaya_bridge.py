"""Additive CHHAYA v2 -> NYAYA bridge (Phase 7 handoff consumption).

Does NOT modify prior.py / likelihoods.py / posterior.py / scorer.py /
validity_gate.py / any other existing NYAYA file. NYAYA's existing Bayesian
machinery is untouched by this module.

Per `docs/research/VARUNA_INTELLIGENCE_SPEC.md` (CHHAYA v2 design): the
long-term direction is widening NYAYA's `SourceHypothesis` space with a real
likelihood term fed by CHHAYA's dark-contact evidence, not letting CHHAYA
compute its own competing posterior. This module is the honest, minimal
first step toward that: it translates a `ChhayaEvidenceHandoff` into a small,
bounded, documented prior NUDGE — not a posterior, not a rank, not a
decision. CHHAYA MUST NOT become the final attribution engine: nothing here
outputs a `DecisionState`, a `CandidateScore`, or an `AttributionResultV2`.
"""
from __future__ import annotations

from dataclasses import dataclass

# Small and documented, not fitted against any dataset — this is a
# placeholder-strength nudge specifically because CHHAYA v2's own detector
# (classical CFAR) is itself uncalibrated; a nudge weight larger than this
# would overstate confidence in evidence that is honestly RELATIVE_PLAUSIBILITY,
# not a calibrated probability. Revisit only alongside real outcome data
# (see VARUNA_INTELLIGENCE_SPEC.md's SMRITI v2 section).
DARK_CONTACT_PRIOR_WEIGHT = 0.15


@dataclass
class DarkContactEvidence:
    case_id: str
    scene_id: str
    supported: bool                        # True only for a POSSIBLE_DARK_VESSEL outcome
    top_candidate_plausibility: float | None
    prior_nudge: float                     # bounded [0, DARK_CONTACT_PRIOR_WEIGHT]
    explanation: str


def dark_contact_prior_contribution(handoff) -> DarkContactEvidence:
    """`handoff`: a `varuna_chhaya.v2.nyaya_handoff.ChhayaEvidenceHandoff`.
    Typed loosely (duck-typed, not imported at module scope) so this NYAYA
    module never has a hard import-time dependency on `varuna_chhaya` —
    NYAYA must be usable standalone even if CHHAYA v2 is absent."""
    from varuna_chhaya.v2.outcomes import ChhayaOutcome  # local import by design, see docstring

    if handoff.outcome != ChhayaOutcome.POSSIBLE_DARK_VESSEL or not handoff.candidates:
        return DarkContactEvidence(
            case_id=handoff.case_id, scene_id=handoff.scene_id, supported=False,
            top_candidate_plausibility=None, prior_nudge=0.0,
            explanation=f"CHHAYA outcome={handoff.outcome.value} does not support a dark-contact prior contribution",
        )

    top = min(handoff.candidates, key=lambda c: c.rank)
    clipped = max(0.0, min(1.0, top.relative_plausibility))
    nudge = DARK_CONTACT_PRIOR_WEIGHT * clipped
    return DarkContactEvidence(
        case_id=handoff.case_id, scene_id=handoff.scene_id, supported=True,
        top_candidate_plausibility=top.relative_plausibility, prior_nudge=nudge,
        explanation=(
            f"top CHHAYA candidate (rank 1, relative_plausibility={top.relative_plausibility:.2f}) "
            f"is a supported dark contact -> bounded prior nudge {nudge:.3f}. Documented input for "
            f"a future SourceHypothesis.DARK_CONTACT likelihood term "
            f"(docs/research/VARUNA_INTELLIGENCE_SPEC.md) — NOT itself a posterior or a decision."
        ),
    )
