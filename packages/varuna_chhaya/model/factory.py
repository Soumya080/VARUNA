from typing import Any
from .config import ChhayaModelConfig
import warnings

def create_chhaya_model(config: ChhayaModelConfig) -> Any:
    """
    Creates the PyTorch model for CHHAYA (LSTM/Transformer).
    Returns a mock for testing if torch is not available.
    """
    try:
        import torch
        import torch.nn as nn
        
        class ChhayaLSTM(nn.Module):
            def __init__(self, config):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size=config.input_dim,
                    hidden_size=config.hidden_dim,
                    num_layers=config.num_layers,
                    batch_first=True,
                    dropout=config.dropout if config.num_layers > 1 else 0
                )
                self.fc = nn.Linear(config.hidden_dim, config.output_dim)
                
            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out)
                
        return ChhayaLSTM(config)
    except ImportError:
        warnings.warn("torch not installed, returning MockChhayaModel")
        class MockChhayaModel:
            def __init__(self, config):
                self.config = config
                
            def __call__(self, x, *args, **kwargs):
                import numpy as np
                import torch
                B, T, _ = x.shape
                return torch.zeros((B, T, self.config.output_dim))
                
            def eval(self):
                pass
                
            def train(self):
                pass
                
            def to(self, device):
                return self
                
            def state_dict(self):
                return {"mock": "data"}
                
        return MockChhayaModel(config)
