"""
VARUNA — real marine-data freshness reporting (Phase 9, Tier 1).

Answers "how fresh is this, actually" honestly, using real file metadata —
NOT a live feed and NEVER labelled as one. Confirmed directly this session:
`Era5Adapter`/`CmemsAdapter`/the AIS bronze path all read pre-fetched local
files ("Live remote fetch is out of scope here" — era5.py's own docstring).
ERA5 is additionally a reanalysis product with an inherent ~5-day latency
regardless of fetch method; it can never honestly be "live."

Freshness is computed two ways, whichever is derivable:
  1. The file's own declared valid-time range, when it's embedded in the
     filename convention already used by this repo's real MC20 acquisition
     (e.g. `era5_mc20_2023-01-11_to_2023-01-17.nc`) — the scientifically
     meaningful number (how old is the DATA, not the download).
  2. Falling back to the file's mtime on disk (when is downloaded, at
     least, for real) when no valid-time range can be parsed.

No network calls, no new adapter classes, no new dependency — this module
only stats real files that are already part of this repo's data layout.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_DATE_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class SourceFreshness:
    source_id: str
    tier: str  # "archival" | "reanalysis" | "not_configured"
    found: bool
    file_path: str | None
    data_as_of: datetime | None       # the data's own declared valid-time end, when derivable
    file_mtime: datetime | None       # when the file was actually written to disk
    age_days: float | None            # age of data_as_of (preferred) or file_mtime, whichever exists
    honest_label: str                 # the exact phrase Phase 9 requires — never rounds up to "live"


def _parse_date_range_from_name(path: Path) -> datetime | None:
    m = _DATE_RANGE_RE.search(path.stem)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(2), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _newest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    candidates = sorted(directory.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _freshness_for(source_id: str, tier: str, directory: Path, pattern: str,
                    label_prefix: str) -> SourceFreshness:
    f = _newest_file(directory, pattern)
    if f is None:
        return SourceFreshness(
            source_id=source_id, tier="not_configured", found=False, file_path=None,
            data_as_of=None, file_mtime=None, age_days=None,
            honest_label=f"{label_prefix}: NOT_CONFIGURED — no local file found under {directory}",
        )

    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
    data_as_of = _parse_date_range_from_name(f)
    reference = data_as_of or mtime
    age_days = (datetime.now(timezone.utc) - reference).total_seconds() / 86400.0

    if data_as_of is not None:
        label = f"{label_prefix}: {tier}, data valid through {data_as_of.date().isoformat()} ({age_days:.1f} days ago)"
    else:
        label = f"{label_prefix}: {tier}, file on disk since {mtime.date().isoformat()} ({age_days:.1f} days ago) — no embedded valid-time range to read"

    try:
        display_path = str(f.relative_to(_REPO_ROOT))
    except ValueError:
        # Not under the repo root (e.g. a configured external data dir, or a
        # test fixture on a different drive) -- fall back to the absolute
        # path rather than crashing on a perfectly valid file location.
        display_path = str(f)

    return SourceFreshness(
        source_id=source_id, tier=tier, found=True, file_path=display_path,
        data_as_of=data_as_of, file_mtime=mtime, age_days=round(age_days, 2), honest_label=label,
    )


def marine_context_report() -> dict[str, SourceFreshness]:
    """Real freshness for the three local marine-data sources this
    deployment actually has file access to. Each is honestly `archival`
    (AIS/CMEMS: a real past snapshot) or `reanalysis` (ERA5: inherently
    ~5-day-latency by product design, never live regardless of fetch
    method) — never labelled `live` or `real-time`, because none of them
    are, confirmed by reading the real adapters' own docstrings this
    session."""
    return {
        "era5": _freshness_for(
            "era5", "reanalysis", _REPO_ROOT / "data" / "raw" / "era5_mc20", "*.nc",
            "ERA5 (reanalysis, ~5-day inherent latency by product design)",
        ),
        "cmems": _freshness_for(
            "cmems", "archival", _REPO_ROOT / "data" / "raw" / "cmems_mc20_timeseries", "*.nc",
            "CMEMS (local snapshot)",
        ),
        "ais": _freshness_for(
            "ais", "archival", _REPO_ROOT / "data" / "raw" / "ais", "*.csv",
            "AIS (bronze archive)",
        ),
    }
