# VARUNA GRID v2 — Intelligence Specification

**Date:** 2026-09-02
**Audience:** the Integration/Product session. This document defines implementation-ready
contracts; it does not implement them. Every contract here is designed to extend
`packages/varuna_contracts` and the real, already-implemented patterns documented in
`VARUNA_INTELLIGENCE_RESEARCH_MAP.md` (`EvidenceEnvelope.derive()`, `ValidityState`,
NYAYA's density-likelihood pattern, the Validity Gate's fail-closed check pattern) — nothing
here proposes a parallel type system.

**Design stance (per governing brief §20):** simple, measurable, interpretable,
deterministic, reproducible, before anything learned. Every contract below has an explicit
"deterministic today / learnable later" note.

---

## Detection Evidence (NETRA output contract)

**Status today:** NETRA emits raw logits/probabilities; whether these are already wrapped in
`EvidenceEnvelope` with a populated `UncertaintyBlock`/`QualityMetrics.ood_score` was not
independently re-verified this pass (research map §7, item 2) — this is the first thing
Integration should check before building anything below.

**Proposed contract** (extends, does not replace, `EnvelopedArtifact`):

```python
class DetectionEvidence(EnvelopedArtifact):
    scene_id: str
    tile_id: str | None
    oil_probability_map_ref: str        # PRAMAN artifact ref, never the raw array inline
    max_probability: float
    predicted_foreground_fraction: float
    threshold_used: float               # the frozen 0.806, explicit, never implicit
    ood_score: float                    # real, from OODDetector v2 below — NOT the stub
    ood_flag: bool                      # ood_score above a calibrated cutoff
    connected_components: int | None
```

`envelope.quality.ood_score` MUST be populated from a real `OODDetector`
(`packages/varuna_netra/ood.py` today returns `np.random.uniform` — dead on arrival for any
downstream consumer that trusts it). Minimum viable real version, no training required:
- **Energy score** or **max-softmax-probability distance from the training-set distribution**
  computed once, offline, over the v0.2 training/holdout split to get a reference
  distribution (mean/std of max-logit energy), then at inference compare the new scene's
  energy to that reference. This is a closed-form, no-training, `[cheap-experiment]`-tier
  fix — see roadmap.
- Do **not** ship a Mahalanobis-on-features detector as v1; it requires a covariance
  estimate over a feature extractor that isn't currently instrumented for feature capture.
  That's a `[moderate-compute]` v2, not blocking.

`ood_flag` threshold: calibrate against the **already-known** two reference points — v0.2 on
CALM-GRD-HOLDOUT (in-domain, should not flag) and v0.2 on MC20 (known OOD, must flag,
max_probability≈3e-6 already measured). This is a 2-point calibration, not a sweep; do not
over-fit a threshold to two points — treat it as provisional and re-check against every new
external case as it arrives.

---

## Evidence Ledger

**Status today:** does not exist as a reasoning surface. PRAMAN is a registry
(`register_artifact`/`get`/`list_by_case`), not a ledger that anyone queries for "what do we
currently believe, and why."

**Proposed contract** — a **read-side view**, not new storage:

```python
class EvidenceLedger:
    """Read-only aggregation over PRAMAN artifacts + their EvidenceEnvelopes for one case.
    Does not store anything PRAMAN doesn't already store. Answers questions PRAMAN's
    flat artifact list cannot answer directly."""

    def __init__(self, praman: PramanService, case_id: str): ...

    def current_belief_state(self) -> list[EvidenceEnvelope]:
        """Latest envelope per (produced_by, artifact_type) — supersession by created_at,
        never by silently dropping an older, conflicting one; superseded envelopes stay
        queryable via history()."""

    def contradictions(self) -> list[tuple[EvidenceEnvelope, EvidenceEnvelope]]:
        """Pairs of live envelopes whose AnomalyFlag.CROSS_SOURCE_CONFLICT /
        CROSS_MODULE_CONTRADICTION was set, or whose derived quantities disagree beyond a
        documented tolerance (e.g. NYAYA's top posterior vessel vs. CHHAYA's dark-contact
        flag disagreeing on whether *any* vessel is implicated)."""

    def provenance_chain(self, artifact_id: str) -> list[EvidenceEnvelope]:
        """Walk parent_artifact_ids back to raw sources. Already fully supported by the
        existing schema (`parent_artifact_ids`) — this method is pure traversal, no new
        field needed."""

    def weakest_link(self) -> EvidenceEnvelope:
        """The envelope with the worst rank(trust, validity, degradation) in the case —
        i.e. exactly what `derive()` would compute if everything were combined right now.
        This IS the ledger's headline answer to 'what is currently limiting our confidence.'"""
```

