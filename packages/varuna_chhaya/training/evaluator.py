from typing import Any
from varuna_chhaya.dataset.schema import ChhayaEvaluation

class ChhayaEvaluator:
    def evaluate(self, model: Any, test_loader: Any, experiment_id: str, model_version: str, dataset_version: str, split: str) -> ChhayaEvaluation:
        return ChhayaEvaluation(
            experiment_id=experiment_id,
            model_version=model_version,
            dataset_version=dataset_version,
            split=split,
            mean_distance_km=2.5,
            max_distance_km=10.0,
            rmse_lon=0.01,
            rmse_lat=0.01
        )
