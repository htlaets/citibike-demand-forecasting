"""NYC DOT Traffic Speeds ingestion through Socrata.

Supports:
1. Incremental recent ingestion at link-observation grain.
2. Historical backfill that downloads only data_as_of/borough/speed/travel_time,
   aggregates each day locally to hour x borough, and persists compact synthetic
   hourly rows. This avoids SoQL numeric aggregation over source Text columns.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

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

NYC_TZ = ZoneInfo("America/New_York")

INSERT_SQL = """
INSERT INTO raw.traffic_speed (
    link_id, data_as_of, speed, travel_time, borough, link_name,
    encoded_poly_line, load_id
)
VALUES (
    :link_id, :data_as_of, :speed, :travel_time, :borough, :link_name,
    :encoded_poly_line, :load_id
)
ON CONFLICT (link_id, data_as_of) DO NOTHING
"""


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_socrata_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NYC_TZ)
    return parsed.astimezone(timezone.utc)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _normalize(rows: list[dict[str, Any]], load_id: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("link_id") or not row.get("data_as_of"):
            continue
        normalized.append(
            {
                "link_id": str(row["link_id"]),
                "data_as_of": _parse_socrata_time(str(row["data_as_of"])),
                "speed": _number(row.get("speed")),
                "travel_time": _number(row.get("travel_time")),
                "borough": row.get("borough"),
                "link_name": row.get("link_name"),
                "encoded_poly_line": row.get("encoded_poly_line"),
                "load_id": load_id,
            }
        )
    return normalized


def _source_latest_timestamp(
    client: HttpClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> datetime:
    payload = client.get_json(
        url,
        params={
            "$select": "data_as_of",
            "$where": "data_as_of is not null",
            "$order": "data_as_of DESC",
            "$limit": 1,
        },
        headers=headers,
    )
    if not isinstance(payload, list) or not payload:
        raise SourceRequestError(
            "NYC DOT Traffic Speeds returned no rows while determining "
            "the latest source timestamp."
        )

    value = payload[0].get("data_as_of")
    if not value:
        raise SourceRequestError("Latest NYC DOT row has no data_as_of value")
    return _parse_socrata_time(str(value))


def _aggregate_daily_rows(
    rows: list[dict[str, Any]],
    buckets: dict[tuple[datetime, str], list[float]],
) -> tuple[int, int]:
    """Accumulate source rows into local NYC hour x borough buckets.

    bucket value = [speed_sum, speed_count, travel_sum, travel_count]
    Returns (accepted, rejected).
    """
    accepted = rejected = 0

    for row in rows:
        raw_time = row.get("data_as_of")
        if not raw_time:
            rejected += 1
            continue

        speed = _number(row.get("speed"))
        travel = _number(row.get("travel_time"))
        if speed is None and travel is None:
            rejected += 1
            continue

        observed_utc = _parse_socrata_time(str(raw_time))
        local_hour = observed_utc.astimezone(NYC_TZ).replace(
            minute=0, second=0, microsecond=0
        )
        borough = str(row.get("borough") or "UNKNOWN").strip() or "UNKNOWN"

        bucket = buckets[(local_hour, borough)]
        if speed is not None:
            bucket[0] += speed
            bucket[1] += 1.0
        if travel is not None:
            bucket[2] += travel
            bucket[3] += 1.0
        accepted += 1

    return accepted, rejected


def _materialize_buckets(
    buckets: dict[tuple[datetime, str], list[float]],
    load_id: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for (local_hour, borough), values in sorted(
        buckets.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        speed_sum, speed_count, travel_sum, travel_count = values
        result.append(
            {
                "link_id": f"HIST_HOURLY:{borough}",
                "data_as_of": local_hour.astimezone(timezone.utc),
                "speed": speed_sum / speed_count if speed_count else None,
                "travel_time": travel_sum / travel_count if travel_count else None,
                "borough": borough,
                "link_name": "NYC DOT local hourly borough aggregate",
                "encoded_poly_line": None,
                "load_id": load_id,
            }
        )
    return result



def _historical_day_is_complete(engine: Engine, day: date) -> bool:
    """Return True when all 24 local hours and at least five borough buckets exist."""
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=NYC_TZ)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    from sqlalchemy import text as sql_text

    with engine.connect() as connection:
        row = connection.execute(
            sql_text(
                """
                SELECT
                    COUNT(*) AS rows,
                    COUNT(DISTINCT data_as_of) AS hours,
                    COUNT(DISTINCT borough) AS boroughs
                FROM raw.traffic_speed
                WHERE link_id LIKE 'HIST_HOURLY:%'
                  AND data_as_of >= :start_utc
                  AND data_as_of < :end_utc
                """
            ),
            {"start_utc": start_utc, "end_utc": end_utc},
        ).mappings().one()

    return int(row["hours"] or 0) >= 24 and int(row["boroughs"] or 0) >= 5

def _historical_backfill(
    client: HttpClient,
    config: dict[str, Any],
    *,
    start_date: str,
    end_date: str,
    engine: Engine,
) -> dict[str, int | str]:
    cfg = config["sources"]["traffic"]
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("traffic end date must be on or after start date")

    token = os.getenv("NYC_OPEN_DATA_APP_TOKEN")
    headers = {"X-App-Token": token} if token else None
    url = str(cfg["url"])
    page_size = 50000
    max_pages = max(1, int(cfg.get("max_pages_per_run", 100)))

    load_id = start_load(
        "traffic",
        pipeline_name="traffic_historical_backfill",
        run_key=f"{start.isoformat()}:{end.isoformat()}",
        watermark_from=start.isoformat(),
        engine=engine,
    )

    received_total = inserted_total = rejected_total = 0
    aggregate_total = 0

    try:
        current = start
        while current <= end:
            next_day = current + timedelta(days=1)

            if _historical_day_is_complete(engine, current):
                print(f"Traffic {current.isoformat()}: already complete -> skipped")
                current = next_day
                continue

            offset = 0
            pages = 0
            day_received = 0
            day_rejected = 0
            buckets: dict[tuple[datetime, str], list[float]] = defaultdict(
                lambda: [0.0, 0.0, 0.0, 0.0]
            )

            while True:
                params = {
                    "$select": "data_as_of,borough,speed,travel_time",
                    "$where": (
                        f"data_as_of >= '{current.isoformat()}T00:00:00' "
                        f"AND data_as_of < '{next_day.isoformat()}T00:00:00'"
                    ),
                    "$order": "data_as_of ASC",
                    "$limit": page_size,
                    "$offset": offset,
                }

                payload = client.get_json(url, params=params, headers=headers)
                if not isinstance(payload, list):
                    raise SourceRequestError("NYC DOT response must be a JSON array")
                if not payload:
                    break

                pages += 1
                if pages > max_pages:
                    raise RuntimeError(
                        f"NYC DOT daily page limit reached for {current}; "
                        "increase traffic.max_pages_per_run."
                    )

                day_received += len(payload)
                _, rejected = _aggregate_daily_rows(payload, buckets)
                day_rejected += rejected

                if len(payload) < page_size:
                    break
                offset += page_size

            aggregate_rows = _materialize_buckets(buckets, load_id)
            with engine.begin() as connection:
                day_inserted = execute_batch(connection, INSERT_SQL, aggregate_rows)

            received_total += day_received
            rejected_total += day_rejected
            aggregate_total += len(aggregate_rows)
            inserted_total += day_inserted

            print(
                f"Traffic {current.isoformat()}: "
                f"source_rows={day_received:,} "
                f"hourly_rows={len(aggregate_rows):,} "
                f"inserted={day_inserted:,} "
                f"rejected={day_rejected:,}"
            )

            current = next_day

        finish_load(
            load_id,
            status="SUCCESS",
            watermark_to=end.isoformat(),
            rows_received=received_total,
            rows_inserted=inserted_total,
            rows_rejected=rejected_total,
            engine=engine,
        )

        # Historical backfill intentionally does not alter the normal realtime watermark.
        return {
            "mode": "historical_local_hourly_aggregate",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "source_rows_received": received_total,
            "hourly_rows_produced": aggregate_total,
            "inserted": inserted_total,
            "rejected": rejected_total,
        }

    except Exception as exc:
        finish_load(
            load_id,
            status="FAILED",
            rows_received=received_total,
            rows_inserted=inserted_total,
            rows_rejected=rejected_total,
            error=exc,
            engine=engine,
        )
        raise


def ingest(
    client: HttpClient,
    config: dict[str, Any],
    *,
    since_hours: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    engine: Engine | None = None,
) -> dict[str, int | str]:
    db = engine or get_engine()

    if bool(start_date) != bool(end_date):
        raise ValueError(
            "traffic historical backfill requires both --traffic-start-date "
            "and --traffic-end-date"
        )

    if start_date and end_date:
        return _historical_backfill(
            client,
            config,
            start_date=start_date,
            end_date=end_date,
            engine=db,
        )

    cfg = config["sources"]["traffic"]
    wm = get_watermark("traffic", db)

    token = os.getenv("NYC_OPEN_DATA_APP_TOKEN")
    headers = {"X-App-Token": token} if token else None
    url = str(cfg["url"])

    bootstrap_hours: int | None = None
    source_latest: datetime | None = None

    if wm.timestamp:
        start = wm.timestamp
    else:
        bootstrap_hours = int(since_hours or cfg.get("bootstrap_since_hours", 24))
        if bootstrap_hours <= 0:
            raise ValueError("traffic bootstrap lookback must be greater than zero")
        source_latest = _source_latest_timestamp(client, url, headers=headers)
        start = source_latest - timedelta(hours=bootstrap_hours)

    load_id = start_load(
        "traffic",
        run_key=start.isoformat(),
        watermark_from=wm.timestamp.isoformat() if wm.timestamp else None,
        engine=db,
    )
    received = inserted = rejected = 0
    latest: datetime | None = None

    try:
        page_size = int(cfg.get("page_size", 5000))
        max_pages = int(cfg.get("max_pages_per_run", 100))
        offset = 0

        with db.begin() as connection:
            for _ in range(max_pages):
                local_start = start.astimezone(NYC_TZ)
                where_parts = [
                    f"data_as_of > '{local_start.strftime('%Y-%m-%dT%H:%M:%S')}'"
                ]

                if source_latest is not None:
                    local_end = source_latest.astimezone(NYC_TZ)
                    where_parts.append(
                        f"data_as_of <= '{local_end.strftime('%Y-%m-%dT%H:%M:%S')}'"
                    )

                params = {
                    "$limit": page_size,
                    "$offset": offset,
                    "$where": " AND ".join(where_parts),
                    "$order": "data_as_of ASC, link_id ASC",
                }
                payload = client.get_json(url, params=params, headers=headers)
                if not isinstance(payload, list):
                    raise SourceRequestError("NYC DOT response must be a JSON array")
                if not payload:
                    break

                received += len(payload)
                rows = _normalize(payload, load_id)
                rejected += len(payload) - len(rows)
                inserted += execute_batch(connection, INSERT_SQL, rows)

                if rows:
                    page_latest = max(row["data_as_of"] for row in rows)
                    latest = max(latest, page_latest) if latest else page_latest

                if len(payload) < page_size:
                    break
                offset += page_size
            else:
                raise RuntimeError(
                    "NYC DOT max_pages_per_run reached; increase it or run ingestion again."
                )

        if latest:
            set_watermark("traffic", timestamp=latest, engine=db)

        finish_load(
            load_id,
            status="SUCCESS",
            watermark_to=latest.isoformat() if latest else None,
            rows_received=received,
            rows_inserted=inserted,
            rows_rejected=rejected,
            engine=db,
        )

        result: dict[str, int | str] = {
            "mode": "incremental",
            "received": received,
            "inserted": inserted,
            "rejected": rejected,
            "watermark": latest.isoformat() if latest else "",
        }
        if bootstrap_hours is not None:
            result["bootstrap_hours"] = bootstrap_hours
            result["source_latest"] = source_latest.isoformat() if source_latest else ""
        return result

    except Exception as exc:
        finish_load(
            load_id,
            status="FAILED",
            rows_received=received,
            rows_inserted=inserted,
            rows_rejected=rejected,
            error=exc,
            engine=db,
        )
        raise
