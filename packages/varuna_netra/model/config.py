from pydantic import BaseModel, ConfigDict

class NetraModelConfig(BaseModel):
    encoder_name: str = "resnet34"
    encoder_weights: str | None = "imagenet"
    in_channels: int = 2
    classes: int = 2
    tile_confidence_head: bool = True
    
    model_config = ConfigDict(extra="forbid")
