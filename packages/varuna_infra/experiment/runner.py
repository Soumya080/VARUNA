from typing import Any, Callable
from varuna_infra.experiment.store import ExperimentStore
import uuid

class ExperimentRunner:
    def __init__(self, store: ExperimentStore):
        self.store = store
        
    def run(self, name: str, fn: Callable[[str], Any]) -> str:
        experiment_id = f"exp_{uuid.uuid4().hex[:8]}"
        self.store.log_param(experiment_id, "name", name)
        # Execute the training/evaluation function
        fn(experiment_id)
        return experiment_id
