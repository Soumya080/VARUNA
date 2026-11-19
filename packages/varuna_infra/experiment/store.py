from typing import Dict, Any, Protocol

class ExperimentStore(Protocol):
    def log_metric(self, experiment_id: str, key: str, value: float) -> None:
        ...
        
    def log_param(self, experiment_id: str, key: str, value: Any) -> None:
        ...

class InMemoryExperimentStore(ExperimentStore):
    def __init__(self):
        self.metrics: Dict[str, Dict[str, float]] = {}
        self.params: Dict[str, Dict[str, Any]] = {}
        
    def log_metric(self, experiment_id: str, key: str, value: float) -> None:
        self.metrics.setdefault(experiment_id, {})[key] = value
        
    def log_param(self, experiment_id: str, key: str, value: Any) -> None:
        self.params.setdefault(experiment_id, {})[key] = value
