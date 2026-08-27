from typing import Protocol, List, Any
from .schema import ChhayaSample

class ChhayaDatasetProvider(Protocol):
    def load_sample(self, sample_id: str) -> ChhayaSample:
        ...
        
    def list_samples(self, split: str) -> List[ChhayaSample]:
        ...
        
    def get_manifest(self) -> Any:
        ...
