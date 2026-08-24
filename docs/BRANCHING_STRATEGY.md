# VARUNA GRID v2 — Branching & Worktree Strategy

## Branch Hierarchy
```
develop
├── varuna/lead
├── varuna/backend
├── varuna/frontend
└── varuna/mlops
```

## Rules
- **main** = stable
- **develop** = integration
- **role branches** = isolated
- **worktrees** = required
- **contracts** = protected
- **no force push**
- **no destructive reset**
- **no cross-role direct editing**
- **merge into develop only after tests**
