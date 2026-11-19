from pydantic import BaseModel, ConfigDict

class NetraTrainingConfig(BaseModel):
    epochs: int = 50
    batch_size: int = 8
    lr: float = 3e-4
    weight_decay: float = 1e-4
    warmup_epochs: int = 5
    patience: int = 8
    amp: bool = True
    seed: int = 42
    checkpoint_dir: str = "models/netra"
    
    model_config = ConfigDict(extra="forbid")
