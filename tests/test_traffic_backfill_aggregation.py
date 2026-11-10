from collections import defaultdict

from citibike_pipeline.ingestion.traffic import (
    _aggregate_daily_rows,
    _materialize_buckets,
)


def test_client_side_traffic_hourly_aggregation() -> None:
    source = [
        {
            "data_as_of": "2026-09-01T08:15:00",
            "borough": "Manhattan",
            "speed": "20",
            "travel_time": "100",
        },
        {
            "data_as_of": "2026-09-01T08:45:00",
            "borough": "Manhattan",
            "speed": "30",
            "travel_time": "140",
        },
    ]
    buckets = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])

    accepted, rejected = _aggregate_daily_rows(source, buckets)
    result = _materialize_buckets(buckets, load_id=7)

    assert accepted == 2
    assert rejected == 0
    assert len(result) == 1
    assert result[0]["link_id"] == "HIST_HOURLY:Manhattan"
    assert result[0]["speed"] == 25.0
    assert result[0]["travel_time"] == 120.0
    assert result[0]["load_id"] == 7
