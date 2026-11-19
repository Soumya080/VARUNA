from pydantic import BaseModel, ConfigDict

class ChhayaModelConfig(BaseModel):
    input_dim: int = 4
    hidden_dim: int = 128
    num_layers: int = 3
    output_dim: int = 2
    dropout: float = 0.1
    seq_len: int = 72
    
    model_config = ConfigDict(extra="forbid")
