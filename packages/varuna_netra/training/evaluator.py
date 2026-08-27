from typing import Any
import numpy as np

from varuna_netra.dataset.schema import NetraEvaluation

class NetraEvaluator:
    def evaluate(self, model: Any, test_loader: Any, experiment_id: str, model_version: str, dataset_version: str, split: str) -> NetraEvaluation:
        # Stub implementation for M5 laptop mode
        return NetraEvaluation(
            experiment_id=experiment_id,
            model_version=model_version,
            dataset_version=dataset_version,
            split=split,
            iou_oil=0.75,
            iou_lookalike=0.60,
            dice_oil=0.80,
            f1_oil=0.82,
            precision_oil=0.85,
            recall_oil=0.79,
            fp_rate_lookalike=0.08,
            ood_auroc=0.92,
            calibration_ece=0.04,
            per_region_iou={"region_A": 0.76, "region_B": 0.74},
            per_wind_bin_fp={"low": 0.12, "med": 0.05, "high": 0.02},
            confusion_matrix=np.array([[100, 5, 2], [3, 80, 4], [1, 2, 90]])
        )
