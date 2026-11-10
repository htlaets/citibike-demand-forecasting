"""Build a compact, complete station-hour modeling data set from PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import Engine, text

from citibike_pipeline.database.connection import get_engine


@dataclass(frozen=True)
class ModelingData:
    frame: pd.DataFrame
    stations: pd.DataFrame
    min_hour: pd.Timestamp
    max_hour: pd.Timestamp
    coverage: dict[str, float]


def _range(engine: Engine) -> tuple[pd.Timestamp, pd.Timestamp]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    MIN(observed_hour) AS min_hour,
                    MAX(observed_hour) AS max_hour
                FROM gold.station_hourly_demand
                """
            )
        ).mappings().one()

    if row["min_hour"] is None or row["max_hour"] is None:
        raise RuntimeError("gold.station_hourly_demand is empty; run dbt build first")

    return pd.Timestamp(row["min_hour"]), pd.Timestamp(row["max_hour"])


def _top_stations(engine: Engine, top_n: int) -> pd.DataFrame:
    query = text(
        """
        SELECT
            station_sk,
            station_id,
            MAX(station_name) AS station_name,
            SUM(rides_started)::BIGINT AS total_rides
        FROM gold.station_hourly_demand
        GROUP BY station_sk, station_id
        ORDER BY total_rides DESC, station_sk
        LIMIT :top_n
        """
    )
    frame = pd.read_sql(query, engine, params={"top_n": int(top_n)})
    if frame.empty:
        raise RuntimeError("No stations available for modeling")
    return frame


def _demand(engine: Engine, top_n: int) -> pd.DataFrame:
    query = text(
        """
        WITH top_stations AS (
            SELECT station_sk
            FROM gold.station_hourly_demand
            GROUP BY station_sk
            ORDER BY SUM(rides_started) DESC, station_sk
            LIMIT :top_n
        )
        SELECT
            d.observed_hour,
            d.station_sk,
            d.rides_started
        FROM gold.station_hourly_demand d
        JOIN top_stations t USING (station_sk)
        ORDER BY d.station_sk, d.observed_hour
        """
    )
    return pd.read_sql(query, engine, params={"top_n": int(top_n)})


def _weather(engine: Engine, min_hour: pd.Timestamp, max_hour: pd.Timestamp) -> pd.DataFrame:
    query = text(
        """
        SELECT
            observed_at AS observed_hour,
            temperature_2m,
            relative_humidity_2m,
            precipitation,
            snowfall,
            wind_speed_10m
        FROM silver.weather_hourly
        WHERE observed_at BETWEEN :min_hour AND :max_hour
        ORDER BY observed_at
        """
    )
    return pd.read_sql(
        query,
        engine,
        params={"min_hour": min_hour.to_pydatetime(), "max_hour": max_hour.to_pydatetime()},
    )


def _traffic(engine: Engine, min_hour: pd.Timestamp, max_hour: pd.Timestamp) -> pd.DataFrame:
    query = text(
        """
        SELECT
            observed_hour,
            AVG(avg_speed) AS avg_traffic_speed,
            AVG(avg_travel_time) AS avg_travel_time
        FROM silver.traffic_hourly
        WHERE observed_hour BETWEEN :min_hour AND :max_hour
        GROUP BY observed_hour
        ORDER BY observed_hour
        """
    )
    return pd.read_sql(
        query,
        engine,
        params={"min_hour": min_hour.to_pydatetime(), "max_hour": max_hour.to_pydatetime()},
    )


def build_modeling_data(
    *,
    top_stations: int = 250,
    engine: Engine | None = None,
) -> ModelingData:
    """Create complete hourly grids, including explicit zero-demand hours."""
    if top_stations <= 0:
        raise ValueError("top_stations must be greater than zero")

    db = engine or get_engine()
    min_hour, max_hour = _range(db)
    min_hour = min_hour.tz_convert("UTC") if min_hour.tzinfo else min_hour.tz_localize("UTC")
    max_hour = max_hour.tz_convert("UTC") if max_hour.tzinfo else max_hour.tz_localize("UTC")

    stations = _top_stations(db, top_stations)
    demand = _demand(db, top_stations)
    weather = _weather(db, min_hour, max_hour)
    traffic = _traffic(db, min_hour, max_hour)

    hours = pd.date_range(min_hour, max_hour, freq="h")
    grid = pd.MultiIndex.from_product(
        [stations["station_sk"].astype(int).tolist(), hours],
        names=["station_sk", "observed_hour"],
    ).to_frame(index=False)

    station_columns = stations[["station_sk", "station_id", "station_name"]].copy()
    station_columns["station_sk"] = station_columns["station_sk"].astype(int)
    station_columns["station_id"] = station_columns["station_id"].astype(str)

    for data in (demand, weather, traffic):
        if "observed_hour" in data.columns:
            data["observed_hour"] = pd.to_datetime(data["observed_hour"], utc=True)

    grid = grid.merge(station_columns, on="station_sk", how="left", validate="many_to_one")
    grid = grid.merge(
        demand[["station_sk", "observed_hour", "rides_started"]],
        on=["station_sk", "observed_hour"],
        how="left",
        validate="one_to_one",
    )
    grid["rides_started"] = grid["rides_started"].fillna(0).astype("int32")

    grid = grid.merge(weather, on="observed_hour", how="left", validate="many_to_one")
    grid = grid.merge(traffic, on="observed_hour", how="left", validate="many_to_one")
    grid = grid.sort_values(["station_sk", "observed_hour"]).reset_index(drop=True)

    coverage = {
        "weather_percent": round(
            float(grid["temperature_2m"].notna().mean() * 100.0), 2
        ),
        "traffic_percent": round(
            float(grid["avg_traffic_speed"].notna().mean() * 100.0), 2
        ),
    }

    return ModelingData(
        frame=grid,
        stations=stations,
        min_hour=min_hour,
        max_hour=max_hour,
        coverage=coverage,
    )
