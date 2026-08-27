import pytest
import numpy as np
from datetime import datetime, timezone
from varuna_data_eng.schemas.normalization import NormalizationRecord, ChannelStats
from varuna_netra.preprocessing import normalize_sar_tile

def test_normalize_sar_tile_uses_record():
    # Setup record
    record = NormalizationRecord(
        dataset_version="v1",
        sensor="SENTINEL_1",
        channels={
            "VV": ChannelStats(mean=-10.0, std=3.0, min=-30.0, max=0.0, p2=-20.0, p98=-5.0),
            "VH": ChannelStats(mean=-15.0, std=4.0, min=-35.0, max=0.0, p2=-25.0, p98=-8.0)
        },
        method="p2_p98",
        n_samples=100,
        computed_at=datetime.now(timezone.utc),
        checksum="123"
    )
    
    vv = np.array([[-20.0, -12.5], [-5.0, 0.0]])
    vh = np.array([[-25.0, -16.5], [-8.0, 0.0]])
    
    out = normalize_sar_tile(vv, vh, record)
    
    assert out.shape == (3, 2, 2)
    # VV check
    # lo = -20, hi = -5. diff = 15
    # (-20) -> 0.0
    # (-12.5) -> 7.5/15 = 0.5
    # (-5) -> 1.0
    # (0.0) -> clipped to 1.0
    np.testing.assert_allclose(out[0], np.array([[0.0, 0.5], [1.0, 1.0]]), atol=1e-5)
    
    # VH check
    # lo = -25, hi = -8. diff = 17
    # (-25) -> 0.0
    # (-16.5) -> 8.5/17 = 0.5
    # (-8) -> 1.0
    # (0) -> 1.0
    np.testing.assert_allclose(out[1], np.array([[0.0, 0.5], [1.0, 1.0]]), atol=1e-5)
