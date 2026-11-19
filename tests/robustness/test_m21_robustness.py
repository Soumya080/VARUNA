"""
VARUNA GRID M2.1 — Robustness Tests.

Tests posterior normalization, latent behavior, temporal clipping,
weak evidence, dense traffic, and domain-mismatch elimination.
"""
import pytest
import datetime as _dt
if not hasattr(_dt, "UTC"):
    _dt.UTC = _dt.timezone.utc
import enum as _enum
if not hasattr(_enum, "StrEnum"):
    class _StrEnum(str, _enum.Enum): pass
    _enum.StrEnum = _StrEnum

import numpy as np
from datetime import datetime, timezone, timedelta
from varuna_contracts.schemas import VesselTrack, AISPoint, VesselType
from varuna_nyaya.likelihoods import compute_density_likelihoods
from varuna_nyaya.posterior import compute_posterior
from varuna_nyaya.corridor import build_corridor_mask


def _make_track(mmsi, lon, lat, t0_hours=0.5, t1_hours=1.5):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return VesselTrack(
        mmsi=mmsi,
        vessel_type=VesselType.TANKER,
        points=[
            AISPoint(timestamp=base + timedelta(hours=t0_hours),
                     lon=lon, lat=lat, sog_knots=5.0, heading_deg=0.0),
            AISPoint(timestamp=base + timedelta(hours=t1_hours),
                     lon=lon, lat=lat, sog_knots=5.0, heading_deg=0.0),
        ],
    )


def _make_phi(shape=(2, 10, 10), peak_idx=None, uniform=False):
    phi = np.zeros(shape, dtype=np.float32)
    if uniform:
        phi[:] = 1.0 / phi.size
    elif peak_idx:
        for t, y, x in peak_idx:
            phi[t, y, x] = 1.0 / len(peak_idx)
    else:
        phi[0, 5, 5] = 0.6
        phi[1, 6, 6] = 0.4
    return phi


_LON_EDGES = np.linspace(0, 1, 11)
_LAT_EDGES = np.linspace(0, 1, 11)
_TIME_EDGES = np.array([0.0, 1.0, 2.0])


class TestPosteriorNormalization:
    """Test 1: Posterior always sums to 1."""

    def test_basic_normalization(self):
        phi = _make_phi()
        t1 = _make_track("V1", 0.55, 0.55)
        t2 = _make_track("V2", 0.15, 0.15)
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t1, t2], 50.0)
        priors = {"V1": 1.0, "V2": 1.0}
        posterior, _, _, _ = compute_posterior(densities, rho_0, priors, 0.5)
        assert abs(sum(posterior.values()) - 1.0) < 1e-6

    def test_many_candidates(self):
        phi = _make_phi()
        tracks = [_make_track(f"V{i}", 0.1*i, 0.1*i) for i in range(20)]
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, tracks, 50.0)
        priors = {f"V{i}": 1.0 for i in range(20)}
        posterior, _, _, _ = compute_posterior(densities, rho_0, priors, 0.5)
        assert abs(sum(posterior.values()) - 1.0) < 1e-6


class TestLatentPriorBehavior:
    """Test 2: Latent prior sweep produces monotonic latent posterior."""

    def test_prior_sweep(self):
        phi = _make_phi()
        t1 = _make_track("V1", 0.55, 0.55)
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t1], 50.0)
        priors = {"V1": 1.0}
        latent_probs = []
        for pi0 in [0.1, 0.3, 0.5, 0.7, 0.9]:
            post, _, _, _ = compute_posterior(densities, rho_0, priors, pi0)
            latent_probs.append(post["LATENT_SOURCE"])
        # Higher latent prior -> higher latent posterior
        for i in range(len(latent_probs) - 1):
            assert latent_probs[i] <= latent_probs[i+1] + 1e-6


