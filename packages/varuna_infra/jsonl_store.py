"""
VARUNA — generic JSONL-backed persistence.

Generalises the pattern already proven by `varuna_smriti.memory.SmritiStore`:
an in-memory dict/list of pydantic models, mirrored to a JSON-lines file,
rewritten atomically on every write. Deliberately not a database — the whole
local stack runs with `USE_POSTGRES=false`, and the point here is that a
restart must not erase human decisions, not that we need query planning.

Two shapes, because the callers genuinely need different ones:

  * `KeyedJsonlStore`  — dict-like, one record per key, last write wins.
                         Backs the alert store and the mission repository.
  * `AppendJsonlStore` — append-only log, order preserved.
                         Backs the authorization audit logs, where losing or
                         reordering entries would corrupt the record of who
                         was allowed to do what.

Failure posture: a corrupt line is skipped and *counted* (`load_errors`)
rather than silently swallowed or allowed to crash the process — losing one
malformed record must not cost you every acknowledgement ever made. Callers
can surface `load_errors` on a health endpoint.

Writes are atomic (temp file + `os.replace`). A half-written state file is
worse than a missing one, because it looks valid.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Callable, Generic, Iterable, Iterator, TypeVar

T = TypeVar("T")


def _atomic_write(path: Path, lines: Iterable[str]) -> None:
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False,
            dir=str(path.parent), suffix=".tmp",
        ) as fh:
            tmp = Path(fh.name)
            for line in lines:
                fh.write(line + "\n")
        tmp.replace(path)
        tmp = None
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


class _BaseJsonlStore(Generic[T]):
    def __init__(self, path: str | Path, *,
                 loads: Callable[[str], T], dumps: Callable[[T], str]) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._loads = loads
        self._dumps = dumps
        #: Count of lines that failed to parse on load. Non-zero means the
        #: state file has been damaged — surface it, do not hide it.
        self.load_errors: int = 0

    @property
    def path(self) -> Path:
        return self._path

    def _read_lines(self) -> Iterator[T]:
        if not self._path.exists():
            return
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield self._loads(raw)
            except Exception:
                self.load_errors += 1
                continue


class KeyedJsonlStore(_BaseJsonlStore[T]):
    """One record per key; later lines win. Mirrors `SmritiStore`'s semantics."""

    def __init__(self, path: str | Path, *, key: Callable[[T], str],
                 loads: Callable[[str], T], dumps: Callable[[T], str]) -> None:
        super().__init__(path, loads=loads, dumps=dumps)
        self._key = key
        self._items: dict[str, T] = {}
        for item in self._read_lines():
            self._items[self._key(item)] = item

    def put(self, item: T) -> T:
        self._items[self._key(item)] = item
        self._flush()
        return item

    def get(self, key: str) -> T | None:
        return self._items.get(key)

    def all(self) -> list[T]:
        return list(self._items.values())

    def delete(self, key: str) -> bool:
        existed = self._items.pop(key, None) is not None
        if existed:
            self._flush()
        return existed

    def clear(self) -> None:
        """Drop everything, including on disk. Used by tests, never by the
        product — an operator must not be able to erase the record."""
        self._items.clear()
        self._flush()

    def __len__(self) -> int:
        return len(self._items)

    def _flush(self) -> None:
        _atomic_write(self._path,
                      (self._dumps(v) for _, v in sorted(self._items.items())))


class AppendJsonlStore(_BaseJsonlStore[T]):
    """Append-only, order-preserving. For audit trails."""

    def __init__(self, path: str | Path, *,
                 loads: Callable[[str], T], dumps: Callable[[T], str]) -> None:
        super().__init__(path, loads=loads, dumps=dumps)
        self._items: list[T] = list(self._read_lines())

    def append(self, item: T) -> T:
        self._items.append(item)
        # Genuine append — no rewrite. An audit log must never be rewritten
        # wholesale, because a crash mid-rewrite could lose prior entries.
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(self._dumps(item) + "\n")
        return item

    def all(self) -> list[T]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()
        _atomic_write(self._path, [])

    def __len__(self) -> int:
        return len(self._items)


def state_dir(repo_root: Path | None = None) -> Path:
    """Where persisted operational state lives.

    Defaults to `<repo>/reports/state`, beside the existing SMRITI JSONL, so
    there is one obvious place to look and one place to delete to reset a
    demo.

    `VARUNA_STATE_DIR` overrides it. That override is not decoration: without
    it a test run loads — and mutates — the same files the live API is using,
    which silently coupled the test suite to whatever had been clicked in the
    cockpit. It also lets a deployment put state on a different volume.
    """
    import os

    override = os.environ.get("VARUNA_STATE_DIR")
    if override:
        d = Path(override)
    else:
        root = repo_root or Path(__file__).resolve().parents[2]
        d = root / "reports" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d
