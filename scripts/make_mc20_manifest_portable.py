"""Rewrite absolute machine paths in the MC20 event manifest as repo-relative.

The MC20 event directory is the one piece of `data/gold` small enough to ship
(19 MB of a 131 GB tree), and CHHAYA reads it at request time. Its manifest
currently hardcodes `D:\\ROUTER(DATASETS)\\VARUNA\\...`, which breaks on any
other machine. This converts every such path to a POSIX repo-relative one and
records the original root under `_portability` so the provenance of the
rewrite is auditable.

Idempotent: running it twice is a no-op. Pass --check to report without
writing (exit 1 if absolute paths remain).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "gold" / "events" / "mc20_v0_1" / "manifest.json"


def _looks_absolute(s: str) -> bool:
    return len(s) > 2 and s[1] == ":" and s[2] in ("\\", "/")


def _to_relative(s: str, repo: Path) -> str | None:
    """Return a POSIX repo-relative path, or None if `s` is not under repo."""
    candidate = Path(s.replace("\\", "/"))
    try:
        return candidate.resolve().relative_to(repo.resolve()).as_posix()
    except Exception:
        return None


def convert(obj, repo: Path, found: list[tuple[str, str]], path: str = ""):
    if isinstance(obj, dict):
        # `_portability` records where the rewrite happened; its absolute
        # root is provenance, not a path the code resolves. Never rewrite it
        # and never report it as un-portable.
        return {k: (v if k == "_portability" else convert(v, repo, found, f"{path}/{k}"))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert(v, repo, found, f"{path}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, str) and _looks_absolute(obj):
        rel = _to_relative(obj, repo)
        if rel is not None:
            found.append((path, obj))
            return rel
        # Absolute but outside the repo (e.g. a raw download dir) — cannot be
        # made portable. Leave it and report it rather than silently mangling.
        found.append((path, f"OUTSIDE-REPO {obj}"))
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, do not write")
    args = ap.parse_args()

    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST}")
        return 1

    original = json.loads(MANIFEST.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    converted = convert(original, REPO, found)

    outside = [f for f in found if f[1].startswith("OUTSIDE-REPO")]
    inside = [f for f in found if not f[1].startswith("OUTSIDE-REPO")]

    print(f"absolute paths found: {len(found)}  (repo-relative-able: {len(inside)}, "
          f"outside repo: {len(outside)})")
    for key, val in found:
        print(f"  {key} = {val[:100]}")

    if args.check:
        return 1 if found else 0

    if not found:
        print("already portable — nothing to do")
        return 0

    converted["_portability"] = {
        "rewritten_by": "scripts/make_mc20_manifest_portable.py",
        "original_repo_root": str(REPO),
        "note": ("Absolute paths were rewritten as POSIX repo-relative so this event "
                 "directory can be committed and used on any machine. Resolve them "
                 "against the repository root."),
        "n_rewritten": len(inside),
        "n_left_absolute_outside_repo": len(outside),
    }
    MANIFEST.write_text(json.dumps(converted, indent=2) + "\n", encoding="utf-8")
    print(f"rewrote {len(inside)} path(s) -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
