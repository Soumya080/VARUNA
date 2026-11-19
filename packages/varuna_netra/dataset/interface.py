from typing import Protocol, List, Any
from .schema import NetraSample

class NetraDatasetProvider(Protocol):
    def load_sample(self, sample_id: str) -> NetraSample:
        ...
        
    def list_samples(self, split: str) -> List[NetraSample]:
        ...
        
    def get_manifest(self) -> Any:
        ...
