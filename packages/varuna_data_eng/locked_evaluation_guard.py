"""
VARUNA GRID — Locked evaluation dataset guard.

Reads data/catalog/locked_evaluation_manifest.json and provides a single
function any training-discovery path can call before including a dataset
in a training/tuning/normalization/early-stopping pool:

    from varuna_data_eng.locked_evaluation_guard import raise_if_locked
    raise_if_locked("zenodo_part3", context="training")

This module does not modify anything and does not itself touch any raw
data. It is new code, not wired into any existing training entrypoint
(NETRA's training path is out of scope for this pass) — it exists so that
the moment a locked dataset is genuinely wired into a training loop
somewhere, this guard is available to call rather than needing to be
invented at that point.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "catalog" / "locked_evaluation_manifest.json"
)

Context = Literal["training", "tuning", "normalization", "threshold_tuning", "early_stopping"]

_CONTEXT_TO_POLICY_KEY = {
    "training": "training_allowed",
    "tuning": "tuning_allowed",
    "normalization": "normalization_allowed",
    "threshold_tuning": "threshold_tuning_allowed",
    "early_stopping": "early_stopping_allowed",
}


class LockedDatasetError(RuntimeError):
    """Raised when a training-discovery path attempts to use a dataset
    that data/catalog/locked_evaluation_manifest.json marks as locked for
    that specific purpose."""


def _load_manifest() -> dict:
    if not _MANIFEST_PATH.exists():
        # No manifest means no locked datasets are declared — fail open
        # only in the narrow sense of "nothing to check", never fail open
        # on an actual lock (a lock, once declared, is always enforced).
        return {"policy": {}, "datasets": {}}
    return json.loads(_MANIFEST_PATH.read_text())


def is_locked(dataset_id: str) -> bool:
    """True if dataset_id appears in the locked-evaluation manifest at all
    (regardless of context)."""
    manifest = _load_manifest()
    return dataset_id in manifest.get("datasets", {})


def raise_if_locked(dataset_id: str, context: Context = "training") -> None:
    """Raise LockedDatasetError if dataset_id is locked for the given
    context. A no-op (returns normally) if the dataset is not in the
    manifest, or if the manifest's policy for that context is explicitly
    True — but the shipped manifest's policy block has every context set
    False, and there is no code path here that lets a caller override
    that from outside the manifest file itself."""
    manifest = _load_manifest()
    datasets = manifest.get("datasets", {})
    if dataset_id not in datasets:
        return

    policy = manifest.get("policy", {})
    policy_key = _CONTEXT_TO_POLICY_KEY.get(context)
    allowed = policy.get(policy_key, False) if policy_key else False

    if not allowed:
        entry = datasets[dataset_id]
        raise LockedDatasetError(
            f"Dataset {dataset_id!r} is LOCKED_EVALUATION and cannot be used "
            f"for {context!r}. reason={entry.get('reason', 'no reason recorded')}. "
            f"See data/catalog/locked_evaluation_manifest.json and "
            f"docs/datasets/EXTERNAL_EVALUATION_DATA.md."
        )


def locked_dataset_ids() -> list[str]:
    """All dataset_ids currently declared locked, regardless of context."""
    manifest = _load_manifest()
    return sorted(manifest.get("datasets", {}).keys())
