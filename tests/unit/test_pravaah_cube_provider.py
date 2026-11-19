"""Tests for CubeBackedPravaahProvider — the real-forcing PRAVAAH boundary.
Uses a fully synthetic in-memory ForcingCube (no real ERA5/CMEMS file I/O)."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from varuna_contracts.evidence import (
    EvidenceEnvelope,
    EvidenceMode,
    Provenance,
    QualityMetrics,
    TrustState,
    ValidityState,
)
from varuna_contracts.schemas import BBox, GeoPoint, SlickClass, SlickDetection
from varuna_data_eng.schemas.forcing import (
    ForcingCube,
    ForcingSource,
    ForcingVariable,
    SpatialCoverageStatus,
    TimeSeriesStatus,
)
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_pravaah.cube_provider import CubeBackedPravaahProvider


def _make_cube(n_time=5):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(hours=i) for i in range(n_time)]
    return ForcingCube(
        cube_id="test-current-cube",
        source=ForcingSource.CMEMS_ANALYSIS,
        product_id="test",
        variables=[ForcingVariable(name="uo", unit="m/s"), ForcingVariable(name="vo", unit="m/s")],
        time_coords=times,
        lat_coords=[10.0, 20.0],
        lon_coords=[70.0, 80.0],
        grid_resolution_deg=10.0,
        temporal_resolution_hours=1.0,
        data_path="/dev/null",
        crs="EPSG:4326",
        bbox=BBox(min_lon=70.0, min_lat=10.0, max_lon=80.0, max_lat=20.0),
        time_range=(times[0], times[-1]),
        file_checksum="deadbeef",
        file_size_bytes=1,
        provenance=DataProvenance(source_id="test", adapter_id="test", license="test"),
        time_series_status=TimeSeriesStatus.SUFFICIENT,
        spatial_coverage_status=SpatialCoverageStatus.FULL,
    )


def _make_slick(lon=75.0, lat=15.0, obs_time=None):
    obs_time = obs_time or datetime(2026, 1, 1, 1, 0, tzinfo=UTC)
    return SlickDetection(
        slick_id="slick-cube-01", scene_id="scene-01", observation_time=obs_time,
        classification=SlickClass.OIL, confidence=0.9, mask_path="mock.tif",
        centroid=GeoPoint(lon=lon, lat=lat),
        bbox=BBox(min_lon=lon - 0.1, min_lat=lat - 0.1, max_lon=lon + 0.1, max_lat=lat + 0.1),
        area_km2=5.0, perimeter_km=10.0, elongation=2.0, orientation_deg=45.0,
        age_prior_mean_hours=24.0, age_prior_std_hours=12.0,
        mean_wind_speed_ms=5.0, netra_model_version="mock-v1",
    )


def _make_envelope():
    return EvidenceEnvelope(
        artifact_id="test-env-01", produced_by="test", trust=TrustState.TRUSTED,
        validity_state=ValidityState.VALID, quality=QualityMetrics(model_confidence=1.0),
        provenance=Provenance(source_id="test"), mode=EvidenceMode.SIMULATED,
    )


def test_rejects_insufficient_cube_at_construction():
    # A single-timestep cube can't even be pydantic-constructed with
    # time_series_status=SUFFICIENT (the schema validator rejects that
    # combination) — build it directly as INSUFFICIENT instead.
    base = datetime(2026, 1, 1, tzinfo=UTC)
    insufficient = ForcingCube(
        cube_id="insufficient", source=ForcingSource.CMEMS_ANALYSIS, product_id="test",
        variables=[ForcingVariable(name="uo", unit="m/s"), ForcingVariable(name="vo", unit="m/s")],
        time_coords=[base], lat_coords=[10.0, 20.0], lon_coords=[70.0, 80.0],
        grid_resolution_deg=10.0, temporal_resolution_hours=1.0, data_path="/dev/null",
        crs="EPSG:4326", bbox=BBox(min_lon=70.0, min_lat=10.0, max_lon=80.0, max_lat=20.0),
        time_range=(base, base), file_checksum="x", file_size_bytes=1,
        provenance=DataProvenance(source_id="test", adapter_id="test", license="test"),
        time_series_status=TimeSeriesStatus.INSUFFICIENT, spatial_coverage_status=SpatialCoverageStatus.FULL,
    )
    with pytest.raises(ValueError, match="insufficient"):
        CubeBackedPravaahProvider(insufficient, np.zeros((2, 2)), np.zeros((2, 2)))


def test_forecast_produces_trajectory_and_lands_landfall_check():
    cube = _make_cube(n_time=5)
    u_grid = np.ones((5, 2, 2)) * 0.5   # eastward current
    v_grid = np.ones((5, 2, 2)) * 0.2
    provider = CubeBackedPravaahProvider(cube, u_grid, v_grid)

    slick = _make_slick(lon=75.0, lat=15.0, obs_time=datetime(2026, 1, 1, 0, 30, tzinfo=UTC))
    env = _make_envelope()
    forecast = provider.forecast_drift(slick, None, horizon_hours=2.0, envelope=env)

    assert forecast.horizon_hours == 2.0
    assert Path(forecast.trajectory_path).exists()
    data = np.load(forecast.trajectory_path)
    assert data["lons"].shape[0] == 50  # n_particles
    # particles should have moved in +lon direction under eastward current
    assert np.mean(data["lons"][:, -1]) > np.mean(data["lons"][:, 0])


def test_real_forecast_propagates_real_evidence_mode_and_provenance():
    """
    ADR-0009 / Track 2 Task 7: a real current field driving PRAVAAH must
    surface evidence_mode/provenance/case_id on the resulting
    ForwardForecast, unlike CubeBackedPravaahProvider previously accepting
    (and silently dropping) the `envelope` parameter entirely.
    """
    cube = _make_cube(n_time=5)
    u_grid = np.ones((5, 2, 2)) * 0.5
    v_grid = np.ones((5, 2, 2)) * 0.2
    provider = CubeBackedPravaahProvider(cube, u_grid, v_grid)

    slick = _make_slick(lon=75.0, lat=15.0, obs_time=datetime(2026, 1, 1, 0, 30, tzinfo=UTC))
    real_env = EvidenceEnvelope(
        artifact_id="forcing-env-01", case_id="case-real-01", produced_by="cube_field",
        provenance=Provenance(source_id="cmems.glorys12v1"), mode=EvidenceMode.REAL,
    )
    forecast = provider.forecast_drift(slick, None, horizon_hours=2.0, envelope=real_env)

    assert forecast.envelope.mode is EvidenceMode.REAL
    assert forecast.envelope.case_id == "case-real-01"
    # .derive()'s own convention (unrelated to this change): provenance.source_id
    # names the immediate producer of THIS artifact, not the upstream source --
    # lineage back to the real forcing input travels via parent_artifact_ids.
    assert forecast.envelope.provenance.source_id == "pravaah_cube_provider"
    assert "forcing-env-01" in forecast.envelope.parent_artifact_ids
    assert forecast.envelope.model_version == provider.get_model_version()


def test_out_of_domain_mid_trajectory_freezes_not_crashes():
    cube = _make_cube(n_time=5)
    u_grid = np.ones((5, 2, 2)) * 50.0  # unrealistically large current, pushes particles out of domain fast
    v_grid = np.zeros((5, 2, 2))
    provider = CubeBackedPravaahProvider(cube, u_grid, v_grid)

    slick = _make_slick(lon=79.9, lat=15.0, obs_time=datetime(2026, 1, 1, 0, 30, tzinfo=UTC))
    env = _make_envelope()
    # Must not raise even though particles will exit the cube's lon=[70,80] domain.
    forecast = provider.forecast_drift(slick, None, horizon_hours=2.0, envelope=env)
    assert forecast.horizon_hours == 2.0
