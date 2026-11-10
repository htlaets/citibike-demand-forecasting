"""Leakage-safe feature engineering for station-hour demand."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


HISTORY_FEATURES = [
    "station_id",
    "lag_1",
    "lag_24",
    "lag_168",
    "rolling_mean_3",
    "rolling_mean_24",
    "rolling_mean_168",
]

CALENDAR_FEATURES = HISTORY_FEATURES + [
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]

WEATHER_FEATURES = CALENDAR_FEATURES + [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "snowfall",
    "wind_speed_10m",
]

TRAFFIC_FEATURES = WEATHER_FEATURES + [
    "avg_traffic_speed",
    "avg_travel_time",
]

FEATURE_SETS = {
    "history": HISTORY_FEATURES,
    "calendar": CALENDAR_FEATURES,
    "weather": WEATHER_FEATURES,
    "traffic": TRAFFIC_FEATURES,
}


@dataclass(frozen=True)
class TimeSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    validation_start: pd.Timestamp
    test_start: pd.Timestamp


def engineer_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Create historical/calendar features using only information from prior hours."""
    required = {"station_sk", "station_id", "observed_hour", "rides_started"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required modeling columns: {', '.join(sorted(missing))}")

    data = frame.copy()
    data["observed_hour"] = pd.to_datetime(data["observed_hour"], utc=True)
    data["station_id"] = data["station_id"].astype(str)
    data["rides_started"] = data["rides_started"].fillna(0).astype(float)
    data = data.sort_values(["station_sk", "observed_hour"]).reset_index(drop=True)

    grouped = data.groupby("station_sk", sort=False)["rides_started"]
    for lag in (1, 24, 168):
        data[f"lag_{lag}"] = grouped.shift(lag)

    for window in (3, 24, 168):
        data[f"rolling_mean_{window}"] = (
            data.groupby("station_sk", sort=False)["rides_started"]
            .transform(
                lambda values, window=window: values.shift(1).rolling(
                    window=window,
                    min_periods=1,
                ).mean()
            )
        )

    local_time = data["observed_hour"].dt.tz_convert("America/New_York")
    data["hour_of_day"] = local_time.dt.hour.astype("int16")
    data["day_of_week"] = local_time.dt.dayofweek.astype("int16")
    data["is_weekend"] = (data["day_of_week"] >= 5).astype("int8")

    data["hour_sin"] = np.sin(2.0 * np.pi * data["hour_of_day"] / 24.0)
    data["hour_cos"] = np.cos(2.0 * np.pi * data["hour_of_day"] / 24.0)
    data["dow_sin"] = np.sin(2.0 * np.pi * data["day_of_week"] / 7.0)
    data["dow_cos"] = np.cos(2.0 * np.pi * data["day_of_week"] / 7.0)

    # A full previous week is required for the seasonal-naive baseline and the
    # 168-hour lag. Dropping these rows keeps all model comparisons on one grain.
    data = data[data["lag_168"].notna()].copy()
    return data.reset_index(drop=True)


def time_split(
    frame: pd.DataFrame,
    *,
    validation_days: int = 4,
    test_days: int = 5,
) -> TimeSplit:
    """Chronological train/validation/test split; never shuffles observations."""
    if validation_days <= 0 or test_days <= 0:
        raise ValueError("validation_days and test_days must be positive")

    data = frame.sort_values("observed_hour").copy()
    if data.empty:
        raise ValueError("modeling frame is empty")

    max_hour = pd.Timestamp(data["observed_hour"].max())
    test_start = max_hour - pd.Timedelta(days=test_days) + pd.Timedelta(hours=1)
    validation_start = test_start - pd.Timedelta(days=validation_days)

    train = data[data["observed_hour"] < validation_start].copy()
    validation = data[
        (data["observed_hour"] >= validation_start)
        & (data["observed_hour"] < test_start)
    ].copy()
    test = data[data["observed_hour"] >= test_start].copy()

    if train.empty or validation.empty or test.empty:
        raise ValueError(
            "Not enough history for the requested chronological split. "
            "Load a longer demand period or reduce validation/test days."
        )

    return TimeSplit(
        train=train,
        validation=validation,
        test=test,
        validation_start=validation_start,
        test_start=test_start,
    )
