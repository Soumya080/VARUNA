"""
CHHAYA v0.1 — source-hypothesis engine.

WHAT THIS IS
------------
A transparent, deterministic Bayesian engine over **declared** likelihood
ratios. Every weight below is an expert-declared prior written by hand in this
file, with a stated justification. **Nothing here is learned, fitted, trained,
or calibrated against outcome data.** `HypothesisMethod.DECLARED_LIKELIHOOD_RATIO`
is stamped on every output so no downstream consumer can render this as a model
result.

WHY A DECLARED-PRIOR ENGINE AND NOT A MODEL
-------------------------------------------
There is no labelled source-class dataset in this repository. Training a
classifier would require inventing labels, and a model fitted on invented
labels is strictly worse than an explicit rule set: the rule set is at least
auditable and its assumptions are visible in the diff. When a labelled corpus
exists, `SourceHypothesisEngine` can be swapped behind the same
`SourceHypothesisEnvelope` contract without touching any caller — that is the
point of putting the contract in `varuna_contracts` rather than here.

CALIBRATION STATUS: UNCALIBRATED. The posteriors are internally consistent
(they are a genuine Bayesian update over the declared LRs) but they have never
been checked against real outcomes, so they express *relative* plausibility
under the stated assumptions, not empirical frequencies. This is recorded in
`methodology_note` on every envelope rather than only in this docstring.
"""
from __future__ import annotations

import math

from varuna_contracts.evidence import (
    EvidenceEnvelope, EvidenceMode, Provenance,
)
from varuna_contracts.source_hypothesis import (
    FactorContribution, HypothesisMethod, SourceClass, SourceHypothesis,
    SourceHypothesisEnvelope,
)

ENGINE_VERSION = "chhaya-v0.1-declared-lr"

# --------------------------------------------------------------------------
# Declared priors. These are base rates over source CLASS given that a slick
# has been detected at all -- not detection rates.
#
# Justification: global spill-attribution literature consistently finds
# operational vessel discharge to be the dominant identifiable class in
# routine maritime surveillance, with natural seepage dominant only in
# specific geological basins (notably the Gulf of Mexico -- see the MC20
# regional-adjustment note below). These are order-of-magnitude judgements
# chosen to be defensible and legible, NOT measured frequencies.
# --------------------------------------------------------------------------
BASE_PRIORS: dict[SourceClass, float] = {
    SourceClass.VESSEL_ASSOCIATED: 0.40,
    SourceClass.NATURAL_SEEP: 0.20,
    SourceClass.COASTAL: 0.15,
    SourceClass.OTHER_ANTHROPOGENIC: 0.15,
    SourceClass.UNKNOWN: 0.10,
}

# Declared log-likelihood ratios, in natural log units. Magnitudes are chosen
# on a coarse, deliberately blunt scale so that no single factor can dominate:
#   ln(3.0) ~ 1.10  strong support
#   ln(2.0) ~ 0.69  moderate support
#   ln(1.4) ~ 0.34  weak support
# and their negatives for opposition. Finer granularity would imply a
# precision this engine does not have.
_STRONG, _MODERATE, _WEAK = math.log(3.0), math.log(2.0), math.log(1.4)

# Distance (km) inside which an AIS track is treated as co-located with the
# slick. Reuses the AIS join's own spatial convention rather than inventing a
# second radius; see varuna_geospatial/ais_join.py.
VESSEL_COLOCATION_KM = 10.0

# A slick whose elongation exceeds this is linear enough to be consistent with
# a moving discharge rather than a point release. Declared, not fitted.
LINEAR_ELONGATION = 3.0

# Distance (km) from shore below which coastal sources become plausible.
COASTAL_PROXIMITY_KM = 15.0


