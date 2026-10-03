import pytest
import numpy as np
from varuna_infra.evaluation.metrics import compute_iou, compute_haversine_distance

def test_compute_iou():
    mask_true = np.array([[0, 1], [1, 2]])
    mask_pred = np.array([[0, 1], [0, 2]])
    
    ious = compute_iou(mask_true, mask_pred, 3)
    
    # Class 0: true has 1, pred has 2. Intersection = 1, Union = 2. IOU = 0.5
    assert ious[0] == 0.5
    
    # Class 1: true has 2, pred has 1. Intersection = 1, Union = 2. IOU = 0.5
    assert ious[1] == 0.5
    
    # Class 2: true has 1, pred has 1. Intersection = 1, Union = 1. IOU = 1.0
    assert ious[2] == 1.0

def test_compute_haversine_distance():
    dist = compute_haversine_distance(0.0, 0.0, 1.0, 1.0)
    assert dist == 2.0
