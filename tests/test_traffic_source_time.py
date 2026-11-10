from datetime import UTC

from citibike_pipeline.ingestion.traffic import (
    _parse_socrata_time,
    _source_latest_timestamp,
)


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params, headers))
        return self.payload


def test_parse_naive_socrata_timestamp_as_new_york_time() -> None:
    value = _parse_socrata_time("2026-09-01T12:00:00.000")
    assert value.tzinfo == UTC
    assert value.isoformat() == "2026-09-01T16:00:00+00:00"


def test_source_latest_timestamp_uses_latest_dataset_row() -> None:
    client = FakeClient([{"data_as_of": "2026-09-01T12:00:00.000"}])
    value = _source_latest_timestamp(client, "https://example.invalid")
    assert value.isoformat() == "2026-09-01T16:00:00+00:00"
    _, params, _ = client.calls[0]
    assert params["$order"] == "data_as_of DESC"
    assert params["$limit"] == 1
