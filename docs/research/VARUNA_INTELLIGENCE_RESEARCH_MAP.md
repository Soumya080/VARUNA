# VARUNA GRID v2 — Intelligence Research Map

**Date:** 2026-09-02
**Scope:** Intelligence/research direction only (not product integration). No training, no
model modification performed to produce this document.
**Method:** Every claim below was checked against the repository (`packages/`, `apps/`,
`docs/`, `reports/`) as it exists on disk today, not against prior design docs. Where a
prior doc (`VARUNA_MASTER_CONTEXT.md`, `NETRA_TRAINING_MASTER_REPORT.md`) asserted
something not independently re-verified here, it is tagged `[INFERRED]`, not `[PROVEN]`.

**Evidence tags** (used throughout, per component):
`[PROVEN]` — verified against code/tests/data in this pass · `[MEASURED]` — a specific
number or behavior observed directly · `[IMPLEMENTED]` — code exists and runs, but its
correctness/completeness wasn't independently re-verified here · `[INFERRED]` — reasonable
conclusion from adjacent evidence, not directly checked · `[HYPOTHESIZED]` — plausible,
unproven · `[UNKNOWN]` — no evidence found either way · `[REJECTED]` — a prior claim that
this pass found to be false or unsupported.

---

## 1. Current architecture, as it exists on disk

```
Data Sources → Data Guard → NETRA → PRATIVARTAN(Φ) → NYAYA → CHHAYA → PRAVAAH → Validity Gate → ABHIYAN → Mission → Alerts → OperatorCase
```

There are **two parallel package trees**: `packages/varuna_*` (used by `apps/`, has
`__init__.py` reachable from the app layer) and `src/*` (mirrors the same component names —
`src/chhaya`, `src/nyaya`, `src/smriti`, `src/praman`, `src/prativartan`, `src/pravaah`,
`src/abhiyan`, `src/netra`). `[MEASURED]` — nothing under `packages/` or `apps/` imports
from `src.*`; `src/` was last touched 2026-08-24, before the current `packages/`
architecture matured. **`src/` is legacy/dead code relative to the live system** and should
not be read as current design — a real risk for any future session that greps the repo and
finds two competing implementations of the same component name. This should be either
archived or deleted by the Integration session; it is out of scope for this research pass
to delete it unasked.

All "current state" claims below describe `packages/*` only.

---

## 2. The evidence backbone: `EvidenceEnvelope` — `[PROVEN]`, and stronger than expected

`packages/varuna_contracts/evidence.py` is not a stub. It is a genuinely well-formed,
already-implemented evidence architecture that a large part of §5–§12 of the governing
research brief asks us to "design from first principles." It should be read as the
**foundation to build on**, not a gap to fill. Specifically, already implemented:

- **Trust ≠ confidence**, as two separate fields (`TrustState` on the *source*,
  `QualityMetrics.model_confidence` / `UncertaintyBlock` on the *measurement*) —
  exactly the distinction §10 of the brief asks for. `[PROVEN]`
- **Bounded Evidence Influence**: `TrustState.max_influence` caps `influence_weight`
  (TRUSTED=1.0, DEGRADED=0.6, CONFLICTED=0.3, QUARANTINED=0.0), enforced by a Pydantic
  validator, not by convention. `[PROVEN]`
- **Monotonic degradation propagation**: `EvidenceEnvelope.derive()` computes the *worst*
  trust/validity/degradation/mode across all inputs and forbids upgrading. A DEGRADED input
  cannot produce a TRUSTED output. This is exactly §5's requirement ("uncertainty must
  propagate through the pipeline") and it is structural (enforced by `.rank` comparisons in
  code), not a policy someone has to remember. `[PROVEN]`
- **`EvidenceMode` (REAL/SIMULATED/UNAVAILABLE)** with a hard invariant that it can only
  worsen downstream, and a validator that specifically rejects `mode=REAL` combined with
  `degradation_state=CACHED_REPLAY` — i.e. a demo replay can never claim to be a live
  observation. `[PROVEN]`
- **`UncertaintyBlock`** already supports five representations (`none/gaussian/lognormal/
  samples/field/interval`), plus `entropy`, `n_samples`, and a `sensitivity: dict[str,
  float]` field for "d(output)/d(assumption)" — i.e. attribution of uncertainty to a
  specific upstream cause is already a first-class field, not something to invent. `[PROVEN]`