This is deliberately a thin class over data that already exists — it should be a `[NOW,
no-compute]` build, not a research project. Its value is entirely in making the existing
provenance graph *queryable* rather than requiring every consumer to re-derive it.

---

## CHHAYA v2 — extend NYAYA's hypothesis space, don't duplicate it

Per research-map §6, the recommended design does **not** give CHHAYA its own Bayesian
engine. Instead:

1. **CHHAYA keeps its current, narrower job**: SAR-vs-AIS radar contact matching, producing
   `DarkVesselDetection` + `LatentFinding` (coverage sufficiency). This is real, useful, and
   correctly scoped — do not scope-creep it.
2. **NYAYA's hypothesis space is extended** from `{named_vessel_k..., latent}` to:
   ```python
   class SourceHypothesis(StrEnum):
       VESSEL_ASSOCIATED = "vessel_associated"    # existing per-MMSI density likelihood
       DARK_CONTACT = "dark_contact"               # NEW: fed by CHHAYA's DarkVesselDetection
       COASTAL = "coastal"                         # NEW: proximity to a known outfall/port
       NATURAL_SEEP = "natural_seep"                # NEW: proximity to a known seep corridor (SMRITI)
       OTHER_ANTHROPOGENIC = "other_anthropogenic"  # NEW: catch-all, not latent
       UNKNOWN = "unknown"                          # existing "latent" bucket, renamed for clarity
   ```
3. Each new hypothesis needs exactly one thing NYAYA doesn't yet have for it: a
   **likelihood term** comparable to the existing `rho_k` density likelihood. Concrete,
   deterministic v1 formulations (no learning required):
   - `DARK_CONTACT`: likelihood ∝ 1 if a `DarkVesselDetection` exists within the Φ corridor
     near the slick origin and within a plausible time window, else a small constant
     (never zero — CHHAYA's coverage can be insufficient, which must degrade this term's
     `influence_weight`, not silently zero it out).
   - `COASTAL`: likelihood ∝ inverse-distance to nearest known permitted-outfall/port point
     (static reference table — this is genuinely no-compute, just a lookup).
   - `NATURAL_SEEP`: likelihood ∝ SMRITI's `detect_corridors()` result for this region
     (currently always `[]` — this hypothesis's likelihood is legitimately near-zero until
     SMRITI v2 has real case history; it should default to a **flat, uninformative** prior
     contribution, not a fabricated number, exactly like the Validity Gate's treatment of a
     missing `SensitivityBlock`).
   - `OTHER_ANTHROPOGENIC` / `UNKNOWN`: the existing residual/latent treatment, unchanged.
4. **Fusion**: each new likelihood is combined with the existing ones via NYAYA's existing
   posterior machinery (`posterior.py`) — this is a matter of adding terms to an existing,
   validated combination, not inventing a new fusion rule. See "Evidence Fusion" below for
   the general principle this follows.
5. **Confidence, not just presence**: `MockChhayaProvider`'s hardcoded `confidence=0.6` must
   become a real `QualityMetrics.model_confidence` derived from the AIS-coverage fraction
   and proximity distance already computed in `coverage.py` — those numbers already exist in
   the function, they're just being discarded before the envelope is built. This is a
   `[no-compute]` fix.

