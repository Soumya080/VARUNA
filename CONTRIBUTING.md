# CONTRIBUTING.md
## VARUNA GRID v2 — working agreement

Four people, seven days, one repository. These rules exist to keep integration cheap.

---

## 1. Non-negotiables

1. **Integrate daily.** No branch stays unmerged for more than 24 hours.
2. **Every task has INPUT → OUTPUT → ACCEPTANCE TEST.** If you cannot state the acceptance
   test, the task is not ready to start.
3. **Never redefine a contract type.** Import from `varuna_contracts`.
4. **No architecture change without an ADR.**
5. **No new major dependency without justification** in the PR.
6. **No generic LLM-generated code without tests.**
7. **Never mark something complete in documentation without a passing test.**

---

## 2. Branching & Worktrees

**VARUNA v2 uses a strict Role-Based Branching and Worktree Strategy.**

See [BRANCHING_STRATEGY.md](docs/BRANCHING_STRATEGY.md) for full details.

### Summary
- **`main`**: Production-ready. Do not commit directly.
- **`develop`**: Shared integration branch.
- **Role Branches (`varuna/lead`, `varuna/backend`, etc.)**: Development occurs exclusively in these isolated branches, which are checked out in adjacent worktrees (e.g., `../VARUNA-lead`).

Never merge role branches directly into each other. All integration happens through `develop`.

---

## 3. Commits

Conventional commits, imperative mood:

```
feat(nyaya): add corridor-based latent source residual
fix(data_guard): fail closed on unknown check result
test(contract): assert derive() never upgrades trust
docs(adr): ADR-0004 phi histogram over KDE
```

Scope is the package or role. Keep the subject under 72 characters and explain *why* in
the body when it is not obvious.

---

## 4. Pull requests

Every PR states:

- **What** changed and **why**
- Which module contract it implements (link the `LLM_IMPLEMENTATION_GUIDE.md` §10 entry)
- Which threat-matrix rows it covers, if any
- Test evidence — paste the actual output, do not assert
- Status label change for `SETUP_STATUS.md`, if applicable

**Merge requires:** CI green · a review from someone other than the author ·
`SETUP_STATUS.md` updated when a status changes.

---

## 5. Definition of Done

A module is DONE only when **all** hold:

- [ ] implemented, fully type-hinted
- [ ] module docstring states purpose, invariants, failure behaviour
- [ ] unit + contract tests pass
- [ ] imports only from `varuna_contracts` (no cross-module reach-through)
- [ ] structured logging with `case_id` bound
- [ ] failure behaviour defined and robustness-tested
- [ ] reproducible (seeded where stochastic)
- [ ] integrated on `develop`
- [ ] `processing_version` / `model_version` stamped on outputs
- [ ] `SETUP_STATUS.md` updated honestly

Scientific modules additionally: benchmarked · uncertainty reported · robustness-tested
under degraded forcing · limitations documented in the model card.

---

## 6. Code style

```bash
make fmt         # ruff --fix
make lint        # ruff
make typecheck   # mypy
make test        # unit + contract
make check       # all of the above — what CI runs
```

Python 3.12 · full type hints · Pydantic v2 at boundaries · `structlog` never `print` ·
UTC tz-aware only · WGS84 (lon, lat) · absolute imports · line length 100 ·
seed all randomness · docstrings explain **why**, not what.

---

## 7. Testing

Write the **contract test first** — it defines "done".

| Layer | When to add |
|---|---|
| `tests/unit/` | Any pure function with a branch |
| `tests/contract/` | Any change touching a boundary type or invariant |
| `tests/integration/` | Anything touching postgres/redis/minio |
| `tests/scientific/` | Any numerical result — seeded, with tolerances |
| `tests/robustness/` | Every P0/P1 row you implement containment for |
| `tests/e2e/` | Changes to the CASE-0001 path |

**A contract-test failure means an architectural rule was broken, not that a test is
flaky.** Fix the caller, or write an ADR. Never relax the assertion to get green.

---

## 8. ADRs

Required for: architecture changes · contract changes · scientific semantics · a new major
dependency · anything on the rejected list (Kafka, Kubernetes, service mesh, vector DB,
RAG, agents, RL in core).

`docs/adr/ADR-NNNN-short-title.md`:

```markdown
# ADR-NNNN — Title
**Status:** Proposed | Accepted | Superseded · **Date:** · **Deciders:**
## Context      (the forces, honestly — including what went wrong before)
## Decision     (what we are doing)
## Consequences (positive, negative, mitigation)
## Rejected alternatives  (and why each was rejected)
```

Otherwise: decide and proceed. Record non-obvious choices briefly. Do not block on style,
naming, or anything a later edit can recover.

---

## 9. Working with coding LLMs

Give the model exactly three things:

1. `LLM_IMPLEMENTATION_GUIDE.md`
2. the relevant `tasks/ROLE_0N_*.md`
3. `packages/varuna_contracts/`

That is sufficient context. It does not need the originating conversation.

**Review LLM output for these specifically** — they are the recurring failure patterns:

- redefined contract types instead of importing them
- hand-constructed envelopes that silently upgrade trust (must use `.derive()`)
- swallowed exceptions or silent defaults (`except: return 0.0`)
- external HTTP calls outside `varuna_source_adapters`
- point estimates where a distribution is required (age, landfall)
- confident claims in comments or docs that violate the honesty rules
- **fabricated numerical results** — a benchmark figure or accuracy value that was never computed

The LLM stops and asks a human only for the seven cases in `LLM_IMPLEMENTATION_GUIDE.md`
§15. Everything else it decides independently.

---

## 10. Honesty in code and docs

The honesty rules (`LLM_IMPLEMENTATION_GUIDE.md` §12) apply to code comments, docstrings,
variable names, UI copy, commit messages, and documentation — not only to slides.

If you write a status label, it must be justified by repository evidence. `SETUP_STATUS.md`
defines what each label means. **"It probably works" is `IMPLEMENTED`, not `VERIFIED`.**
