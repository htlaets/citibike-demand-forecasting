"""Forecast evaluation metrics used consistently across all models."""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def _arrays(actual: Iterable[float], predicted: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    y_true = np.asarray(list(actual), dtype=float)
    y_pred = np.asarray(list(predicted), dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError("actual and predicted must have the same shape")
    if y_true.size == 0:
        raise ValueError("metrics require at least one observation")
    return y_true, y_pred


def mae(actual: Iterable[float], predicted: Iterable[float]) -> float:
    y_true, y_pred = _arrays(actual, predicted)
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(actual: Iterable[float], predicted: Iterable[float]) -> float:
    y_true, y_pred = _arrays(actual, predicted)
    return float(math.sqrt(np.mean(np.square(y_true - y_pred))))


def wape(actual: Iterable[float], predicted: Iterable[float]) -> float:
    """Weighted absolute percentage error in percentage points."""
    y_true, y_pred = _arrays(actual, predicted)
    denominator = float(np.sum(np.abs(y_true)))
    if denominator == 0:
        return float("nan")
    return float(np.sum(np.abs(y_true - y_pred)) / denominator * 100.0)


def evaluate(actual: Iterable[float], predicted: Iterable[float]) -> dict[str, float]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "wape": wape(actual, predicted),
    }
