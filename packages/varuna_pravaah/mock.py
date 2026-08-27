import numpy as np
import tempfile
from pathlib import Path
from typing import Optional

from varuna_contracts.schemas import SlickDetection, ForwardForecast
from varuna_contracts.evidence import EvidenceEnvelope
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

        return ForwardForecast(
            forecast_id=f"fcast-{slick.slick_id}",
            slick_id=slick.slick_id,
            horizon_hours=horizon_hours,
            landfalls=landfalls,
            trajectory_path=str(traj_path),
        )

    def get_model_version(self) -> str:
        return self.MOCK_VERSION
