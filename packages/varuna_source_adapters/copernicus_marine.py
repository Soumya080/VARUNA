"""Real CMEMS SourceAdapter — reads local CMEMS NetCDF files via forcing_readers.

Replaces the previous 5-line stub (fetch_currents() -> {"data": "mock_cmems_data"}).
Reads NetCDF files already present under a configured local directory. Both
files currently on disk are single-timestep snapshots — this adapter reports
that honestly via ForcingCube.time_series_status=insufficient rather than
pretending a snapshot is a time series.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from varuna_contracts.evidence import Provenance
from varuna_data_eng.schemas.forcing import ForcingCube
from varuna_source_adapters.forcing_readers import read_cmems_netcdf
from varuna_source_adapters.protocol import FetchResult, SourceAdapter, SourceQuery


class CmemsAdapter(SourceAdapter):
    """Reads real local CMEMS NetCDF files. is_simulated=False."""

    ADAPTER_VERSION = "real-v1"

    def __init__(self, netcdf_dir: Path | str):
        self._netcdf_dir = Path(netcdf_dir)

    @property
    def source_id(self) -> str:
        return "cmems.real"

    def health_check(self) -> bool:
        return self._netcdf_dir.exists() and any(self._netcdf_dir.rglob("*.nc"))

    def build_cube(self, netcdf_path: Path) -> ForcingCube:
        return read_cmems_netcdf(netcdf_path, adapter_id=self.source_id)

    def fetch(self, query: SourceQuery) -> FetchResult:
        if not self._netcdf_dir.exists():
            raise FileNotFoundError(f"CMEMS directory not found: {self._netcdf_dir}")
        candidates = sorted(self._netcdf_dir.rglob("*.nc"))
        if not candidates:
            raise FileNotFoundError(f"No .nc files found under {self._netcdf_dir}")

        chosen = candidates[0]
        cube = read_cmems_netcdf(chosen, adapter_id=self.source_id)

        return FetchResult(
            artifact_path=cube.data_path,
            provenance=Provenance(
                source_id=self.source_id,
                source_version=self.ADAPTER_VERSION,
                notes=(
                    f"Read local file {chosen.name}; time_series_status="
                    f"{cube.time_series_status.value}. Single-timestep files "
                    f"are returned as-is, never silently treated as a time "
                    f"series — callers must check "
                    f"ForcingCube.assert_usable_for_advection()."
                ),
            ),
            is_simulated=False,
            fetched_at=datetime.now(UTC),
        )
