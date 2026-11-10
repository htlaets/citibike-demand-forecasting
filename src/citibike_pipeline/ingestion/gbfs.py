"""Idempotent Citi Bike GBFS station snapshot ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine

from citibike_pipeline.database.connection import get_engine
from citibike_pipeline.database.metadata import finish_load, set_watermark, start_load
from citibike_pipeline.http import HttpClient, SourceRequestError
from citibike_pipeline.ingestion.common import execute_batch

INFO_SQL = """
INSERT INTO raw.gbfs_station_information (
    station_id, observed_at, station_name, latitude, longitude, capacity, load_id
)
VALUES (
    :station_id, :observed_at, :station_name, :latitude, :longitude, :capacity, :load_id
)
ON CONFLICT (station_id, observed_at) DO NOTHING
"""

STATUS_SQL = """
INSERT INTO raw.gbfs_station_status (
    station_id, observed_at, num_bikes_available, num_docks_available,
    is_installed, is_renting, is_returning, load_id
)
VALUES (
    :station_id, :observed_at, :num_bikes_available, :num_docks_available,
    :is_installed, :is_renting, :is_returning, :load_id
)
ON CONFLICT (station_id, observed_at) DO NOTHING
"""


def _feeds(discovery: dict[str, Any]) -> dict[str, str]:
    data = discovery.get("data", {})
    candidates = []
    if isinstance(data, dict):
        if isinstance(data.get("feeds"), list):
            candidates = data["feeds"]
        else:
            for value in data.values():
                if isinstance(value, dict) and isinstance(value.get("feeds"), list):
                    candidates = value["feeds"]
                    break
    result = {
        str(item["name"]): str(item["url"])
        for item in candidates
        if isinstance(item, dict) and item.get("name") and item.get("url")
    }
    if not result:
        raise SourceRequestError("GBFS discovery response contains no feeds")
    return result


def _feed_timestamp(payload: dict[str, Any]) -> datetime:
    value = payload.get("last_updated")
    try:
        # GBFS v2 commonly uses epoch seconds.
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, OSError):
        pass
    # Round fallback to minute so immediate reruns remain idempotent.
    now = datetime.now(UTC)
    return now.replace(second=0, microsecond=0)


def _station_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return []
    rows = data.get("stations", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _bool(value: Any) -> bool | None:
    if value in (1, "1", True):
        return True
    if value in (0, "0", False):
        return False
    return None


def ingest(
    client: HttpClient,
    config: dict[str, Any],
    *,
    engine: Engine | None = None,
) -> dict[str, int | str]:
    db = engine or get_engine()
    cfg = config["sources"]["citibike_gbfs"]
    load_id = start_load("citibike_gbfs", engine=db)
    received = inserted = 0
    try:
        discovery = client.get_json(str(cfg["discovery_url"]))
        if not isinstance(discovery, dict):
            raise SourceRequestError("GBFS discovery response must be an object")
        feeds = _feeds(discovery)
        required = {"station_information", "station_status"}
        missing = required - feeds.keys()
        if missing:
            raise SourceRequestError(f"GBFS feeds missing: {', '.join(sorted(missing))}")

        info_payload = client.get_json(feeds["station_information"])
        status_payload = client.get_json(feeds["station_status"])
        if not isinstance(info_payload, dict) or not isinstance(status_payload, dict):
            raise SourceRequestError("GBFS feed responses must be JSON objects")

        info_ts = _feed_timestamp(info_payload)
        status_ts = _feed_timestamp(status_payload)
        info_source = _station_rows(info_payload)
        status_source = _station_rows(status_payload)
        received = len(info_source) + len(status_source)

        info_rows = [
            {
                "station_id": str(r.get("station_id")),
                "observed_at": info_ts,
                "station_name": r.get("name"),
                "latitude": r.get("lat"),
                "longitude": r.get("lon"),
                "capacity": r.get("capacity"),
                "load_id": load_id,
            }
            for r in info_source
            if r.get("station_id") is not None
        ]
        status_rows = [
            {
                "station_id": str(r.get("station_id")),
                "observed_at": status_ts,
                "num_bikes_available": r.get("num_bikes_available"),
                "num_docks_available": r.get("num_docks_available"),
                "is_installed": _bool(r.get("is_installed")),
                "is_renting": _bool(r.get("is_renting")),
                "is_returning": _bool(r.get("is_returning")),
                "load_id": load_id,
            }
            for r in status_source
            if r.get("station_id") is not None
        ]

        with db.begin() as connection:
            inserted += execute_batch(connection, INFO_SQL, info_rows)
            inserted += execute_batch(connection, STATUS_SQL, status_rows)

        latest = max(info_ts, status_ts)
        set_watermark("citibike_gbfs", timestamp=latest, engine=db)
        finish_load(
            load_id,
            status="SUCCESS",
            watermark_to=latest.isoformat(),
            rows_received=received,
            rows_inserted=inserted,
            rows_rejected=received - len(info_rows) - len(status_rows),
            engine=db,
        )
        return {
            "received": received,
            "inserted": inserted,
            "watermark": latest.isoformat(),
        }
    except Exception as exc:
        finish_load(
            load_id,
            status="FAILED",
            rows_received=received,
            rows_inserted=inserted,
            error=exc,
            engine=db,
        )
        raise