- **`ValidityState`** (VALID/DEGRADED/RESTRICTED/INCONCLUSIVE) with
  `allows_operational_action` as the single authority gating the Action Gateway. `[PROVEN]`

**Research implication:** §5–§12 of the governing brief ask "how should VARUNA represent
evidence, uncertainty, and validity." The honest answer is: **the type system for this
already exists and is good.** The real gap is not the contract — it's that most producers
either don't populate `UncertaintyBlock`/`QualityMetrics` with real numbers, or don't exist
yet to consume them (see §4, §6, §7 below). The intelligence work is in **populating and
consuming** this contract faithfully, not replacing it. Any new design (CHHAYA v2, SMRITI
v2, NextBestAction, the Agent loop) MUST be expressed in terms of `EvidenceEnvelope` /
`derive()` / `ValidityState`, not a parallel confidence scheme. See
`VARUNA_INTELLIGENCE_SPEC.md`.

### Validity Gate — `[PROVEN]`, real and fail-closed

`packages/varuna_nyaya/validity_gate.py` runs 10–11 deterministic checks (source trust, Φ
convergence, Φ entropy, ensemble completeness, particle loss, age/forcing/diffusivity
sensitivity when available, posterior entropy, distinguishability, evidence mode) and
fails closed: a genuinely missing `SensitivityBlock` is treated as **blocking**, with an
explicit comment refusing to fabricate a passing number just to keep the gate's shape
unchanged (`validity_gate.py`, the "Do NOT fabricate a passing... number" block). This is
the single best exemplar in the repo of the discipline the brief's §12 asks for, and should
be the template for any new abstention logic (CHHAYA, SMRITI), not a new pattern.

### ABHIYAN's decision-state translation — `[PROVEN]`, correctly layered

`packages/varuna_abhiyan/decision_state.py::derive_operational_decision_state()` is a pure,
read-only translation from `ValidityGateResult` to a 4-state operational vocabulary
(VALID/RESTRICTED/BLOCKED/UNAVAILABLE). Its own docstring is explicit that it "is NOT a
second gate" and "never re-evaluates evidence" — a genuinely disciplined separation of
concerns between *evidence assessment* (NYAYA) and *operational consequence* (ABHIYAN).

### PRAMAN — `[PROVEN]`, but narrower than its brief-§18 role suggests

`packages/varuna_praman/praman.py` is an **artifact/provenance registry** (register, get,
list-by-case, optional object-store upload with sha256 content hash). It is NOT an
evidence-fusion or ledger-reasoning engine. Calling it "the Evidence Ledger" (as §5 of the
brief does) over-states its current role. `[REJECTED]` (as a claim that PRAMAN already *is*
the evidence ledger) — see `VARUNA_INTELLIGENCE_SPEC.md` §Evidence Ledger for the proposed
read-side layer that would actually earn that name.

---

## 3. Current uncertainty handling — mixed, and one important fake

- The **contract** for uncertainty (`UncertaintyBlock`, `QualityMetrics.ood_score`) is real
  and expressive. `[PROVEN]`
- **PRATIVARTAN (Φ)** populates real uncertainty: `SensitivityBlock` with
  age/forcing/diffusivity sensitivity computed by actual parameter perturbation sweeps
  (confirmed via `validity_gate.py`'s consumption of `phi.sensitivity.*_sensitivity` and the
  extensive ADR-0007/ADR-0008 commentary describing how each is derived). `[PROVEN]`
- **NYAYA** populates real posterior uncertainty (`posterior_entropy`,
  `distinguishability`) from an actual Bayesian density-likelihood computation
  (`packages/varuna_nyaya/likelihoods.py` compares Φ mass *density* inside vs. outside
  vessel corridors — a real, non-trivial statistical treatment, not a placeholder).
  `[PROVEN]`
