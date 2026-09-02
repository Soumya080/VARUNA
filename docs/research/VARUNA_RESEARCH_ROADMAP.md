# VARUNA GRID v2 — Research Roadmap

**Date:** 2026-09-02. Companion to `VARUNA_INTELLIGENCE_RESEARCH_MAP.md` (what's true today)
and `VARUNA_INTELLIGENCE_SPEC.md` (what to build). Nothing in this document is authorization
to execute — per the governing brief, any item tagged `moderate-compute` or
`expensive-research` requires a separate, explicit written justification (research question,
evidence, expected information gain, compute/runtime cost, success/failure criterion,
protected evaluation surface, decision impact) **before** execution, and none has been
produced or approved in this session.

**Cost tags:** `no-compute` (reading/wiring/aggregation over existing data) ·
`cheap-experiment` (minutes, no training, e.g. a diagnostic forward pass) ·
`moderate-compute` (a short training run or sweep, ≤~30 min, needs the written justification
above) · `expensive-research` (hours+, needs the written justification and should default to
NOT happening until several cheaper items have been tried first).

---

## NOW (this week, no training)

| Item | Cost | Why now |
|---|---|---|
| Replace `NETRA/ood.py`'s `np.random.uniform` stub with a real energy/max-softmax OOD score, calibrated on the 2 known reference points (CALM-GRD-HOLDOUT in-domain, MC20 OOD) | `cheap-experiment` | Highest information-gain-per-cost item found this pass — closes the single gap every downstream robustness claim depends on. No training; a closed-form pass over already-computed logits. |
| Build `EvidenceLedger` as a thin read-side class over PRAMAN (research map §2, spec §Evidence Ledger) | `no-compute` | Pure aggregation over data that already exists; unblocks NextBestAction and the fusion-correlation guard below. |
| Fix `MockChhayaProvider`'s hardcoded `confidence=0.6` to derive from the coverage/proximity numbers already computed in `coverage.py` | `no-compute` | The real numbers already exist in the function and are being thrown away. |
| Diagnose the go/no-go harness's documented "EvidenceEnvelope construction error" (`experiments/go_nogo_v2/`) — read-only diagnosis of whether it's a one-line fix or structural | `cheap-experiment` | It's the closest existing thing to the brief's §15 benchmark; repairing an existing broken harness is cheaper than building a new one from zero. |
| Verify whether NETRA's production envelope currently populates `QualityMetrics`/`UncertaintyBlock` at all (research map §7 open question 2) | `cheap-experiment` | One grep + one read; resolves an assumption several other items depend on. |
| Add `depends_on_raw_source_ids` overlap assertion to any evidence-fusion combination code as it's written (spec §Evidence Fusion) | `no-compute` | Cheapest possible prevention of the single most common evidence-fusion bug (double-counting correlated sources); costs nothing to build in from the start, expensive to retrofit later. |

## NEXT (this month, mostly no/cheap compute, some moderate-compute *proposals* to write up — not run)

| Item | Cost | Notes |
|---|---|---|
| SMRITI v2 schema + write path (episodic table per spec, Postgres, per ADR-0004) | `no-compute` | Schema and a real `record_outcome()` writer. Retrieval-quality tuning explicitly deferred — see research map §9 item 4: too little real case history exists yet to tune against. |
| NYAYA hypothesis-space extension (`SourceHypothesis` widened, `DARK_CONTACT`/`COASTAL` deterministic likelihood terms) | `no-compute` → `cheap-experiment` for validation against existing Track 2 test fixtures | `NATURAL_SEEP` term stays a flat prior until SMRITI v2 has real corridor data — do not fabricate a corridor signal to make the term "complete." |
| Validity Gate extension: `chhaya_coverage`, `source_hypothesis_distinguishability`, `netra_ood` checks (spec §Validity) | `no-compute` once the real OOD score and widened hypothesis space exist | Follows the exact `GateCheck`/fail-closed pattern already in `validity_gate.py` — no new design needed, just more checks in the same shape. |
| NextBestAction v1: static `expected_uncertainty_reduction` table + `action_value()` scoring over the 6-action registry in the spec | `no-compute` | Deterministic, hand-calibrated table; explicitly not learned yet. |
| Write (not run) the justification doc for a `topk_frac` / MIL-loss-weight ablation on NETRA v0.3 (per `B1_SCORE_DIAGNOSTIC.md`'s own recommendation) | `no-compute` (writing the justification) / the ablation itself is `moderate-compute` and requires separate approval | This is the most informative next NETRA training-adjacent question identified across this session and the prior one — but it is a training run and stays gated behind the brief's own approval process. |

## LATER (once NOW/NEXT are real and some case volume exists)

| Item | Cost | Notes |
|---|---|---|
| Agent orchestration loop wrapping `GoldenCaseWorkflow` (spec §Agent orchestration) | `no-compute` (it's a decision-point wrapper, not new inference) | Depends on EvidenceLedger + NBA + widened Validity Gate all existing first — sequencing matters, this is intentionally not a NOW item. |
| SMRITI retrieval-quality tuning (which structured predicates actually help) | `cheap-experiment`, repeatable | Only meaningful once real episodic rows exist — premature before that. |
| VARUNA benchmark v1 (spec §Evaluation hooks `CaseScenario`/`EvaluationResult`), built from repaired go/no-go harness + hand-authored difficult cases (low-wind, ambiguous SAR, no-spill, vessel-associated, natural-seep ambiguity, missing AIS, conflicting evidence, OOD imagery, degraded environmental data — per governing brief §15) | `no-compute` to author scenarios / `cheap-experiment` to run them against the current pipeline | This should become a standing regression suite, run before any future NETRA/CHHAYA/NYAYA change — see "Future research" below for why this is the single highest-value *process* investment. |
| Learned `DARK_CONTACT` likelihood term (replacing the deterministic proximity heuristic) | `moderate-compute`, needs real confirmed-outcome cases first | Explicitly gated on SMRITI v2 outcome memory having enough rows to be meaningful — not a near-term item regardless of compute budget. |

## FUTURE RESEARCH (ranked, with full cost/risk/impact accounting)

Per governing brief §16, all 9 candidate NETRA-generalization directions, ranked by
information gain per unit cost — **none authorized to run**:

| # | Direction | Hypothesis | Evidence for it | Info gain | Compute | Data cost | Risk | Eval method | Decision impact |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **topk_frac / MIL-weight ablation** | `topk_frac=0.10` too restrictive and/or MIL weight too low caused the "minimal confident core" collapse | B1 diagnostic: p90/p95=0.000 but p99=0.999 (direct signature of restrictive top-k pooling) | **High** — directly tests the diagnostic's own leading hypothesis | ~30min–2h per config, small grid | none new | Low (frozen baselines untouched, B1 already disqualified) | Same CALM-GRD-HOLDOUT protocol, same evaluator | If it recovers recall: strong signal MIL formulation, not domain gap, was the cause — reopens weak-supervision path. If not: rules it out cheaply. |
| 2 | Stronger labels (fewer WEAK_BOX, more STRONG_PIXEL in target domain) | Label noise (62.3% non-oil box interior, measured) caps achievable recall regardless of formulation | Master report's label-quality analysis | Medium-high | none (labeling is data cost, not compute) | **High** (manual annotation) | Low | Same protocol | Would separate "label ceiling" from "formulation" as the bottleneck — but expensive to acquire, so sequenced after #1 |
| 3 | Better low-wind data (more/varied low-wind scenes) | Domain gap is about scene diversity, not just label quality | v0.2's real MC20 null result | Medium | none (acquisition, not training, is the cost) | Medium (acquisition + qualification pipeline already exists from Phase C/D of prior sessions) | Low | Same protocol | Only informative after #1 rules in/out formulation as dominant |
| 4 | Domain adaptation (feature alignment, adversarial or otherwise) | Master report hypothesis #3 ("domain gap too wide for mixed-batch weak supervision") | B1's AUC only mildly reduced (some transferable signal exists) is weak circumstantial support | Medium | `expensive-research` | none new | Medium (architecture change, harder to keep interpretable) | Same protocol + needs new ablation infra | Not worth starting before #1's result is known |
| 5 | Representation learning (self-supervised pretraining on unlabeled SAR) | More SAR-general features would generalize better zero-shot | None specific to this failure yet | Low-medium (untargeted) | `expensive-research` | Large (needs unlabeled corpus) | Medium | New protocol needed | Speculative; do not start before cheaper diagnostics exhausted |
| 6 | Uncertainty/OOD improvements *for NETRA itself* (learned OOD head, not just the energy-score fix in NOW) | A learned detector would out-perform the closed-form energy score | None yet — the closed-form version doesn't exist yet to compare against | Medium, but only once a real baseline OOD score exists | `moderate-compute` | none new | Low | Compare against the NOW-item energy score on the same 2 reference points + any new external case | Sequenced strictly after the NOW item, not a substitute for it |
| 7 | Calibration (post-hoc, e.g. temperature scaling) on v0.2 or a future B-series model | The B1 diagnostic's own "aside" found v0.2's best-F1 threshold (0.00098) is far from the frozen 0.806 on the WEAK_BOX surface — worth understanding even for v0.2 | Direct measurement, this session | Medium, cheap enough to be worth doing regardless of B1's fate | `cheap-experiment` (fit a scalar on already-computed scores, no retraining) | none | Low | Compare calibrated-threshold performance against frozen 0.806 on the SAME protected holdout, report only, no redeployment without separate sign-off | Informative regardless of which future direction wins — recommend doing this cheaply alongside #1 |
| 8 | Architecture changes (deeper encoder, different decoder) | Capacity, not data/formulation, is the bottleneck | Weak — nothing in the evidence points at capacity specifically | Low | `expensive-research` | none new | Medium | New protocol | Least justified by current evidence; last priority |
| 9 | External-domain validation (beyond MC20, a second real external case) | Generalization claims need more than one external data point | v0.2's MC20 result is currently VARUNA's *only* real external validation | High for *trustworthiness of any future claim*, independent of which model direction wins | `no-compute`/`cheap-experiment` if data already acquirable, else data-cost | Medium (acquisition) | Low | New held-out case, same protocol | Should happen in parallel with #1–2 regardless of outcome — one external case is not enough to trust any generalization story, including this document's own |

**Recommended sequencing if/when training work is re-approved:** #1 (ablation) and #7
(calibration study) are both cheap, fast, and directly informed by this session's own
measurements — run together first. Their combined result determines whether #2/#3 (data) or
#4/#5 (architecture/domain-adaptation) is the better-justified next spend. #9 (a second
external validation case) should be pursued in parallel on its own track, since it improves
the trustworthiness of *every* other direction's eventual evaluation, not just one of them.

---

## Benchmark design (governing brief §15, elaborated)

Scenario categories to author first (each needs: initial evidence, hidden outcome, available
actions+costs, expected decision state, expected hypothesis where unambiguous):

1. **Clean positive** — real oil, good conditions, unambiguous vessel source → expect VALID,
   `VESSEL_ASSOCIATED`.
2. **Low-wind ambiguous** — the exact CALM-GRD-HOLDOUT regime NETRA struggles with → expect
   DEGRADED or RESTRICTED depending on OOD score, tests whether the new `netra_ood` gate
   check actually fires appropriately.
3. **No-spill / lookalike** — a low-wind cell with no real slick → expect VALID +
   correctly-negative, tests false-positive discipline.
4. **Dark vessel, no AIS** — tests the new `DARK_CONTACT` NYAYA term end-to-end.
5. **Natural-seep-plausible region with no SMRITI history yet** → expect the flat-prior
   behavior specified for `NATURAL_SEEP` (spec §CHHAYA) rather than a fabricated confident
   answer — this scenario exists specifically to catch a regression where someone "fixes"
   the flat prior by inventing a plausible-looking number.
6. **Missing AIS entirely** → expect CHHAYA's `INSUFFICIENT_COVERAGE` to propagate through
   to a DEGRADED/RESTRICTED gate state, not a silently-confident vessel attribution.
7. **Conflicting evidence** (e.g. strong NETRA detection + NYAYA posterior flat) → expect
   `EvidenceLedger.contradictions()` non-empty and an escalation, not a system-chosen winner.
8. **OOD imagery** (MC20-like) → expect the `netra_ood` gate check to block/degrade, this is
   the direct regression test for the NOW item at the top of this document.
9. **Degraded environmental data** (stale ERA5/CMEMS) → expect `DegradationState.STALE_INPUT`
   to propagate to DEGRADED, testing the existing `derive()` monotonicity end-to-end through
   a realistic, not synthetic-only, path.

Metrics per `EvaluationResult` (spec §Evaluation hooks): correctness, correct-abstention
rate, evidence efficiency, tool/action-selection quality, appropriate-stopping rate. Track
these **as a suite over time** — a system that gets more accurate but less efficient, or more
efficient but starts over-trusting SMRITI, should show up as a regression even if headline
accuracy improves. This benchmark, kept current, is the single highest-value process
investment identified in this pass: every other roadmap item above becomes easier to justify
or reject once there is a standing, repeatable way to measure whether a change actually
improved system-level decision quality rather than just one component's isolated metric.
