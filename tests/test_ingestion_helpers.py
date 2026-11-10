from datetime import date

import pandas as pd

from citibike_pipeline.ingestion.citibike_trips import (
    _normalize_chunk,
    archive_candidates,
)
from citibike_pipeline.ingestion.common import iter_months, next_month
from citibike_pipeline.ingestion.weather import _rows as weather_rows


def test_month_iteration() -> None:
    assert list(iter_months(date(2026, 10, 1), date(2026, 12, 1))) == [
        date(2026, 10, 1),
        date(2026, 11, 1),
        date(2026, 12, 1),
    ]
    assert next_month(date(2026, 12, 1)) == date(2027, 1, 1)


def test_citibike_archive_candidates() -> None:
    urls = archive_candidates("https://example.test/tripdata", date(2026, 9, 1))
    assert urls[0].endswith("/202609-citibike-tripdata.zip")
    assert urls[1].endswith("/202609-citibike-tripdata.csv.zip")


def test_citibike_normalization_rejects_missing_ride_id() -> None:
    frame = pd.DataFrame(
        [
            {
                "ride_id": "r1",
                "rideable_type": "classic_bike",
                "started_at": "2026-09-01 10:00:00",
                "ended_at": "2026-09-01 10:10:00",
                "start_station_name": "A",
                "start_station_id": "1",
                "end_station_name": "B",
                "end_station_id": "2",
                "start_lat": 40.7,
                "start_lng": -74.0,
                "end_lat": 40.71,
                "end_lng": -73.99,
                "member_casual": "member",
            },
            {
                "ride_id": None,
                "rideable_type": "classic_bike",
                "started_at": "2026-09-01 11:00:00",
                "ended_at": "2026-09-01 11:10:00",
                "start_station_name": "A",
                "start_station_id": "1",
                "end_station_name": "B",
                "end_station_id": "2",
                "start_lat": 40.7,
                "start_lng": -74.0,
                "end_lat": 40.71,
                "end_lng": -73.99,
                "member_casual": "member",
            },
        ]
    )
    rows, rejected = _normalize_chunk(
        frame, source_file="x.csv", source_month=date(2026, 9, 1), load_id=1
    )
    assert len(rows) == 1
    assert rejected == 1
    assert rows[0]["ride_id"] == "r1"


def test_weather_rows_are_hourly() -> None:
    payload = {
        "latitude": 40.7,
        "longitude": -74.0,
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [1.0, 2.0],
            "relative_humidity_2m": [80.0, 79.0],
            "precipitation": [0.0, 0.1],
            "rain": [0.0, 0.1],
            "snowfall": [0.0, 0.0],
            "weather_code": [0, 3],
            "wind_speed_10m": [8.0, 9.0],
        },
    }
    rows = weather_rows(payload, 99)
    assert len(rows) == 2
    assert rows[0]["load_id"] == 99
