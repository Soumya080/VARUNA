import sys
import enum
import datetime

# Monkeypatch for Python 3.10 support
if not hasattr(enum, "StrEnum"):
    class StrEnum(str, enum.Enum):
        pass
    enum.StrEnum = StrEnum

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc


# --- optional heavy extras -------------------------------------------------
# torch and friends live in the `ml` extra, not the base install. Several NETRA
# test modules reach torch at import time, so on a plain `pip install -e .`
# pytest aborted with "Interrupted: N errors during collection" and ran NOTHING
# -- a teammate verifying a fresh clone saw zero tests, not a passing suite.
#
# Skip only modules that genuinely cannot be imported. Where the ml extra IS
# installed (the training machine) this whole guard is inert: collection there
# is unchanged at 745 tests, so no assertion is weakened or silently dropped.
import importlib.util
import re


def _missing(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is None
    except (ImportError, ValueError):
        return True


_OPTIONAL = {name for name in ("torch", "mlflow", "segmentation_models_pytorch")
             if _missing(name)}

# First-party modules that import torch at module scope. A test file importing
# any of these fails to collect without the ml extra, even though it never
# names torch itself -- static analysis of the test file alone cannot see this,
# so the chain is listed explicitly rather than guessed at.
_TORCH_BACKED = (
    "varuna_netra.training",
    "scripts.smoke_train_netra",
    "scripts.smoke_train_chhaya",
    "scripts.lab_smoke_test",
)


def pytest_ignore_collect(collection_path, config):
    """Ignore a test module only if an optional extra it needs is absent."""
    if not _OPTIONAL or collection_path.suffix != ".py":
        return None
    try:
        src = collection_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    # Match module-scope imports only. A bare "import torch" substring search
    # would also ignore files that import it inside one test or mention it in a
    # comment, dropping every other test in the file with it --
    # tests/unit/test_mc20_event_gold.py has 17 tests and one transitive torch
    # dependency, and losing all 17 to guard one is exactly the quiet coverage
    # loss this must not cause.
    if "torch" in _OPTIONAL:
        for mod in _TORCH_BACKED:
            if re.search(r"^from " + re.escape(mod) + r"[. ]|^import "
                         + re.escape(mod) + r"\b", src, re.MULTILINE):
                return True
    for mod in _OPTIONAL:
        if re.search(r"^import " + mod + r"\b|^from " + mod + r"[. ]",
                     src, re.MULTILINE):
            return True
    return None
