from typing import Any
import numpy as np

class OODDetector:
    def __init__(self):
        # Stub for Mahalanobis / Energy score logic
        pass
        
    def compute_score(self, logits: Any, features: Any = None) -> float:
        # Return a mock OOD score between 0 and 1
        return float(np.random.uniform(0.1, 0.9))
