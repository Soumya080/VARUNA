from pydantic import BaseModel, ConfigDict

class NetraModelConfig(BaseModel):
    encoder_name: str = "resnet34"
    encoder_weights: str = "imagenet"
    in_channels: int = 3
    classes: int = 3
    tile_confidence_head: bool = True
    
    model_config = ConfigDict(extra="forbid")
