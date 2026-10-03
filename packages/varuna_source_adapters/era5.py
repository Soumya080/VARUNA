"""Real ERA5 SourceAdapter — reads local ERA5 GRIB files via forcing_readers.

Replaces the previous 5-line stub (fetch_wind() -> {"data": "mock_era5_data"}).
This adapter never contacts the CDS API; it reads GRIB files already present
under a configured local directory. Live remote fetch is out of scope here —
see docs/datasets/AIS_ACQUISITION_SPEC.md-style specs for what a live fetch
would need; this adapter only covers "read what's already on disk, honestly".
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from varuna_contracts.evidence import Provenance
from varuna_data_eng.schemas.forcing import ForcingCube
from varuna_source_adapters.forcing_readers import read_era5_grib
from varuna_source_adapters.protocol import FetchResult, SourceAdapter, SourceQuery


class Era5Adapter(SourceAdapter):
    """Reads real local ERA5 GRIB files. is_simulated=False — this is real data,
    not a mock, even though it is read from disk rather than fetched live."""

    ADAPTER_VERSION = "real-v1"

    def __init__(self, grib_dir: Path | str):
        self._grib_dir = Path(grib_dir)

    @property
    def source_id(self) -> str:
        return "era5.real"

    def health_check(self) -> bool:
        return self._grib_dir.exists() and any(self._grib_dir.glob("*.grib"))

    def build_cube(self, grib_path: Path, reference_bbox=None) -> ForcingCube:
        """Direct access to a validated ForcingCube for one file, bypassing
        the SourceQuery matching below. Used by tests and by callers that
        already know exactly which file they want."""
        return read_era5_grib(grib_path, reference_bbox=reference_bbox, adapter_id=self.source_id)

    def fetch(self, query: SourceQuery) -> FetchResult:
        if not self._grib_dir.exists():
            raise FileNotFoundError(f"ERA5 directory not found: {self._grib_dir}")
        candidates = sorted(self._grib_dir.glob("*.grib"))
        if not candidates:
            raise FileNotFoundError(f"No .grib files found under {self._grib_dir}")

        # No spatial/temporal index exists yet over the local GRIB set (see
        # audit: the 3 files span 3 different bboxes). Until that index is
        # built, fetch() picks the first file and reports its actual
        # coverage honestly via the ForcingCube it returns — it does not
        # pretend to have matched `query`.
        chosen = candidates[0]
        cube = read_era5_grib(chosen, reference_bbox=query.bbox, adapter_id=self.source_id)

        return FetchResult(
            artifact_path=cube.data_path,
            provenance=Provenance(
                source_id=self.source_id,
                source_version=self.ADAPTER_VERSION,
                notes=(
                    f"Read local file {chosen.name}; spatial_coverage_status="
                    f"{cube.spatial_coverage_status.value}, time_series_status="
                    f"{cube.time_series_status.value}. No spatial index over "
                    f"multiple GRIB chunks yet — see forcing_readers.py."
                ),
            ),
            is_simulated=False,
            fetched_at=datetime.now(UTC),
        )
