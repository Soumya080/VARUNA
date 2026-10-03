from typing import Any
import os
import random
import numpy as np
from pydantic import BaseModel, ConfigDict

class ChhayaTrainingConfig(BaseModel):
    epochs: int = 50
    batch_size: int = 32
    lr: float = 1e-3
    seed: int = 42
    checkpoint_dir: str = "models/chhaya"
    
    model_config = ConfigDict(extra="forbid")

class ChhayaTrainer:
    def __init__(self, config: ChhayaTrainingConfig):
        self.config = config
        
    def _seed_everything(self):
        random.seed(self.config.seed)
        np.random.seed(self.config.seed)
        try:
            import torch
            torch.manual_seed(self.config.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.config.seed)
                torch.backends.cudnn.deterministic = True
        except ImportError:
            pass

    def train(self, model: Any, train_loader: Any, val_loader: Any, experiment_id: str) -> str:
        self._seed_everything()
        os.makedirs(self.config.checkpoint_dir, exist_ok=True)
        best_checkpoint_path = os.path.join(self.config.checkpoint_dir, f"{experiment_id}_best.pt")
        
        # Stub for M5 testing mode
        for epoch in range(min(2, self.config.epochs)):
            pass
            
        try:
            import torch
            if hasattr(model, "state_dict"):
                torch.save(model.state_dict(), best_checkpoint_path)
            else:
                with open(best_checkpoint_path, "w") as f:
                    f.write("mock")
        except ImportError:
            with open(best_checkpoint_path, "w") as f:
                f.write("mock")
                
        return best_checkpoint_path
