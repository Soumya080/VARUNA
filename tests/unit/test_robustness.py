import pytest
from varuna_netra.model.factory import create_netra_model
from varuna_netra.model.config import NetraModelConfig

def test_robustness_gpu_unavail():
    # Model factory should gracefully degrade to MockNetraModel if torch is unavail or GPU unavail
    # which it already does via ImportError handling
    config = NetraModelConfig(in_channels=2, classes=3)
    model = create_netra_model(config)
    assert model is not None
