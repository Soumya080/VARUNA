import numpy as np

def compute_iou(mask_true: np.ndarray, mask_pred: np.ndarray, num_classes: int) -> dict[int, float]:
    ious = {}
    for c in range(num_classes):
        true_c = (mask_true == c)
        pred_c = (mask_pred == c)
        intersection = np.logical_and(true_c, pred_c).sum()
        union = np.logical_or(true_c, pred_c).sum()
        if union == 0:
            ious[c] = float('nan')
        else:
            ious[c] = float(intersection / union)
    return ious

def compute_haversine_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    # simple stub for test
    return abs(lon1 - lon2) + abs(lat1 - lat2)
