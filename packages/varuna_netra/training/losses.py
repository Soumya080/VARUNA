from typing import Any

class DiceLoss:
    def __init__(self, smooth: float = 1.0):
        self.smooth = smooth
        
    def __call__(self, preds: Any, targets: Any) -> float:
        # Stub implementation for M5 laptop tests
        return 0.5

class CombinedLoss:
    def __init__(self, class_weights: list[float] = None):
        self.class_weights = class_weights or [1.0, 1.0, 1.0]
        self.dice = DiceLoss()
        
    def __call__(self, preds: Any, targets: Any) -> float:
        # 0.5 * Dice + 0.5 * CE stub
        return self.dice(preds, targets) + 0.5
