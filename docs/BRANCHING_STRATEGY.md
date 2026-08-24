# VARUNA GRID v2 — Branching & Worktree Strategy

## Branch Roles

- **`main`**: The stable, production-ready branch. Direct commits to `main` are strictly prohibited.
- **`develop`**: The shared integration branch. All features and fixes are merged here before release.
- **Role Branches**: Isolated branches for each of the four engineering roles:
  - `varuna/lead` (Scientific / ML Lead)
  - `varuna/backend` (Data / Backend Engineer)
  - `varuna/frontend` (Frontend / Geospatial / Field Experience)
  - `varuna/mlops` (MLOps / Integration / Operations)

## Worktree Roles

To ensure isolated and safe development, each role operates in a dedicated Git worktree adjacent to the main repository:

- `../VARUNA-lead` → Tracks `varuna/lead`
- `../VARUNA-backend` → Tracks `varuna/backend`
- `../VARUNA-frontend` → Tracks `varuna/frontend`
- `../VARUNA-mlops` → Tracks `varuna/mlops`
- `../VARUNA` (Main repo checkout) → Tracks `develop` (or `main`)

**Rule**: Agents and engineers must only work in their designated worktree to prevent cross-contamination and accidental overwrites of other roles' work.

## Protected Files & Contract Ownership

- **`packages/varuna_contracts/`**: This directory is a **protected shared contract boundary**. It defines the interfaces between the isolated components.
- **Contract Changes**: Any changes to contracts require explicit cross-role review and an Architecture Decision Record (ADR) in `docs/adr/`. No role should unilaterally change a contract.
- **Architectural Rules**: Raw evidence must never be overwritten, and uncertainty must propagate (`EvidenceEnvelope.derive()`).

## Merge Strategy & Daily Integration Flow

1. **Isolation**: Development occurs exclusively on the designated role branch within the respective worktree.
2. **No Direct Merges Between Roles**: Role branches (`varuna/lead`, `varuna/backend`, etc.) **must never** be merged directly into each other.
3. **Integration via `develop`**:
   - When a role completes a unit of work (with passing tests), they merge their branch into `develop`.
   - Other roles regularly pull (or rebase against) `develop` to receive updates.
4. **No Destructive Commands**: Force-pushing (`git push -f`), destructive rebases, or history rewrites are not allowed on shared branches.

## Commit Expectations

- Commits should be atomic and represent a single logical change.
- Commit messages must follow conventional commits (e.g., `feat:`, `fix:`, `chore:`).
- Code must pass linting, type-checking, and contract tests (`make check`) before being merged into `develop`.
- Swallowed exceptions or silent defaults are explicitly forbidden (Fail safely, not silently).
