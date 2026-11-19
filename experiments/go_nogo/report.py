"""Small reporting helpers for go/no-go result artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.go_nogo.sweep import render_markdown_summary


def write_summary(results_json: Path) -> Path:
    manifest = json.loads(results_json.read_text(encoding="utf-8"))
    out = results_json.with_name("SUMMARY.md")
    out.write_text(render_markdown_summary(manifest), encoding="utf-8")
    return out
