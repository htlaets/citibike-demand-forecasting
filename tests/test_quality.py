import pytest

from citibike_pipeline.quality.checks import (
    check_citibike,
    check_source,
    check_traffic,
    check_weather,
)


def test_valid_citibike_snapshot_passes() -> None:
    snapshot = {
        "source": "citibike",
        "payload": {
            "feeds": {
                "station_information": {
                    "data": {
                        "stations": [
                            {
                                "station_id": "1",
                                "name": "Broadway",
                                "lat": 40.72,
                                "lon": -73.99,
                            }
                        ]
                    }
                },
                "station_status": {
                    "data": {
                        "stations": [
                            {
                                "station_id": "1",
                                "num_bikes_available": 8,
                                "num_docks_available": 12,
                            }
                        ]
                    }
                },
            }
        },
    }

    report = check_citibike(snapshot)

    assert report.passed
    assert report.row_count == 1
    assert report.metrics["station_information_rows"] == 1


def test_citibike_duplicate_station_fails() -> None:
    station = {"station_id": "1", "name": "A", "lat": 40.7, "lon": -74.0}
    snapshot = {
        "feeds": {
            "station_information": {"data": {"stations": [station, station]}},
            "station_status": {
                "data": {
                    "stations": [
                        {"station_id": "1", "num_bikes_available": 1, "num_docks_available": 2}
                    ]
                }
            },
        }
    }

    report = check_citibike(snapshot)

    assert not report.passed
    assert any(issue.check == "duplicates" for issue in report.issues)


def test_valid_weather_snapshot_tracks_time_range() -> None:
    snapshot = {
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [2.0, 3.0],
            "relative_humidity_2m": [70, 68],
            "precipitation": [0.0, 0.2],
            "weather_code": [0, 3],
            "wind_speed_10m": [10.0, 12.0],
        }
    }

    report = check_weather(snapshot)

    assert report.passed
    assert report.row_count == 2
    assert report.metrics["time_min"] == "2026-01-01T00:00:00"
    assert report.metrics["time_max"] == "2026-01-01T01:00:00"


def test_weather_mismatched_arrays_and_null_fail() -> None:
    snapshot = {
        "hourly": {
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "temperature_2m": [None],
        }
    }

    report = check_weather(snapshot)

    assert not report.passed
    checks = {issue.check for issue in report.issues}
    assert {"row_count", "nulls"} <= checks


def test_valid_traffic_snapshot_accepts_numeric_strings() -> None:
    snapshot = [
        {
            "link_id": "100",
            "speed": "35.5",
            "travel_time": "120",
            "data_as_of": "2026-01-01T00:00:00.000",
        }
    ]

    report = check_traffic(snapshot)

    assert report.passed
    assert report.row_count == 1


def test_traffic_invalid_type_range_and_duplicate_fail() -> None:
    snapshot = [
        {"link_id": "100", "speed": "fast", "travel_time": "-1", "data_as_of": "bad"},
        {"link_id": "100", "speed": "20", "travel_time": "5", "data_as_of": "bad"},
    ]

    report = check_traffic(snapshot)

    assert not report.passed
    checks = {issue.check for issue in report.issues}
    assert {"duplicates", "types", "ranges"} <= checks


def test_dispatcher_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        check_source("unknown", {})
