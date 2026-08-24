# LEAD HANDOFF

**Lead Worktree Path:** `D:\VARUNA-lead`
**Lead Branch:** `varuna/lead`

## Contract Status
- The authoritative contracts are in `packages/varuna_contracts/`.
- Contracts are **protected and verified**. Currently, 22 contract tests pass (`tests/contract/`).
- Do not redefine contract types. Do not let an LLM compute Φ/posteriors/trust/assignments/severity. Uncertainty must propagate using `EvidenceEnvelope.derive()`.

## Scientific Scaffold Status
- All modules are scaffolded (`varuna_netra`, `varuna_prativartan`, `varuna_nyaya`, `varuna_chhaya`), but the scientific pipeline is not implemented.

## Current Go/No-Go Status
- `experiments/go_nogo/` is invalid and its 100% cannot be quoted.
- A fair rebuild yields ~12% (chance 5%). See `docs/DECISIONS.md` §1.

## Exact First Scientific Task / Milestone
**FAIR GO/NO-GO → PRATIVARTAN → PhiField → NYAYA → ValidityGate**

## Files to Inspect
- `packages/varuna_contracts/` (Source of truth for contracts)
- `docs/adr/`
- `ARCHITECTURE_V2.md`
- `FAILURE_THREAT_MATRIX.md`
- `LLM_IMPLEMENTATION_GUIDE.md`

## Commands
- **Working Command:** `PYTHONPATH=packages python -m pytest tests/contract -q` (works today).

## Current Missing Dependencies & Known Blockers
- Python is 3.10 locally (spec requires 3.12).
- Stack never started; Docker never built. OpenDrift is not installed.
- **P0 Risk:** Go/no-go invalid — every downstream claim depends on rebuilding it honestly.
- **P0 Risk:** Nothing runs — no Dockerfile build, no OpenDrift. This blocks development.
- **P0 Risk:** Calibration blocked until the harness is valid.