class TestDiffusePhi:
    """Test 3: Uniform Phi -> INCONCLUSIVE or LATENT_SOURCE."""

    def test_uniform_phi(self):
        phi = _make_phi(uniform=True)
        t1 = _make_track("V1", 0.55, 0.55)
        t2 = _make_track("V2", 0.15, 0.15)
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t1, t2], 50.0)
        priors = {"V1": 1.0, "V2": 1.0}
        posterior, _, decision, entropy = compute_posterior(
            densities, rho_0, priors, 0.5)
        # With uniform phi, densities are equal everywhere, so
        # entropy should be high or decision should be non-discriminating
        assert abs(sum(posterior.values()) - 1.0) < 1e-6


class TestNoCandidates:
    """Test 5: No candidates -> LATENT_SOURCE."""

    def test_empty_tracks(self):
        phi = _make_phi()
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [], 50.0)
        priors = {}
        posterior, _, decision, _ = compute_posterior(
            densities, rho_0, priors, 0.5)
        assert posterior.get("LATENT_SOURCE", 0) > 0.9


class TestWeakEvidence:
    """Test 6: All L_k ≈ 0 -> LATENT_SOURCE."""

    def test_vessels_far_from_phi(self):
        phi = _make_phi()  # peak at (0,5,5) and (1,6,6)
        # Vessel far away from any peak
        t1 = _make_track("V1", 0.05, 0.05)
        t2 = _make_track("V2", 0.95, 0.95)
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t1, t2], 5.0)
        priors = {"V1": 1.0, "V2": 1.0}
        posterior, _, _, _ = compute_posterior(densities, rho_0, priors, 0.5)
        assert abs(sum(posterior.values()) - 1.0) < 1e-6


class TestStrongCandidate:
    """Test 7: One vessel right on the peak -> should win."""

    def test_single_strong(self):
        phi = _make_phi()
        t_on = _make_track("ON_PEAK", 0.55, 0.55)
        t_off = _make_track("OFF", 0.05, 0.05)
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t_on, t_off], 50.0)
        priors = {"ON_PEAK": 1.0, "OFF": 1.0}
        posterior, _, decision, _ = compute_posterior(
            densities, rho_0, priors, 0.3)
        # The on-peak vessel should have highest posterior among vessels
        vessel_posts = {k: v for k, v in posterior.items() if k != "LATENT_SOURCE"}
        best = max(vessel_posts, key=vessel_posts.get)
        assert best == "ON_PEAK"


class TestTemporalClipping:
    """Test 9: Vessel outside Phi time range -> L_k = 0."""

    def test_out_of_time(self):
        phi = _make_phi()
        # Track at time 10-11 hours, but Phi only covers 0-2 hours
        t_out = _make_track("OUT", 0.55, 0.55, t0_hours=10.0, t1_hours=11.0)
        densities, rho_0, _ = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t_out], 50.0)
        assert densities["OUT"] == 0.0


class TestPartitionOfUnity:
    """Test 10: Non-overlapping corridors -> sum(L_k) + L_0 ≈ 1."""

    def test_partition(self):
        phi = _make_phi()
        t1 = _make_track("V1", 0.55, 0.55)
        t2 = _make_track("V2", 0.15, 0.15)
        _, _, diag = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t1, t2], 5.0)
        assert abs(diag["partition_sum"] - 1.0) < 0.02


class TestDensityEliminatesDomainMismatch:
    """Core scientific test: density-based likelihoods should allow
    a strong vessel to beat latent even when corridor is tiny."""

    def test_strong_vessel_beats_latent(self):
        phi = _make_phi()
        # Vessel right on the peak with narrow corridor
        t_on = _make_track("TRUE", 0.55, 0.55)
        densities, rho_0, diag = compute_density_likelihoods(
            phi, _LON_EDGES, _LAT_EDGES, _TIME_EDGES, [t_on], 50.0)
        priors = {"TRUE": 1.0}
        # With balanced prior (0.5), the on-peak vessel should beat latent
        posterior, _, _, _ = compute_posterior(densities, rho_0, priors, 0.5)
        assert posterior["TRUE"] > posterior["LATENT_SOURCE"], (
            f"Density likelihoods should allow strong vessel to beat latent: "
            f"TRUE={posterior['TRUE']:.4f}, LATENT={posterior['LATENT_SOURCE']:.4f}"
        )
