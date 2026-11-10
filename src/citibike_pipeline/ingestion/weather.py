"""Incremental Open-Meteo Historical Weather ingestion."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import Engine

from citibike_pipeline.database.connection import get_engine
from citibike_pipeline.database.metadata import (
    finish_load,
    get_watermark,
    set_watermark,
    start_load,
)
from citibike_pipeline.http import HttpClient, SourceRequestError
from citibike_pipeline.ingestion.common import execute_batch

INSERT_SQL = """
INSERT INTO raw.weather_hourly (
    observed_at, temperature_2m, relative_humidity_2m, precipitation,
    rain, snowfall, weather_code, wind_speed_10m, latitude, longitude, load_id
)
VALUES (
    :observed_at, :temperature_2m, :relative_humidity_2m, :precipitation,
    :rain, :snowfall, :weather_code, :wind_speed_10m, :latitude, :longitude, :load_id
)
ON CONFLICT (observed_at) DO NOTHING
"""


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _rows(payload: dict[str, Any], load_id: int) -> list[dict[str, Any]]:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise SourceRequestError("Open-Meteo response has no hourly time series")
    times = hourly["time"]
    frame = pd.DataFrame(
        {
            "observed_at": times,
            "temperature_2m": hourly.get("temperature_2m"),
            "relative_humidity_2m": hourly.get("relative_humidity_2m"),
            "precipitation": hourly.get("precipitation"),
            "rain": hourly.get("rain"),
            "snowfall": hourly.get("snowfall"),
            "weather_code": hourly.get("weather_code"),
            "wind_speed_10m": hourly.get("wind_speed_10m"),
        }
    )
    frame["observed_at"] = (
        pd.to_datetime(frame["observed_at"], errors="coerce")
        .dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
        .dt.tz_convert("UTC")
    )
    for col in frame.columns:
        frame[col] = frame[col].astype(object).where(pd.notna(frame[col]), None)
    records = frame.to_dict(orient="records")
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    for row in records:
        row["latitude"] = latitude
        row["longitude"] = longitude
        row["load_id"] = load_id
    return records


def ingest(
    client: HttpClient,
    config: dict[str, Any],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    engine: Engine | None = None,
) -> dict[str, int | str] | None:
    db = engine or get_engine()
    cfg = config["sources"]["weather"]
    wm = get_watermark("weather", db)

    if start_date:
        start = _parse_date(start_date)
    elif wm.value:
        start = _parse_date(wm.value) + timedelta(days=1)
    else:
        start = _parse_date(str(cfg.get("bootstrap_start_date", "2026-01-01")))

    end = _parse_date(end_date) if end_date else date.today() - timedelta(days=2)
    if start > end:
        return None

    load_id = start_load(
        "weather",
        run_key=f"{start.isoformat()}:{end.isoformat()}",
        watermark_from=wm.value,
        engine=db,
    )
    try:
        variables = cfg.get("hourly", [])
        params = {
            "latitude": cfg["latitude"],
            "longitude": cfg["longitude"],
            "timezone": cfg.get("timezone", "America/New_York"),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(str(v) for v in variables),
        }
        payload = client.get_json(str(cfg["historical_url"]), params=params)
        if not isinstance(payload, dict):
            raise SourceRequestError("Open-Meteo response must be a JSON object")
        rows = _rows(payload, load_id)
        with db.begin() as connection:
            inserted = execute_batch(connection, INSERT_SQL, rows)

        set_watermark("weather", value=end.isoformat(), engine=db)
        finish_load(
            load_id,
            status="SUCCESS",
            watermark_to=end.isoformat(),
            rows_received=len(rows),
            rows_inserted=inserted,
            engine=db,
        )
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "received": len(rows),
            "inserted": inserted,
        }
    except Exception as exc:
        finish_load(load_id, status="FAILED", error=exc, engine=db)
        raise
