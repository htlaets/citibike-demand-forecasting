"""Forecasting package."""

from __future__ import annotations

from typing import Any


def train_forecasting_pipeline(*args: Any, **kwargs: Any):
    """Lazily import the training stack so lightweight metric/feature modules stay standalone."""
    from .train import train_forecasting_pipeline as _train

    return _train(*args, **kwargs)


__all__ = ["train_forecasting_pipeline"]
