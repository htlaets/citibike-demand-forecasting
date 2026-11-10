"""Persist model evaluation and forecast outputs in the GOLD layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import Engine, text

from citibike_pipeline.database.connection import get_engine


METRIC_SQL = """
INSERT INTO gold.model_metrics (
    model_name,
    model_version,
    split_name,
    evaluation_from,
    evaluation_to,
    mae,
    rmse,
    wape,
    rows_evaluated
)
VALUES (
    :model_name,
    :model_version,
    :split_name,
    :evaluation_from,
    :evaluation_to,
    :mae,
    :rmse,
    :wape,
    :rows_evaluated
)
ON CONFLICT (
    model_name, model_version, split_name, evaluation_from, evaluation_to
)
DO UPDATE SET
    mae = EXCLUDED.mae,
    rmse = EXCLUDED.rmse,
    wape = EXCLUDED.wape,
    rows_evaluated = EXCLUDED.rows_evaluated,
    evaluated_at = CURRENT_TIMESTAMP
"""

FORECAST_SQL = """
INSERT INTO gold.forecast_results (
    model_name,
    model_version,
    trained_at,
    forecast_for,
    station_sk,
    prediction,
    actual,
    horizon_hours,
    feature_set_version
)
VALUES (
    :model_name,
    :model_version,
    :trained_at,
    :forecast_for,
    :station_sk,
    :prediction,
    :actual,
    :horizon_hours,
    :feature_set_version
)
ON CONFLICT (
    model_name, model_version, forecast_for, station_sk, horizon_hours
)
DO UPDATE SET
    prediction = EXCLUDED.prediction,
    actual = EXCLUDED.actual,
    trained_at = EXCLUDED.trained_at,
    feature_set_version = EXCLUDED.feature_set_version,
    forecast_generated_at = CURRENT_TIMESTAMP
"""


def persist_metric(
    *,
    model_name: str,
    model_version: str,
    split_name: str,
    evaluation_from: pd.Timestamp,
    evaluation_to: pd.Timestamp,
    metrics: dict[str, float],
    rows_evaluated: int,
    engine: Engine | None = None,
) -> None:
    db = engine or get_engine()
    with db.begin() as connection:
        connection.execute(
            text(METRIC_SQL),
            {
                "model_name": model_name,
                "model_version": model_version,
                "split_name": split_name,
                "evaluation_from": evaluation_from.to_pydatetime(),
                "evaluation_to": evaluation_to.to_pydatetime(),
                "mae": float(metrics["mae"]),
                "rmse": float(metrics["rmse"]),
                "wape": float(metrics["wape"]),
                "rows_evaluated": int(rows_evaluated),
            },
        )


def persist_forecasts(
    frame: pd.DataFrame,
    *,
    model_name: str,
    model_version: str,
    trained_at: datetime,
    feature_set_version: str,
    horizon_hours: int = 1,
    engine: Engine | None = None,
    chunk_size: int = 5000,
) -> int:
    db = engine or get_engine()
    rows: list[dict[str, Any]] = []
    inserted = 0

    for item in frame[
        ["observed_hour", "station_sk", "rides_started", "prediction"]
    ].itertuples(index=False):
        rows.append(
            {
                "model_name": model_name,
                "model_version": model_version,
                "trained_at": trained_at,
                "forecast_for": pd.Timestamp(item.observed_hour).to_pydatetime(),
                "station_sk": int(item.station_sk),
                "prediction": max(0.0, float(item.prediction)),
                "actual": float(item.rides_started),
                "horizon_hours": int(horizon_hours),
                "feature_set_version": feature_set_version,
            }
        )

        if len(rows) >= chunk_size:
            with db.begin() as connection:
                result = connection.execute(text(FORECAST_SQL), rows)
                inserted += max(0, int(result.rowcount or 0))
            rows.clear()

    if rows:
        with db.begin() as connection:
            result = connection.execute(text(FORECAST_SQL), rows)
            inserted += max(0, int(result.rowcount or 0))

    return inserted


def list_metrics(limit: int = 30, engine: Engine | None = None) -> list[dict[str, Any]]:
    db = engine or get_engine()
    with db.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    model_name,
                    model_version,
                    split_name,
                    evaluation_from,
                    evaluation_to,
                    mae,
                    rmse,
                    wape,
                    rows_evaluated,
                    evaluated_at
                FROM gold.model_metrics
                ORDER BY evaluated_at DESC, model_name
                LIMIT :limit
                """
            ),
            {"limit": int(limit)},
        ).mappings()
        return [dict(row) for row in rows]
