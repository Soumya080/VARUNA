# Worker Init
#
# NOT_IMPLEMENTED (Phase 4 cleanup, docs/product/HONESTY_LEDGER.md #36).
#
# Every task under `apps/worker/tasks/` is an empty `pass` body — a Celery
# task scaffold, never a working async pipeline. Nothing in VARUNA calls
# into this package: the real pipeline runs synchronously in-process
# (`varuna_domain.golden_case_engine.GoldenCaseWorkflow` /
# `varuna_domain.case_workflow.CaseWorkflow`), not via a task queue.
#
# Kept rather than deleted: it's a real, deliberate roadmap artifact (async
# task offload is a legitimate future architecture for a scaled deployment),
# and deleting it would erase that intent. Leaving it unmarked would have
# been worse — an empty task queue that looks wired is a fake capability.
# `celery_app.py`'s broker (`redis://localhost:6379/0`) is a placeholder
# and is not started or connected to by anything in this repository.
