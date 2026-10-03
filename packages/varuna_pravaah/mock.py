import numpy as np
import tempfile
from pathlib import Path
from typing import Optional

from varuna_contracts.schemas import SlickDetection, ForwardForecast
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_pravaah.protocol import PravaahProvider
from varuna_pravaah.coastline import check_landfall

class MockPravaahProvider(PravaahProvider):
    
    MOCK_VERSION = "mock-v1"
    
    def forecast_drift(self, slick: SlickDetection, forcing_path: Optional[str],
                       horizon_hours: float, envelope: EvidenceEnvelope) -> ForwardForecast:
        rng = np.random.default_rng(hash(slick.slick_id) % 2**31)
        n_particles = 50
        n_steps = int(horizon_hours * 4)  # 15-min steps

        # Simple drift: northeast at 0.5 km/h + noise
        lons = np.zeros((n_particles, n_steps + 1))
        lats = np.zeros((n_particles, n_steps + 1))
        lons[:, 0] = rng.normal(slick.centroid.lon, 0.01, n_particles)
        lats[:, 0] = rng.normal(slick.centroid.lat, 0.01, n_particles)

        for t in range(n_steps):
            lons[:, t+1] = lons[:, t] + 0.005 + rng.normal(0, 0.002, n_particles)
            lats[:, t+1] = lats[:, t] + 0.003 + rng.normal(0, 0.002, n_particles)

        # Save trajectory .npz
        temp_dir = Path(tempfile.gettempdir()) / "varuna_mocks"
        temp_dir.mkdir(parents=True, exist_ok=True)
        traj_path = temp_dir / f"pravaah_mock_{slick.slick_id}.npz"
        np.savez(traj_path, lons=lons, lats=lats)

        # Check landfall using final positions
        landfalls = check_landfall(lons[:, -1], lats[:, -1])

        forecast_id = f"fcast-{slick.slick_id}"
        # ADR-0009: do NOT `envelope.derive(...)` from the caller's envelope
        # here. derive() only ever worsens mode -- it has no mechanism to
        # force a *better* input down to SIMULATED, so if a caller ever
        # passed a REAL-mode envelope into this Mock provider, derive()
        # would let entirely fabricated trajectory positions (fixed
        # northeast-drift + noise, no physics) inherit a REAL claim. A mock
        # provider is itself the originating producer of synthetic data --
        # the same class of case ADR-0006 already handles at the
        # SourceAdapter boundary by hardcoding SIMULATED rather than
        # deriving it. Build a fresh envelope instead, unconditionally
        # SIMULATED, regardless of what the caller supplied.
        out_envelope = EvidenceEnvelope(
            artifact_id=forecast_id,
            case_id=envelope.case_id,
            parent_artifact_ids=[envelope.artifact_id],
            produced_by="pravaah_mock",
            model_version=self.get_model_version(),
            provenance=Provenance(source_id="pravaah.mock", notes="fabricated drift, no real forcing"),
            mode=EvidenceMode.SIMULATED,
        )
        return ForwardForecast(
            forecast_id=forecast_id,
            slick_id=slick.slick_id,
            horizon_hours=horizon_hours,
            landfalls=landfalls,
            trajectory_path=str(traj_path),
            envelope=out_envelope,
        )

    def get_model_version(self) -> str:
        return self.MOCK_VERSION
