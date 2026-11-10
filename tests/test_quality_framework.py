from citibike_pipeline.quality.schema_drift import schema_diff
from citibike_pipeline.quality.warehouse import DQResult, summarize


def test_dq_summary_counts_statuses() -> None:
    results = [
        DQResult("weather", "raw.weather_hourly", "RANGE", "a", "PASS", 10, 0),
        DQResult("traffic", "raw.traffic_speed", "RANGE", "b", "FAIL", 10, 2),
        DQResult("traffic", "raw.traffic_speed", "FRESHNESS", "c", "WARN", 1, 1),
    ]
    assert summarize(results) == {"PASS": 1, "WARN": 1, "FAIL": 1}


def test_schema_diff_detects_add_remove_and_type_change() -> None:
    previous = [
        {
            "column_name": "ride_id",
            "data_type": "text",
            "is_nullable": "NO",
            "ordinal_position": 1,
        },
        {
            "column_name": "speed",
            "data_type": "double precision",
            "is_nullable": "YES",
            "ordinal_position": 2,
        },
    ]
    current = [
        {
            "column_name": "ride_id",
            "data_type": "text",
            "is_nullable": "NO",
            "ordinal_position": 1,
        },
        {
            "column_name": "speed",
            "data_type": "numeric",
            "is_nullable": "YES",
            "ordinal_position": 2,
        },
        {
            "column_name": "borough",
            "data_type": "text",
            "is_nullable": "YES",
            "ordinal_position": 3,
        },
    ]

    diff = schema_diff(previous, current)

    assert diff["added"] == ["borough"]
    assert diff["removed"] == []
    assert "speed" in diff["changed"]