- **NETRA's OOD detector is a fake.** `packages/varuna_netra/ood.py`:
  ```python
  class OODDetector:
      def compute_score(self, logits, features=None) -> float:
          return float(np.random.uniform(0.1, 0.9))  # "Stub for Mahalanobis / Energy score"
  ```
  This returns uniform random noise, not a computed OOD score. `[MEASURED]`. Any prior
  claim that VARUNA "detects out-of-distribution SAR scenes" via this module is
  **`[REJECTED]`** — it does not. The real MC20 null-detection finding
  (`docs/research/NETRA_TRAINING_MASTER_REPORT.md`, max oil probability 3.05e-6) was reached
  by **manual, after-the-fact investigation of raw output statistics**, not by this OOD
  module — i.e. VARUNA currently has *no* automated, in-pipeline OOD signal for NETRA at
  inference time. This is one of the highest-leverage, cheapest gaps identified in this pass
  (see roadmap NOW item).
- **CHHAYA and SMRITI currently produce no real uncertainty at all** — see §6, §7. Their
  mock implementations either omit `UncertaintyBlock` population or return fixed constants
  (`confidence=0.6` in `MockChhayaProvider`).

**Conclusion for §10 of the brief ("uncertainty decomposition"):** the *representation*
problem is solved (`UncertaintyBlock`). The *population* problem is solved for
PRATIVARTAN/NYAYA and unsolved for NETRA (fake OOD), CHHAYA (no model), SMRITI (no model).
There is currently no single place that *decomposes* uncertainty across sources for a given
case — each subsystem's uncertainty lives in its own envelope, propagated but not jointly
reasoned over. This is a real, well-scoped design gap; see spec §Uncertainty.

---

## 4. Current agentic behavior — `[MEASURED]`: none exists

A repo-wide search for agent/orchestration/next-best-action code
(`agent`, `orchestrat`, `next_best_action`, `NextBestAction`, any `class *Agent`) inside
`packages/`, `src/`, `apps/` returned **zero matches**. `[MEASURED]`

What *does* exist and is sometimes mistaken for agentic behavior:

- **`GoldenCaseWorkflow`** (`packages/varuna_domain/golden_case_engine.py`, per
  `docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md`) — a **fixed, deterministic
  pipeline** (stage → stage → stage) with idempotency keying and replay fixtures. It
  executes a pre-determined sequence of stages for every case; it does not choose which
  stage to run next based on evidence, does not decide to skip a stage because evidence is
  already sufficient, and does not decide to escalate. This is orchestration in the
  workflow-engine sense, not in the decision-theoretic sense the brief's §8–§9 describe.
  `[PROVEN]` (from architecture doc + package structure).