class SourceHypothesisEngine:
    """
    Evidence in, ranked hypotheses out. Stateless and deterministic: the same
    inputs always produce the same posteriors, which is what makes replay
    reproducible.
    """

    def __init__(self, *, priors: dict[SourceClass, float] | None = None,
                 region_note: str | None = None) -> None:
        self._priors = dict(priors or BASE_PRIORS)
        total = sum(self._priors.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"priors must sum to 1.0, got {total}")
        self._region_note = region_note

    # ------------------------------------------------------------- scoring

    def assess(
        self,
        *,
        case_id: str,
        parent_envelope: EvidenceEnvelope,
        detection_present: bool,
        elongation: float | None = None,
        area_km2: float | None = None,
        nearest_vessel_km: float | None = None,
        nearest_vessel_temporally_matched: bool = False,
        n_ais_tracks: int | None = None,
        distance_to_shore_km: float | None = None,
        in_known_seep_basin: bool = False,
        wind_speed_ms: float | None = None,
        phi_available: bool = False,
        phi_converged: bool | None = None,
        prior_cases_same_corridor: int = 0,
        contradictions: list[str] | None = None,
        evidence_ids: dict[str, list[str]] | None = None,
    ) -> SourceHypothesisEnvelope:
        """
        Run the update. Every argument is optional-by-absence: a factor whose
        evidence is missing contributes NOTHING rather than a default value,
        so an unobserved quantity can never silently push a hypothesis.

        M6 fix (docs/product/HONESTY_LEDGER.md #8): `evidence_ids` used to be
        a flat `list[str]` — every case evidence id, regardless of relevance
        — stamped onto EVERY `FactorContribution`, so e.g. `no_ais_coverage`
        carried forecast and decision evidence ids that have nothing to do
        with AIS. It is now a mapping keyed by input KIND ("ais",
        "detection", "phi", "smriti", "region", "contradictions"); each
        `add()` call below names which kind(s) actually back that factor, so
        a factor only ever carries the evidence that produced it. Callers
        that still pass a flat list get it treated as a single "general"
        bucket rather than crashing, but the intended contract is the dict.
        """
        contradictions = list(contradictions or [])
        if evidence_ids is None:
            evidence_ids_by_kind: dict[str, list[str]] = {}
        elif isinstance(evidence_ids, dict):
            evidence_ids_by_kind = {k: list(v) for k, v in evidence_ids.items()}
        else:
            # Backward-compat: a flat list (the old contract) is evidence of
            # unknown, unbucketed kind. Never split across factors as if it
            # were relevant to all of them.
            evidence_ids_by_kind = {"general": list(evidence_ids)}
        all_evidence_ids = sorted({eid for ids in evidence_ids_by_kind.values() for eid in ids})

        if not detection_present:
            return self._insufficient(
                case_id, parent_envelope, all_evidence_ids, contradictions,
                reason=("No detection evidence exists for this case, so there is "
                        "no slick whose source could be hypothesised."),
            )

        support: dict[SourceClass, list[FactorContribution]] = {c: [] for c in self._priors}
        against: dict[SourceClass, list[FactorContribution]] = {c: [] for c in self._priors}

        def add(cls: SourceClass, factor: str, detail: str, llr: float,
                measured: bool = True, source: str = "general") -> None:
            fc = FactorContribution(factor=factor, detail=detail,
                                    log_likelihood_ratio=llr,
                                    evidence_ids=evidence_ids_by_kind.get(source, []),
                                    measured=measured)
            (support if llr > 0 else against)[cls].append(fc)

        # ---- Vessel proximity (the single strongest available signal) ----
        if nearest_vessel_km is not None:
            if nearest_vessel_km <= VESSEL_COLOCATION_KM:
                if nearest_vessel_temporally_matched:
                    add(SourceClass.VESSEL_ASSOCIATED, "vessel_colocation",
                        f"A temporally-matched AIS track passes {nearest_vessel_km:.1f} km "
                        f"from the slick (<= {VESSEL_COLOCATION_KM} km).", _STRONG, source="ais")
                    add(SourceClass.NATURAL_SEEP, "vessel_colocation",
                        "A co-located, time-matched vessel is a competing explanation "
                        "that seepage does not require.", -_MODERATE, source="ais")
                else:
                    # Spatial proximity WITHOUT a temporal match is weak. This
                    # mirrors the AIS join's own rule that spatial candidacy is
                    # never promoted into temporal evidence.
                    add(SourceClass.VESSEL_ASSOCIATED, "vessel_spatial_only",
                        f"An AIS track passes {nearest_vessel_km:.1f} km away but is NOT "
                        "temporally matched; proximity alone is not co-occurrence.", _WEAK, source="ais")
            else:
                add(SourceClass.VESSEL_ASSOCIATED, "no_vessel_nearby",
                    f"Nearest AIS track is {nearest_vessel_km:.1f} km away "
                    f"(> {VESSEL_COLOCATION_KM} km).", -_MODERATE, source="ais")
        elif n_ais_tracks == 0:
            # NOTE the `is not None` contract on n_ais_tracks: `None` means
            # "AIS was never consulted" and contributes NOTHING, while `0`
            # means "AIS was consulted and returned no tracks". Defaulting
            # this to 0 previously made an unsupplied argument look like a
            # measurement -- a parameter default silently becoming evidence,
            # which is precisely the fabrication this engine must not commit.
            #
            # Even when genuinely measured, absence of AIS is NOT evidence of
            # absence of vessels -- dark vessels exist. It weakens the vessel
            # hypothesis only slightly, and is flagged as an inference.
            add(SourceClass.VESSEL_ASSOCIATED, "no_ais_coverage",
                "No AIS tracks were available. This is weak evidence at best: a "
                "dark vessel would also produce no AIS.", -_WEAK, measured=False, source="ais")

        # ---- Morphology ----
        if elongation is not None:
            if elongation >= LINEAR_ELONGATION:
                add(SourceClass.VESSEL_ASSOCIATED, "linear_morphology",
                    f"Elongation {elongation:.1f} >= {LINEAR_ELONGATION} is consistent "
                    "with discharge from a moving platform.", _MODERATE, source="detection")
                add(SourceClass.NATURAL_SEEP, "linear_morphology",
                    "Seeps typically surface as point-anchored or patchy features, "
                    "less often as long linear streaks.", -_WEAK, source="detection")
            else:
                add(SourceClass.NATURAL_SEEP, "compact_morphology",
                    f"Elongation {elongation:.1f} < {LINEAR_ELONGATION} is more "
                    "consistent with a fixed point source.", _WEAK, source="detection")

        # ---- Geography ----
        if distance_to_shore_km is not None:
            if distance_to_shore_km <= COASTAL_PROXIMITY_KM:
                add(SourceClass.COASTAL, "shore_proximity",
                    f"Slick is {distance_to_shore_km:.1f} km from shore "
                    f"(<= {COASTAL_PROXIMITY_KM} km), within range of land-based outfall.",
                    _MODERATE, source="region")
            else:
                add(SourceClass.COASTAL, "offshore",
                    f"Slick is {distance_to_shore_km:.1f} km offshore, beyond plausible "
                    "land-based outfall.", -_STRONG, source="region")

        if in_known_seep_basin:
            add(SourceClass.NATURAL_SEEP, "known_seep_basin",
                "Location falls in a basin with documented natural hydrocarbon seepage.",
                _STRONG, source="region")
            add(SourceClass.OTHER_ANTHROPOGENIC, "known_seep_basin",
                "A documented natural source is a competing explanation.", -_WEAK, source="region")

        # ---- Environment ----
        if wind_speed_ms is not None and wind_speed_ms < 3.0:
            # Low wind is a DETECTION-QUALITY caveat, not source evidence. It is
            # recorded against UNKNOWN so it visibly widens uncertainty instead
            # of nudging a substantive class.
            add(SourceClass.UNKNOWN, "low_wind_lookalike_risk",
                f"Wind {wind_speed_ms:.1f} m/s < 3.0 m/s: low-wind glassy water is a "
                "known look-alike regime, so the detection itself is less trustworthy.",
                _MODERATE, source="detection")

        # ---- Repetition (SMRITI) ----
        if prior_cases_same_corridor >= 3:
            add(SourceClass.NATURAL_SEEP, "recurrence",
                f"{prior_cases_same_corridor} prior cases in this corridor; persistent "
                "recurrence at one location favours a fixed, continuous source.",
                _MODERATE, source="smriti")
            add(SourceClass.VESSEL_ASSOCIATED, "recurrence",
                "Repeated slicks at a fixed point are less consistent with transiting "
                "vessels, which differ case to case.", -_WEAK, source="smriti")

        # ---- Reconstruction quality ----
        if phi_available and phi_converged is False:
            add(SourceClass.UNKNOWN, "phi_not_converged",
                "Backward reconstruction did not converge, so origin-based reasoning "
                "cannot discriminate between source classes.", _MODERATE, source="phi")

        # ---- Contradictions widen uncertainty; they never pick a winner ----
        for note in contradictions:
            add(SourceClass.UNKNOWN, "contradiction",
                f"Unresolved contradiction in the evidence: {note}", _WEAK, source="contradictions")

        posteriors = self._update(support, against)
        hypotheses = [
            SourceHypothesis(
                source_class=cls,
                posterior=posteriors[cls],
                prior=self._priors[cls],
                supporting=support[cls],
                contradicting=against[cls],
                rationale=self._rationale(cls, support[cls], against[cls],
                                          self._priors[cls], posteriors[cls]),
            )
            for cls in sorted(self._priors, key=lambda c: posteriors[c], reverse=True)
        ]

        # Count DISTINCT factor names, not contributions: a single input can
        # legitimately emit two contributions (support for one class, opposition
        # to another), and counting those as two independent signals would
        # overstate how much evidence the case actually has.
        n_factors = len({f.factor
                         for bucket in (support, against)
                         for fcs in bucket.values()
                         for f in fcs})
        return SourceHypothesisEnvelope(
            case_id=case_id,
            hypotheses=hypotheses,
            method=HypothesisMethod.DECLARED_LIKELIHOOD_RATIO,
            methodology_note=self._methodology_note(n_factors),
            engine_version=ENGINE_VERSION,
            uncertainty_note=(
                None if n_factors >= 2 else
                "Only one evidential factor was available; posteriors are close to "
                "the declared priors and should not be read as discriminating."
            ),
            insufficient_evidence=n_factors == 0,
            contradictions=contradictions,
            evidence_ids_considered=all_evidence_ids,
            envelope=parent_envelope.derive(
                artifact_id=f"chhaya-{case_id}",
                produced_by="chhaya.hypothesis_engine",
                model_version=ENGINE_VERSION,
            ),
        )

    # ------------------------------------------------------------ internals

    def _update(self, support: dict[SourceClass, list[FactorContribution]],
                against: dict[SourceClass, list[FactorContribution]]
                ) -> dict[SourceClass, float]:
        """Bayesian update in log space, then normalise. No clipping games."""
        unnormalised: dict[SourceClass, float] = {}
        for cls, prior in self._priors.items():
            llr = sum(f.log_likelihood_ratio for f in support[cls])
            llr += sum(f.log_likelihood_ratio for f in against[cls])
            unnormalised[cls] = prior * math.exp(llr)
        total = sum(unnormalised.values())
        if total <= 0:  # unreachable with positive priors; fail loudly if not
            raise ArithmeticError("posterior mass collapsed to zero")
        return {cls: v / total for cls, v in unnormalised.items()}

    def _rationale(self, cls: SourceClass, sup: list[FactorContribution],
                   con: list[FactorContribution], prior: float, post: float) -> str:
        direction = ("raised" if post > prior + 1e-9
                     else "lowered" if post < prior - 1e-9 else "unchanged from")
        if not sup and not con:
            return (f"No evidence bore on {cls.value}; posterior {post:.2f} reflects the "
                    f"declared prior {prior:.2f} only.")
        parts = [f"{f.factor}(+{f.log_likelihood_ratio:.2f})" for f in sup]
        parts += [f"{f.factor}({f.log_likelihood_ratio:.2f})" for f in con]
        return (f"Prior {prior:.2f} {direction} {post:.2f} by: " + ", ".join(parts) + ".")

    def _methodology_note(self, n_factors: int) -> str:
        base = (
            f"CHHAYA {ENGINE_VERSION}: deterministic Bayesian update over "
            f"{n_factors} declared likelihood ratio(s). NOT a trained or learned "
            "model — every weight is an expert-declared constant in "
            "packages/varuna_chhaya/hypothesis_engine.py with a written "
            "justification. UNCALIBRATED: posteriors are internally consistent "
            "but have never been validated against outcome data, so they express "
            "relative plausibility under the stated assumptions, not empirical "
            "frequencies."
        )
        return f"{base} Regional prior note: {self._region_note}" if self._region_note else base

    def _insufficient(self, case_id: str, parent: EvidenceEnvelope,
                      evidence_ids: list[str], contradictions: list[str],
                      reason: str) -> SourceHypothesisEnvelope:
        """Honest 'we cannot say' — UNKNOWN at 1.0, not a flat spread."""
        hyps = [SourceHypothesis(
            source_class=SourceClass.UNKNOWN, posterior=1.0,
            prior=self._priors[SourceClass.UNKNOWN],
            supporting=[], contradicting=[], rationale=reason,
        )]
        hyps += [SourceHypothesis(source_class=c, posterior=0.0, prior=self._priors[c],
                                  supporting=[], contradicting=[],
                                  rationale="Not assessed: " + reason)
                 for c in self._priors if c is not SourceClass.UNKNOWN]
        return SourceHypothesisEnvelope(
            case_id=case_id, hypotheses=hyps,
            method=HypothesisMethod.DECLARED_LIKELIHOOD_RATIO,
            methodology_note=self._methodology_note(0),
            engine_version=ENGINE_VERSION,
            uncertainty_note=reason, insufficient_evidence=True,
            contradictions=contradictions, evidence_ids_considered=evidence_ids,
            envelope=parent.derive(artifact_id=f"chhaya-{case_id}",
                                   produced_by="chhaya.hypothesis_engine",
                                   model_version=ENGINE_VERSION),
        )


# The Gulf of Mexico (MC20's basin) has documented, persistent natural seepage
# at a rate that makes seep-vs-vessel genuinely ambiguous there. Offered as an
# explicit, named regional adjustment a caller must opt into -- not applied
# silently by geography sniffing.
GULF_OF_MEXICO_PRIORS: dict[SourceClass, float] = {
    SourceClass.VESSEL_ASSOCIATED: 0.30,
    SourceClass.NATURAL_SEEP: 0.35,
    SourceClass.COASTAL: 0.10,
    SourceClass.OTHER_ANTHROPOGENIC: 0.15,
    SourceClass.UNKNOWN: 0.10,
}
