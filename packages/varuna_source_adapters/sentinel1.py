"""Real Sentinel-1 SourceAdapter — reads local SAFE products on disk.

Replaces the previous 5-line stub (`fetch_scene()` returning a hardcoded
`{"id": scene_id, "data": "mock_s1_data"}`, which did not even implement
`SourceAdapter`). Mirrors the ERA5/CMEMS adapters' honest pattern exactly:
this never contacts Copernicus/ASF/any live acquisition API — it reads a
`.SAFE` product already present under a configured local directory (e.g.
`data/raw/sentinel1_grd/<event>/<scene>.SAFE`, as produced by
`scripts/acquire_mc20_sar.py`). Live remote acquisition is out of scope
here; see module docstring pattern in `era5.py`/`copernicus_marine.py`.

This adapter does NOT run radiometric calibration or NETRA tiling — that
is `varuna_data_eng.preprocessing.sentinel1_grd_calibration` /
`varuna_integration.netra_boundary`'s job, and duplicating it here would
be exactly the kind of "silently alter NETRA input semantics" the task
prohibits. `fetch()` returns the raw SAFE product's own path plus real,
parsed scene metadata; a caller wanting a NETRA-ready tile calls the
calibration pipeline separately, unchanged.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from varuna_contracts.evidence import Provenance
from varuna_source_adapters.protocol import FetchResult, SourceAdapter, SourceQuery

_START_RE = re.compile(r"<safe:startTime[^>]*>([^<]*)</safe:startTime>")
_STOP_RE = re.compile(r"<safe:stopTime[^>]*>([^<]*)</safe:stopTime>")
_PRODUCT_TYPE_RE = re.compile(r"<s1sarl1:productType[^>]*>([^<]*)</s1sarl1:productType>")


@dataclass(frozen=True)
class Sentinel1SceneMetadata:
    """What was actually parsed from the SAFE product's own manifest —
    never invented. Any field this SAFE product's manifest doesn't carry
    stays `None` rather than being guessed."""
    scene_id: str
    acquisition_start: datetime | None
    acquisition_stop: datetime | None
    product_type: str | None
    polarizations: tuple[str, ...]
    manifest_sha256: str
    safe_path: str


def _parse_scene_metadata(safe_dir: Path) -> Sentinel1SceneMetadata:
    manifest_path = safe_dir / "manifest.safe"
    text = manifest_path.read_text(encoding="utf-8", errors="replace")

    def _parse_dt(m: re.Match | None) -> datetime | None:
        if not m:
            return None
        # SAFE timestamps are naive UTC ("2023-01-15T00:02:06.898608").
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC)

    start = _parse_dt(_START_RE.search(text))
    stop = _parse_dt(_STOP_RE.search(text))
    ptype_m = _PRODUCT_TYPE_RE.search(text)
    product_type = ptype_m.group(1) if ptype_m else None

    # Polarization is not reliably tagged in every manifest.safe variant this
    # codebase has seen (see the empty s1sarl1:polarisation probe in
    # reconnaissance) — measurement filenames encode it unambiguously
    # instead (S1 naming convention: ...-grd-<pol>-...tiff).
    measurement_dir = safe_dir / "measurement"
    pols = tuple(sorted({
        "VV" if "-vv-" in p.name.lower() else "VH" if "-vh-" in p.name.lower()
        else "HH" if "-hh-" in p.name.lower() else "HV" if "-hv-" in p.name.lower()
        else "UNKNOWN"
        for p in measurement_dir.glob("*.tiff")
    })) if measurement_dir.exists() else ()

    return Sentinel1SceneMetadata(
        scene_id=safe_dir.stem,
        acquisition_start=start,
        acquisition_stop=stop,
        product_type=product_type,
        polarizations=pols,
        # Hashing the manifest (KB-scale), not the measurement GeoTIFFs
        # (multi-GB) — a lightweight integrity/identity checksum, not a
        # full-product checksum. Documented as such in Provenance.notes.
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        safe_path=str(safe_dir),
    )


class Sentinel1Adapter(SourceAdapter):
    """Reads real local Sentinel-1 SAFE products. `is_simulated=False` —
    this is a real acquired scene, not a mock, even though it is read from
    disk rather than fetched live from a provider API."""

    ADAPTER_VERSION = "real-v1"

    def __init__(self, safe_root_dir: Path | str):
        self._root = Path(safe_root_dir)

    @property
    def source_id(self) -> str:
        return "sentinel1.real"

    def _candidates(self) -> list[Path]:
        if not self._root.exists():
            return []
        return sorted(p for p in self._root.rglob("*.SAFE") if (p / "manifest.safe").exists())

    def health_check(self) -> bool:
        return bool(self._candidates())

    def scene_metadata(self, safe_dir: Path) -> Sentinel1SceneMetadata:
        """Direct access for a caller that already knows which SAFE product
        it wants (mirrors `Era5Adapter.build_cube`'s bypass-the-query path)."""
        return _parse_scene_metadata(safe_dir)

    def fetch(self, query: SourceQuery) -> FetchResult:
        candidates = self._candidates()
        if not candidates:
            raise FileNotFoundError(f"No .SAFE products found under {self._root}")

        # No spatial/temporal index over multiple local SAFE products exists
        # yet (same honest gap as Era5Adapter/CmemsAdapter) — picks the
        # first candidate and reports its ACTUAL acquisition window, never
        # pretending it matches `query`.
        chosen = candidates[0]
        meta = _parse_scene_metadata(chosen)

        return FetchResult(
            artifact_path=meta.safe_path,
            provenance=Provenance(
                source_id=self.source_id,
                source_version=self.ADAPTER_VERSION,
                notes=(
                    f"scene_id={meta.scene_id}; product_type={meta.product_type}; "
                    f"polarizations={','.join(meta.polarizations) or 'unknown'}; "
                    f"acquisition={meta.acquisition_start}..{meta.acquisition_stop}; "
                    f"manifest_sha256={meta.manifest_sha256} (manifest.safe only, "
                    "NOT the full measurement GeoTIFFs — those are multi-GB and "
                    "not hashed here). No spatial/temporal index over multiple "
                    "local SAFE products yet — see forcing_readers.py for the "
                    "same gap on ERA5/CMEMS. Radiometric calibration and NETRA "
                    "tiling are NOT performed by this adapter — see "
                    "varuna_data_eng.preprocessing.sentinel1_grd_calibration."
                ),
            ),
            is_simulated=False,
            fetched_at=datetime.now(UTC),
        )
