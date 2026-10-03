import pytest
from varuna_infra.experiment.store import InMemoryExperimentStore
from varuna_infra.experiment.runner import ExperimentRunner

def test_experiment_runner():
    store = InMemoryExperimentStore()
    runner = ExperimentRunner(store)
    
    def mock_train(exp_id: str):
        store.log_metric(exp_id, "loss", 0.5)
        
    exp_id = runner.run("test_exp", mock_train)
    
    assert exp_id in store.params
    assert store.params[exp_id]["name"] == "test_exp"
    assert exp_id in store.metrics
    assert store.metrics[exp_id]["loss"] == 0.5