- **`WhatIfSimulator`** (`packages/varuna_domain/whatif/simulator.py`) — a stub. Its one
  method, `simulate_wind_change()`, calls `self.chhaya_service.forecast(...)`, but
  `ChhayaProvider` (the protocol it's typed against) has no `forecast` method — only
  `investigate()`. `[MEASURED]` — this is either dead code or a latent `AttributeError`
  waiting for a caller; either way it is not a working what-if capability today.

**Conclusion:** the entire "agentic intelligence" layer described in the brief's §8–§9
(OBSERVE→ASSESS→UNCERTAINTY→NEXT-BEST-ACTION→EXECUTE→UPDATE→REASSESS) is **greenfield**.
There is nothing to refactor here — this is a genuine "design from first principles"
opportunity, and the design in `VARUNA_INTELLIGENCE_SPEC.md` treats it as such, while
insisting it be built as a thin decision layer *around* `GoldenCaseWorkflow`'s existing
stages, not a replacement for them (§9 of that spec).

---

## 5. Current memory behavior (SMRITI) — `[MEASURED]`: mock, in-process, non-persistent

`packages/varuna_smriti/`:
- `protocol.py` defines a reasonable interface (`record_outcome`, `query_history`,
  `detect_corridors`, `propose_training_batch`) — the *shape* is sound.
- `mock.py` is the **only** implementation. `MockSmritiProvider` stores `HistoricalCase`
  objects in a plain Python list (`self._history: List[HistoricalCase]`), which is
  process-local and lost on restart. `query_history()` does a linear bbox+time filter over
  that list. `detect_corridors()` **always returns `[]`** — recurrence-corridor detection
  does not exist. `[MEASURED]`
- `propose_training_batch()` deliberately returns `status="pending"` and is commented
  "Never auto-approved. Threat G-07" — a genuinely good safety property (memory cannot
  silently become training data), but it also means **the closed learning loop described in
  the brief's §13 has no implementation past this single guardrail**: nothing consumes an
  *approved* `TrainingProposal`, there is no outcome-validation step, no versioning, no
  rollback. `[MEASURED]` (nothing found; `service.py::trigger_learning_loop()` literally
  contains `pass  # Dispatch to task runner in real system` for the approved branch).
- There is **no vector store, no embeddings, no semantic retrieval** anywhere in
  `varuna_smriti` — which is good news relative to the brief's §7 warning against reducing
  SMRITI to "vector database + embeddings": that mistake hasn't been made, because nothing
  has been built yet. The design in the spec should capitalize on this clean slate rather
  than treat it as a gap to patch with the most obvious (semantic-search) tool.

**Conclusion:** any current claim that "VARUNA learns from cases" or "SMRITI provides
historical context" is **`[REJECTED]` as a description of the live system** — it is a
protocol and a guardrail, not a memory. This is accurately reflected already in
`docs/VARUNA_MASTER_CONTEXT.md`'s component board, which does not claim SMRITI is real (it
isn't even listed in the board — a gap in that doc worth flagging to Integration).

---

## 6. Current CHHAYA behavior — `[MEASURED]`: narrower than its intended role, mock-only

`packages/varuna_chhaya/protocol.py`'s `ChhayaProvider.investigate()` signature reveals
CHHAYA's *actual* current job: matching **radar contacts against AIS positions** to find
vessels not broadcasting AIS ("dark vessels"), returning `List[DarkVesselDetection]` plus
one of three `LatentFinding` enum values (`INSUFFICIENT_COVERAGE`,
`RADAR_CONTACT_WITHOUT_AIS`, `VISIBLE_SOURCES_EXIST_BUT_WEAK`).

`MockChhayaProvider` (`mock.py`) implements this with pure geometry: AIS coverage fraction
threshold (0.6), a 10km proximity check, deterministic hashed IDs. Confidence is a hardcoded
`0.6` when it fires — not a computed value.

**This is materially narrower than the source-hypothesis engine the governing brief's §6
describes** (`vessel-associated / coastal / natural seep / other anthropogenic / unknown`,
with priors, likelihoods, temporal/spatial consistency, AIS relationship, environmental
consistency, SAR morphology). Two important findings follow:

1. **NYAYA already implements most of what §6 is asking for**, just under a different name
   and for a narrower hypothesis space. `packages/varuna_nyaya/` is a real Bayesian engine:
   density-based likelihoods of Φ mass per vessel corridor vs. background (`likelihoods.py`),
   a real behavioral prior combining speed-anomaly / loiter / night-proximity sub-scores
   with documented provenance for each threshold (`prior.py`), and posterior/entropy/
   distinguishability outputs consumed by the Validity Gate. This *is* "vessel-associated
   vs. latent/unknown" attribution, done properly, today.
2. **CHHAYA's actual, distinct job is upstream of that**: producing the "is there a vessel
   here that AIS doesn't already tell NYAYA about" signal, and — per its `LatentFinding`
   enum — flagging when SAR coverage itself is insufficient to say anything. This is a
   real and useful function, but it is not itself a multi-hypothesis source-attribution
   engine, and building CHHAYA v2 as if it were duplicates NYAYA rather than complementing
   it.

**Conclusion:** the correct research direction is *not* "give CHHAYA a Bayesian
multi-hypothesis engine like the brief's §6 describes in isolation." It is: **extend
NYAYA's existing hypothesis space** (currently: named vessels + one residual "latent"
bucket) **to include the additional structured hypotheses CHHAYA and other evidence sources
can support** (coastal-outfall proximity, historical natural-seep corridors from SMRITI,
CHHAYA's dark-contact-without-AIS signal as one more likelihood term) — rather than
building a second, competing Bayesian engine. See `VARUNA_INTELLIGENCE_SPEC.md` §CHHAYA for
the concrete contract. This reframing is itself one of this pass's more important findings.

---

## 7. Current NETRA limitations — grounded in `NETRA_TRAINING_MASTER_REPORT.md` + this session's own B1 diagnostic

*(Full history in `docs/research/NETRA_TRAINING_MASTER_REPORT.md`; only the parts load-bearing
for intelligence design are repeated here.)*

- **v0.2** is the only real, deployed detector. Official source-domain IoU 0.6458, PR-AUC
  0.8513, frozen threshold 0.806. `[PROVEN]` (checkpoint hash-verified).
- **v0.2 on MC20 (real external case): null detection** (max oil probability ≈3e-6).
  Cross-domain / low-wind generalization is **not established**. `[PROVEN]`
- **B1** (weak-supervision domain-expansion pilot) trained successfully (benign
  optimization, smooth loss decrease) but regressed catastrophically on held-out target
  domain: IoU −84.1%, Recall −84.8%, PR-AUC only −3.9%. `[PROVEN]`
- This session's own **B1 Score-Distribution Diagnostic**
  (`reports/netra_v03/B1_SCORE_DIAGNOSTIC.md`, `b1_score_diagnostic.json`) established, via
  direct measurement (not the fake OOD module — a manual, read-only forward-pass rerun),
  that the failure is **MIXED, leaning strongly REPRESENTATION_DOMINANT**: B1 retains a
  narrow high-confidence sliver (p99=0.999) but 90%+ of true positive pixels score at
  background level (p90=p95=0.000); best-achievable F1 at *any* threshold is 0.095 vs
  v0.2's 0.408 (>4×); 10/10 spatially-sampled real-oil tiles show zero B1 activation at the
  frozen threshold. This rules out "B1 just needs recalibration" as a sufficient
  explanation. `[PROVEN]` (this session, checkpoint-hash-verified before and after).
- **NETRA has no automated OOD signal in production** — see §3 above. This is a materially
  more urgent gap than any single-model accuracy question, because it means VARUNA
  currently has no way to know, at inference time, that a scene resembles MC20 (i.e. is
  likely to fail) before acting on a null or low-confidence detection.

**Research framing correction (per the brief's own §4):** the natural next question is not
"how do we make NETRA perfect" but "how robust is VARUNA to NETRA's known, measured failure
modes" — and on that question, this pass finds **VARUNA has the evidence contract to be
robust (§2) but is not yet exercising it for NETRA specifically**, because NETRA's OOD
output is fake and its `UncertaintyBlock`/`QualityMetrics.ood_score` are presumably left at
defaults when NETRA's envelope is constructed (not independently re-verified this pass —
`[HYPOTHESIZED]`, cheap to check, flagged in the roadmap).

---

## 8. Current evaluation strategy

- **NETRA**: a real per-tile/per-scene IoU/Dice/Precision/Recall/PR-AUC evaluator exists
  and was used for the v0.2 official test and the B1 CALM-GRD-HOLDOUT run
  (`scripts/netra_v03/08_b1_final_evaluation.py`). It evaluates *final model accuracy only*
  — no calibration metric, no OOD-detection metric (because there's no real OOD detector to
  evaluate), no decision-quality metric. `[PROVEN]`
- **Track 2 (PRATIVARTAN/NYAYA/Validity Gate)**: unit/contract test suites exist
  (`tests/scientific/`, `tests/contract/`) — NYAYA is documented as having ~30 tests,
  Validity Gate ~17, per `VARUNA_MASTER_CONTEXT.md`. `[INFERRED]` (test counts not
  re-counted this pass; test *existence* and passing status was established in prior Track
  2 work, not re-verified here — treat the exact counts as `[INFERRED]`, their general
  existence as `[PROVEN]` from `tests/scientific/` and `tests/contract/` being populated
  directories).
- **The go/no-go benchmark harness is self-documented as scientifically invalid**
  (`VARUNA_MASTER_CONTEXT.md` §9: "EvidenceEnvelope construction error"). `[INFERRED]` from
  that doc; not independently re-run this pass (would require compute this task is not
  authorized to spend). This is the closest existing thing to the "VARUNA benchmark" the
  brief's §15 asks for, and it is currently broken — a concrete, cheap-to-scope repair
  target, not something to build from scratch. See roadmap.
- **There is no evaluation of**: abstention correctness (did the Validity Gate block when it
  should have?), next-best-action quality (doesn't exist yet), memory usefulness (SMRITI
  isn't real yet), or evidence-fusion correctness (CHHAYA/NYAYA joint reasoning doesn't
  exist yet). These are all `[UNKNOWN]` by construction — the machinery to even ask the
  question doesn't exist. Not a criticism; a scope statement for future work.

---

## 9. Unresolved research questions (ranked by how directly this pass's evidence bears on them)

1. **Why did B1's representation collapse for 90%+ of positive pixels while retaining a
   narrow high-confidence core?** Live candidates (from the B1 diagnostic + master report
   §12, non-exclusive): MIL loss weight too low, `topk_frac=0.10` too restrictive, domain
   gap too wide for mixed-batch weak supervision. Not resolved by this pass — deliberately;
   resolving it requires a training experiment, out of scope for this session.
2. **Does NETRA's `EvidenceEnvelope` actually carry a real `QualityMetrics.ood_score` /
   `UncertaintyBlock` today, or defaults?** Cheap, no-training check — see roadmap NOW item.
3. **Should CHHAYA's dark-contact signal be a new NYAYA likelihood term, or a separate
   evidence input fused at the Validity Gate?** A genuine design fork; §6 above argues for
   the former, but this is a judgment call for Integration to make with the concrete
   contract in the spec.
4. **What does SMRITI need to store to be useful, given VARUNA has essentially zero real
   case history yet?** The honest answer right now is: very little real data exists to
   design retrieval against. This argues for building the *schema* and *write path* now
   (cheap), deferring retrieval-quality tuning until real case volume exists (later).
5. **Is the go/no-go harness's EvidenceEnvelope construction error a one-line fix or a
   structural one?** Unknown without reading it directly — flagged for a cheap diagnostic,
   not solved here (would require reading `experiments/go_nogo_v2/`, out of this pass's time
   budget; explicitly deferred, not silently skipped).

---

## 10. Known assumptions (currently load-bearing, not independently re-derived)

- That `packages/varuna_contracts` is the single locked schema surface referenced by ADRs
  0003, 0006–0009 — treated as ground truth per repo convention (`evidence.py`'s own
  docstring: "do not break without an ADR"), not re-derived from the ADRs themselves this
  pass. `[INFERRED]`
- That the CALM-GRD-HOLDOUT / MC20 / Zenodo Part III protection rules from the NETRA master
  report still apply unchanged — this pass did not touch any of those assets and has no
  reason to doubt them, but did not re-derive the rule from scratch either.
- That `tests/scientific/`, `tests/contract/` etc. pass in CI — their existence was
  confirmed by directory listing, not by running them (out of scope: this pass is
  read-only/no-compute by design).

## 11. Unsupported claims found in existing docs (corrected here)

- **"PRAMAN" as "Evidence Ledger"** (brief's own §5/§18 framing) — `[REJECTED]` as a
  description of current code; PRAMAN is an artifact registry. See §2 above.
- **Implicit claim that NETRA has OOD detection** (anywhere this is assumed rather than
  stated as a gap) — `[REJECTED]`; it's `np.random.uniform(0.1, 0.9)`. See §3.
- **Implicit claim that SMRITI "provides historical context to CHHAYA/NYAYA"** — `[REJECTED]`
  as current fact; the protocol exists, nothing populates it with real cases yet, and
  nothing downstream calls `query_history()` today (not found in this pass's search of
  `packages/varuna_chhaya`, `packages/varuna_nyaya` for `smriti` imports — `[MEASURED]`:
  zero matches).
- `VARUNA_MASTER_CONTEXT.md`'s component board is otherwise accurate and conservative where
  checked (correctly marks CHHAYA 🔴 BLOCKED / mock-only, correctly does not claim SMRITI is
  real by omitting it) — flagged here as a **positive** finding: the existing status
  reporting in this repo is generally honest, which is itself useful context for how much to
  trust future undocumented claims.

## 12. High-value future investigations

See `VARUNA_RESEARCH_ROADMAP.md` for the full ranked, cost-tagged list. The single
highest-leverage one identified in this pass, given it requires zero training and zero new
infrastructure: **wire a real OOD score into NETRA's envelope and verify it fires on MC20 /
does not fire on CALM-GRD-HOLDOUT**, because every downstream robustness story in this
document depends on VARUNA actually being able to notice when NETRA is out of its depth, and
today it structurally cannot.