**Learned CHHAYA (future):** once real dark-contact cases with confirmed outcomes exist
(via SMRITI v2's outcome memory), a learned classifier could replace the deterministic
proximity/coverage heuristic for the `DARK_CONTACT` likelihood term specifically — but it
should replace *one likelihood term*, not the whole hypothesis-fusion structure. That
structure (priors × likelihoods → posterior, gated by entropy/distinguishability) should
stay Bayesian and interpretable regardless of whether any individual term becomes learned.

---

## SMRITI v2

**Status today:** protocol + in-memory mock only (research map §5). This is a clean slate,
not a legacy system to migrate — design accordingly.

**Memory taxonomy** (per governing brief §7, mapped onto concrete stores):

| Kind | What | Store | Retrieval trigger |
|---|---|---|---|
| Working/session | Current case's own evidence so far | already `EvidenceLedger` above — not SMRITI's job | n/a |
| Episodic (case) | One row per closed case: region, environmental regime, NETRA behavior (ood_score, activation pattern), source hypothesis + posterior, final decision state, operator override if any | Postgres (already the domain-state store per ADR-0004) — **structured**, not a vector store | keyed lookup: region+time (already `query_history`'s signature), or by NETRA-behavior similarity (see below) |
| Semantic (corridor) | Aggregated recurrence corridors derived FROM episodic memory, not stored independently | Derived view over episodic table, recomputed, not hand-maintained | region bbox lookup (`detect_corridors`, currently stubbed to `[]`) |
| Failure memory | Cases where NETRA/CHHAYA/NYAYA/Validity Gate behaved in a way later shown wrong (false positive confirmed, false negative confirmed, OOD scene that wasn't flagged) | Same episodic table, distinguished by an `outcome_class` column, not a separate store | explicit query by NextBestAction when deciding whether to escalate (see below) |
| Outcome memory | Ground-truth resolution of a case (confirmed spill / confirmed non-event / unresolved), and its provenance (who confirmed, when) | Same table; `outcome` field already exists in `HistoricalCase`, just needs a real writer | feeds `propose_training_batch` gating, and future calibration work |

**Why structured over semantic retrieval, specifically here:** every current and near-term
SMRITI query is answerable by an exact structured predicate — region bbox, time window,
environmental regime bucket (low-wind/high-wind), NETRA behavior bucket (activated/
null/OOD-flagged). None of VARUNA's current evidence is unstructured text where embedding
similarity would out-perform a structured filter. Reach for semantic retrieval only if/when
a genuinely unstructured field appears (e.g. free-text operator notes) — and even then,
retrieve by structured predicate first, semantic search only within that filtered set.

**Retrieval never overrides current evidence** — enforced the same way `EvidenceEnvelope`
already enforces this for everything else: a `HistoricalCase` retrieved from SMRITI is
wrapped in its own `EvidenceEnvelope` with `trust` capped at `DEGRADED` (never `TRUSTED`) by
construction, and any inference that uses it must go through `.derive()` — meaning a case
that leans on strong historical precedent can never come out *more* confident than one
driven by live, direct evidence. This single rule is what prevents the brief's §7 worry
("memory must never override current evidence") from needing a special-case check anywhere
downstream — it falls out of machinery that already exists.

**Provenance for outdated/contradictory memories:** never delete, never overwrite — append
an `outcome_revision` row (same pattern PRAMAN already uses: raw artifacts never mutated).
"Contradictory" memories are a `EvidenceLedger.contradictions()`-shaped concept, not a
special SMRITI feature — most-recent-outcome wins for *display*, but the full history stays
queryable for audit.

**Learning loop, made real (governing brief §13), staged:**
```
CASE → DECISION → ACTION → OUTCOME (human-confirmed, written to episodic table)
     → propose_training_batch() [already exists, already gated pending]
     → HUMAN APPROVAL (required, already enforced — G-07)
     → [NEW] dataset snapshot with content hash, versioned, immutable
     → [NEW] training run references that exact snapshot hash (never "current SMRITI state")
     → [NEW] model version gate: new checkpoint must beat frozen baseline on the SAME
       protected holdout the baseline was scored on, evaluated by the SAME evaluator,
       before it can be proposed for deployment — i.e. literally the process this
       session's own B1 evaluation already followed, formalized as a standing gate
     → rollback = redeploy previous checkpoint hash, already how NETRA versioning works today
```
Nothing in this loop should be described as "VARUNA learns from every case" until the
`[NEW]` steps exist — today, at most, "VARUNA records outcomes that a human could later
choose to build a training set from."

---

## Uncertainty decomposition

**No new types needed** — `UncertaintyBlock` already has `representation`, `mean/std`,
`lower/upper`, `entropy`, `n_samples`, `sensitivity: dict[str, float]`. What's missing is a
**naming convention** so that "model uncertainty" vs "OOD uncertainty" vs "attribution
uncertainty" etc. are consistently keyed, not ad-hoc per producer:

```python
UNCERTAINTY_SOURCE_KEYS = {
    "model":        "epistemic uncertainty of the producing model itself (e.g. ensemble spread)",
    "data":         "input data quality/completeness-driven (QualityMetrics.completeness)",
    "ood":          "distance from training/calibration distribution (QualityMetrics.ood_score)",
    "disagreement": "cross-source conflict magnitude (from EvidenceLedger.contradictions())",
    "attribution":  "NYAYA posterior_entropy / distinguishability",
    "forecast":     "PRATIVARTAN SensitivityBlock (age/forcing/diffusivity)",
    "operational":  "human/process uncertainty — e.g. mission approval pending",
}
```
Each producer populates `UncertaintyBlock.sensitivity[key]` with whichever of the above keys
apply to it (most producers populate 1–2, not all 7). A downstream consumer (NextBestAction,
below) reads across an `EvidenceLedger`'s envelopes and sums/ranks by key to answer "what
kind of uncertainty dominates this case" — this is a `[no-compute]` aggregation over numbers
that mostly already exist (PRATIVARTAN, NYAYA) or will exist once §Detection Evidence's real
OOD score ships.

**When uncertainty is informative vs. when confidence is misleading:** the discipline
already in the Validity Gate generalizes directly — a check that would otherwise "pass" on a
fabricated/default value must instead be marked failing/blocking (the `phi_diagnostics_
availability` pattern). Apply the same rule to any new uncertainty consumer: **an unpopulated
`UncertaintyBlock` (representation="none") must never be silently treated as "no
uncertainty" — it must be treated as "uncertainty about this quantity is itself unknown,"**
which is a `RESTRICTED`-leaning signal, not a `VALID`-leaning one.

---

## Next-Best-Action

**Deterministic v1** (per governing brief §9 — a general principle, not `if confidence < X`):

```python
def action_value(action: CandidateAction, ledger: EvidenceLedger) -> float:
    info_gain = expected_uncertainty_reduction(action, ledger)   # see below
    relevance = decision_relevance(action, ledger)               # 0..1, does this action's
                                                                   # output feed a currently-
                                                                   # blocking or DEGRADED check?
    cost = action.compute_cost + action.operational_cost
    risk = action.risk_score                                     # e.g. tasking a satellite
                                                                   # pass has schedule risk
    return (info_gain * relevance) - cost - risk
```

- `expected_uncertainty_reduction`: for a deterministic v1, this does **not** need to be
  learned — it can be a static per-action-type table calibrated by hand from what each
  action historically resolves (e.g. "requesting a second Φ ensemble member reduces
  `forecast` uncertainty by up to X, never touches `attribution` uncertainty"). This is
  honest and auditable; a learned estimator is future work, not a blocker.
- `decision_relevance`: read directly off `EvidenceLedger.weakest_link()` — an action that
  would improve the ledger's *actual* weakest link scores higher than one that improves an
  already-strong input. This directly implements "don't gather evidence that doesn't move
  the decision."
- **Stopping condition**: stop when the best remaining `action_value()` is ≤ 0, OR when
  `ValidityGateResult.state` is already VALID with no blocking reasons — i.e. NextBestAction
  never contradicts the Validity Gate; it only tries to *earn* a better gate outcome before
  the gate is (re-)evaluated.
- **Escalation condition**: escalate to human when the best action's `risk` term dominates
  (e.g. only a live tasking action remains and its risk exceeds a fixed operational
  threshold), or when `EvidenceLedger.contradictions()` is non-empty and no candidate action
  would resolve it (contradictory evidence that more evidence-gathering cannot settle is
  exactly the case a human should see, not the system silently pick a side).
- **Retry policy**: an action that failed (execution error, not "returned unfavorable
  evidence") may retry once with backoff; a second failure converts to an escalation, never
  a silent drop.
- **Confidence decomposition** for "what do I know / don't know / why does it matter": this
  is literally `EvidenceLedger.current_belief_state()` + the uncertainty-source keys above,
  rendered as text — no new machinery, a reporting concern over existing structure.

**Candidate action registry (v1, all deterministic):**
| Action | Reduces | Cost tier |
|---|---|---|
| Re-run NETRA OOD check on adjacent tile | `ood` | no-compute (once real OOD exists) |
| Request additional Φ ensemble member | `forecast` | moderate-compute |
| Query SMRITI for corridor history | `attribution` (natural-seep prior) | no-compute |
| Widen AIS query window for CHHAYA | `attribution` (dark-contact term) | no-compute |
| Request environmental reprocessing (stale input) | `data` | cheap-experiment (I/O bound) |
| Escalate to human operator | resolves `disagreement`/`operational` directly | zero compute, real operational cost |

---

## Agent orchestration

**A thin loop around `GoldenCaseWorkflow`, not a replacement for it.** The workflow's fixed
stage sequence remains the deterministic backbone (it stays auditable, replayable,
idempotent — do not lose that). The agent loop wraps it:

```
OBSERVE     := GoldenCaseWorkflow's stage outputs so far, read via EvidenceLedger
ASSESS      := ValidityGateResult (already computed by an existing stage)
UNCERTAINTY := uncertainty-source decomposition (above)
NBA         := action_value() ranking (above)
EXECUTE     := either the next fixed workflow stage (normal path) OR a NextBestAction
               "gather more evidence" action (only when ASSESS is DEGRADED/RESTRICTED and
               an action with positive value exists) — this is the ONE new decision point
               the agent adds to an otherwise-fixed pipeline
UPDATE      := new artifacts land in PRAMAN/EvidenceLedger exactly as today
REASSESS    := re-run the Validity Gate; loop, bounded by a max-iterations config (never
               unbounded — a case that cannot reach VALID/DEGRADED in N rounds terminates
               INCONCLUSIVE and escalates, per the brief's own §12 framing of abstention as
               a feature)
```

This keeps the high-stakes property `docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md`
already established for `GoldenCaseWorkflow` (idempotent, replayable, deterministic
`run_id`) intact for the common path, while adding exactly one bounded, logged decision
point for the evidence-insufficient path. This is deliberately the smallest change that
gives VARUNA real agentic behavior without threatening the reconciliation work already done
on the case engine.

---

## Evidence fusion

**Principle:** extend `EvidenceEnvelope.derive()`'s existing monotonic-worst-case pattern
for *qualitative* state (trust/validity/degradation/mode) with an explicit, separate
*quantitative* fusion rule for combining numeric likelihoods (NYAYA's posterior, CHHAYA v2's
new hypothesis terms) — **do not** let the two mix. Qualitative state answers "can we act on
this at all"; quantitative fusion answers "which hypothesis is most likely, given we can."

- Use **log-likelihood-ratio summation** (already NYAYA's pattern via density comparison,
  `rho_k` vs `rho_0`) for combining independent evidence sources — this is the correct,
  standard treatment and NYAYA already does it right for the vessel-density term.
- **Correlated evidence must never be summed as if independent.** Concretely: CHHAYA's
  `DARK_CONTACT` likelihood and NYAYA's existing AIS-track-density likelihood both consume
  AIS data — if a vessel both has a suspicious AIS track AND is corroborated by a dark
  contact for a *different* nearby vessel, those two are independent and may combine. But if
  CHHAYA's `INSUFFICIENT_COVERAGE` finding is driven by the same low AIS density that also
  lowers NYAYA's `ensemble_completeness`-adjacent inputs, summing both as independent
  evidence of "no vessel present" double-counts the single underlying cause (poor AIS
  coverage). **Enforcement, concretely**: every likelihood term must declare a
  `depends_on_raw_source_ids: list[str]` (already derivable from
  `provenance.raw_artifact_refs`); the fusion step refuses to combine two terms whose
  `depends_on_raw_source_ids` overlap without an explicit correlation discount factor —
  this is a straightforward code-level guard, not a research problem, and should be a hard
  assertion, not a warning.
- **No blind confidence-score addition anywhere** — this generalizes the same rule the
  Validity Gate already follows (it never averages check results into one score; it looks at
  the *worst* blocking check and lists caveats separately). Any future "combined confidence
  number" for a case should be explicitly derived (documented formula, e.g. the posterior
  probability of the top `SourceHypothesis`), never an ad-hoc weighted sum of unrelated
  scores.

---

## Validity / abstention (extension, not replacement)

The existing `ValidityState` vocabulary (VALID/DEGRADED/RESTRICTED/INCONCLUSIVE) and
`allows_operational_action` already cover the governing brief's §12 requirements. The only
extension needed: **CHHAYA v2 and SMRITI v2 outputs must be able to trigger the same gate**,
which today only reads `PhiField`/`AttributionResultV2`. Concretely, add analogous checks to
`evaluate_validity_gate()` (or a sibling function following its exact pattern — same
fail-closed discipline, same `GateCheck`/`GateReason` shape):
- `chhaya_coverage`: fails/degrades when `LatentFinding.INSUFFICIENT_COVERAGE`.
- `source_hypothesis_distinguishability`: the NYAYA extension's analogous check to the
  existing `distinguishability` one, now over the widened `SourceHypothesis` space.
- `netra_ood`: **new, and arguably the most important addition** — blocks/degrades when the
  real OOD score (Detection Evidence contract, above) exceeds its calibrated cutoff. This is
  the concrete mechanism that finally makes "VARUNA notices when NETRA is out of its depth"
  operational rather than aspirational.

No new abstention *states* are needed — the existing four already form a complete lattice
for this purpose per the brief's own §12 framing ("we do not have enough evidence" already
maps cleanly to RESTRICTED/INCONCLUSIVE).

---

## Evaluation hooks

```python
@dataclass
class CaseScenario:
    scenario_id: str
    initial_evidence: list[EvidenceEnvelope]     # what's available at t=0
    hidden_outcome: str                          # never given to the system under test
    available_actions: list[CandidateAction]
    action_costs: dict[str, float]
    expected_decision_state: ValidityState
    expected_hypothesis: SourceHypothesis | None  # None for genuinely ambiguous scenarios

@dataclass
class EvaluationResult:
    scenario_id: str
    reached_decision_state: ValidityState
    reached_hypothesis: SourceHypothesis | None
    actions_taken: list[str]
    correct: bool                    # decision_state AND hypothesis both matched, where expected
    correctly_abstained: bool        # expected RESTRICTED/INCONCLUSIVE and system agreed
    evidence_efficiency: float       # info actually needed / info actually gathered
    stopped_appropriately: bool      # matches human judgment of when to stop, from scenario design
```

This is the contract the benchmark in `VARUNA_RESEARCH_ROADMAP.md` §Benchmark is built
against. It deliberately scores **abstention correctness** and **evidence efficiency** as
first-class, separate from raw accuracy — a system that reaches the right answer by
gathering every possible action regardless of cost should score worse on efficiency than one
that reaches it economically, even though both are "correct."
