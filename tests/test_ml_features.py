import pandas as pd

from citibike_pipeline.ml.features import (
    FEATURE_SETS,
    engineer_features,
    time_split,
)


def _frame() -> pd.DataFrame:
    hours = pd.date_range("2026-09-01", periods=24 * 30, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "station_sk": 1,
            "station_id": "station-1",
            "observed_hour": hours,
            "rides_started": list(range(len(hours))),
            "temperature_2m": 20.0,
            "relative_humidity_2m": 60.0,
            "precipitation": 0.0,
            "snowfall": 0.0,
            "wind_speed_10m": 5.0,
            "avg_traffic_speed": 25.0,
            "avg_travel_time": 100.0,
        }
    )


def test_lags_and_rolling_are_shifted_no_current_target_leakage() -> None:
    engineered = engineer_features(_frame())
    first = engineered.iloc[0]

    # First retained row is source hour 168.
    assert first["rides_started"] == 168
    assert first["lag_1"] == 167
    assert first["lag_24"] == 144
    assert first["lag_168"] == 0
    assert first["rolling_mean_3"] == (165 + 166 + 167) / 3


def test_time_split_is_chronological_and_non_overlapping() -> None:
    engineered = engineer_features(_frame())
    split = time_split(engineered, validation_days=4, test_days=5)

    assert split.train["observed_hour"].max() < split.validation["observed_hour"].min()
    assert split.validation["observed_hour"].max() < split.test["observed_hour"].min()
    assert len(split.test) == 5 * 24
    assert len(split.validation) == 4 * 24


def test_ablation_feature_sets_are_nested() -> None:
    assert set(FEATURE_SETS["history"]) < set(FEATURE_SETS["calendar"])
    assert set(FEATURE_SETS["calendar"]) < set(FEATURE_SETS["weather"])
    assert set(FEATURE_SETS["weather"]) < set(FEATURE_SETS["traffic"])
