"""Tests for the locked-evaluation dataset guard.

Uses the real committed manifest (data/catalog/locked_evaluation_manifest.json)
for the "real dataset" tests, and a synthetic manifest (monkeypatched path)
for the policy-matrix and edge-case tests, so the edge cases don't depend
on the real manifest's exact contents staying the same shape forever."""
import json

import pytest

from varuna_data_eng.locked_evaluation_guard import (
    LockedDatasetError,
    is_locked,
    locked_dataset_ids,
    raise_if_locked,
)


def test_real_locked_datasets_are_locked():
    assert is_locked("zenodo_part3")
    assert is_locked("essd")


def test_unknown_dataset_is_not_locked():
    assert not is_locked("zenodo_part1")
    assert not is_locked("some_dataset_not_in_the_manifest")


def test_raise_if_locked_raises_for_real_locked_dataset():
    with pytest.raises(LockedDatasetError, match="zenodo_part3"):
        raise_if_locked("zenodo_part3", context="training")


def test_raise_if_locked_is_noop_for_unlocked_dataset():
    raise_if_locked("zenodo_part1", context="training")  # must not raise


def test_locked_dataset_ids_contains_both():
    ids = locked_dataset_ids()
    assert "zenodo_part3" in ids
    assert "essd" in ids


@pytest.mark.parametrize("context", [
    "training", "tuning", "normalization", "threshold_tuning", "early_stopping",
])
def test_every_context_is_blocked_for_real_locked_datasets(context):
    """The shipped manifest's policy block has every *_allowed field False —
    no context should ever be silently permitted for a locked dataset."""
    with pytest.raises(LockedDatasetError):
        raise_if_locked("essd", context=context)


def test_guard_module_never_writes_to_the_manifest(tmp_path, monkeypatch):
    """The guard is read-only: calling it must never modify the manifest file
    (or any file) on disk."""
    import varuna_data_eng.locked_evaluation_guard as guard_mod

    manifest = {
        "policy": {"training_allowed": False},
        "datasets": {"fake_locked": {"reason": "test"}},
    }
    manifest_path = tmp_path / "locked_evaluation_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(guard_mod, "_MANIFEST_PATH", manifest_path)

    before = manifest_path.read_text()
    with pytest.raises(LockedDatasetError):
        raise_if_locked("fake_locked", context="training")
    after = manifest_path.read_text()
    assert before == after


def test_missing_manifest_fails_open_to_no_locks_but_does_not_error(tmp_path, monkeypatch):
    """If the manifest file is absent entirely, the guard must not crash —
    but this means nothing is protected, which is why the manifest is
    committed to the repo rather than left optional in practice."""
    import varuna_data_eng.locked_evaluation_guard as guard_mod

    monkeypatch.setattr(guard_mod, "_MANIFEST_PATH", tmp_path / "does_not_exist.json")
    assert not is_locked("essd")
    raise_if_locked("essd", context="training")  # must not raise; nothing declared locked
