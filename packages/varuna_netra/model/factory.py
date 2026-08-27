from typing import Any
from .config import NetraModelConfig
import warnings

def create_netra_model(config: NetraModelConfig) -> Any:
    """
    Creates the PyTorch model for NETRA.
    Uses segmentation_models_pytorch if available, otherwise returns a mock for testing.
    """
    try:
        import segmentation_models_pytorch as smp
        model = smp.Unet(
            encoder_name=config.encoder_name,
            encoder_weights=config.encoder_weights,
            in_channels=config.in_channels,
            classes=config.classes
        )
        return model
    except ImportError:
        warnings.warn("segmentation_models_pytorch not installed, returning MockNetraModel")
        class MockNetraModel:
            def __init__(self, config):
                self.config = config
                
            def __call__(self, x, *args, **kwargs):
                import numpy as np
                import torch
                # Return dummy tensor matching batch size and spatial dims
                B = x.shape[0]
                H, W = x.shape[2], x.shape[3]
                C = self.config.classes
                return torch.zeros((B, C, H, W))
                
            def eval(self):
                pass
                
            def train(self):
                pass
                
            def to(self, device):
                return self
                
        return MockNetraModel(config)
