"""Compatibility helper for viewing fair go/no-go summaries.

The old visualizer depended on the invalid monolithic `core.py`. Plotting can be added
later from the new JSON/CSV artifacts; for now this module refuses to fabricate figures.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_summary(results_dir: Path) -> dict[str, object]:
    results_path = results_dir / "results.json"
    manifest = json.loads(results_path.read_text(encoding="utf-8"))
    summary = manifest.get("summary", {})
    if not isinstance(summary, dict):
        raise ValueError("results.json does not contain a summary object")
    return summary


def print_summary(results_dir: Path) -> None:
    summary = load_summary(results_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
