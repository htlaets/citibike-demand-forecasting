"""Warehouse-level data-quality checks persisted in PostgreSQL."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, text

from citibike_pipeline.database.connection import get_engine


@dataclass(frozen=True)
class DQResult:
    source_name: str
    dataset_name: str
    check_type: str
    check_name: str
    status: str
    rows_checked: int | None
    failed_rows: int | None
    column_name: str | None = None
    observed_value: dict[str, Any] | None = None
    expected_value: dict[str, Any] | None = None
    details: str | None = None


def _scalar(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params or {}).scalar()


def _row(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with engine.connect() as connection:
        result = connection.execute(text(sql), params or {}).mappings().one()
    return dict(result)


def _count(engine: Engine, table: str) -> int:
    return int(_scalar(engine, f"SELECT COUNT(*) FROM {table}") or 0)


def _persist(engine: Engine, result: DQResult) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO meta.dq_results (
                    source_name, dataset_name, check_type, check_name,
                    column_name, status, rows_checked, failed_rows,
                    observed_value, expected_value, details
                )
                VALUES (
                    :source_name, :dataset_name, :check_type, :check_name,
                    :column_name, :status, :rows_checked, :failed_rows,
                    CAST(:observed_value AS jsonb),
                    CAST(:expected_value AS jsonb),
                    :details
                )
                """
            ),
            {
                "source_name": result.source_name,
                "dataset_name": result.dataset_name,
                "check_type": result.check_type,
                "check_name": result.check_name,
                "column_name": result.column_name,
                "status": result.status,
                "rows_checked": result.rows_checked,
                "failed_rows": result.failed_rows,
                "observed_value": json.dumps(result.observed_value)
                if result.observed_value is not None
                else None,
                "expected_value": json.dumps(result.expected_value)
                if result.expected_value is not None
                else None,
                "details": result.details,
            },
        )


def _status(failed: int, *, warning: bool = False) -> str:
    if failed <= 0:
        return "PASS"
    return "WARN" if warning else "FAIL"


def _simple_count_check(
    engine: Engine,
    *,
    source_name: str,
    dataset_name: str,
    check_type: str,
    check_name: str,
    fail_sql: str,
    column_name: str | None = None,
    warning: bool = False,
    expected: dict[str, Any] | None = None,
    details: str | None = None,
) -> DQResult:
    total = _count(engine, dataset_name)
    failed = int(_scalar(engine, fail_sql) or 0)
    return DQResult(
        source_name=source_name,
        dataset_name=dataset_name,
        check_type=check_type,
        check_name=check_name,
        column_name=column_name,
        status=_status(failed, warning=warning),
        rows_checked=total,
        failed_rows=failed,
        observed_value={"failed_rows": failed},
        expected_value=expected or {"failed_rows": 0},
        details=details,
    )


def _freshness_check(
    engine: Engine,
    *,
    source_name: str,
    dataset_name: str,
    check_name: str,
    max_timestamp_sql: str,
    sla_hours: int,
) -> DQResult:
    row = _row(
        engine,
        f"""
        SELECT
            MAX(value_ts) AS latest_ts,
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(value_ts))) / 3600.0 AS age_hours
        FROM ({max_timestamp_sql}) q
        """,
    )
    latest = row.get("latest_ts")
    age = float(row["age_hours"]) if row.get("age_hours") is not None else None
    failed = 1 if latest is None or age is None or age > sla_hours else 0
    return DQResult(
        source_name=source_name,
        dataset_name=dataset_name,
        check_type="FRESHNESS",
        check_name=check_name,
        status=_status(failed),
        rows_checked=1,
        failed_rows=failed,
        observed_value={
            "latest_timestamp": latest.isoformat() if latest else None,
            "age_hours": round(age, 2) if age is not None else None,
        },
        expected_value={"max_age_hours": sla_hours},
        details="Freshness is measured from the latest source event available in RAW.",
    )


def _type_check(
    engine: Engine,
    *,
    source_name: str,
    dataset_name: str,
    schema_name: str,
    table_name: str,
    expected_types: dict[str, str],
) -> DQResult:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        ).mappings()
        actual = {str(row["column_name"]): str(row["data_type"]) for row in rows}

    mismatches = {
        column: {"expected": expected, "actual": actual.get(column)}
        for column, expected in expected_types.items()
        if actual.get(column) != expected
    }
    return DQResult(
        source_name=source_name,
        dataset_name=dataset_name,
        check_type="TYPE",
        check_name=f"{table_name}_column_types",
        status=_status(len(mismatches)),
        rows_checked=len(expected_types),
        failed_rows=len(mismatches),
        observed_value={"actual_types": actual, "mismatches": mismatches},
        expected_value={"expected_types": expected_types},
        details="Checks PostgreSQL physical types for analytics-critical columns.",
    )


def _citibike_checks(engine: Engine, cfg: dict[str, Any]) -> list[DQResult]:
    dataset = "raw.citibike_trips"
    checks = [
        _simple_count_check(
            engine,
            source_name="citibike_trips",
            dataset_name=dataset,
            check_type="COMPLETENESS",
            check_name="citibike_required_fields",
            column_name="started_at,ended_at,start_station_id",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.citibike_trips
                WHERE started_at IS NULL
                   OR ended_at IS NULL
                   OR start_station_id IS NULL
                   OR btrim(start_station_id) = ''
            """,
            details=(
                "Rows without a start station or timestamps cannot be used "
                "in station-hour demand."
            ),
        ),
        _simple_count_check(
            engine,
            source_name="citibike_trips",
            dataset_name=dataset,
            check_type="UNIQUENESS",
            check_name="citibike_ride_id_unique",
            column_name="ride_id",
            fail_sql="""
                SELECT COUNT(*)
                FROM (
                    SELECT ride_id
                    FROM raw.citibike_trips
                    GROUP BY ride_id
                    HAVING COUNT(*) > 1
                ) d
            """,
            details="ride_id is the business key and idempotency key.",
        ),
        _simple_count_check(
            engine,
            source_name="citibike_trips",
            dataset_name=dataset,
            check_type="VALIDITY",
            check_name="citibike_trip_duration_valid",
            column_name="started_at,ended_at",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.citibike_trips
                WHERE started_at IS NOT NULL
                  AND ended_at IS NOT NULL
                  AND (
                      ended_at <= started_at
                      OR ended_at - started_at > INTERVAL '24 hours'
                  )
            """,
            expected={"rule": "0 < ended_at-started_at <= 24h"},
        ),
        _simple_count_check(
            engine,
            source_name="citibike_trips",
            dataset_name=dataset,
            check_type="RANGE",
            check_name="citibike_coordinates_in_nyc_envelope",
            column_name="start_lat,start_lng,end_lat,end_lng",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.citibike_trips
                WHERE
                    (start_lat IS NOT NULL AND NOT (start_lat BETWEEN 40.0 AND 42.0))
                    OR (start_lng IS NOT NULL AND NOT (start_lng BETWEEN -75.0 AND -72.0))
                    OR (end_lat IS NOT NULL AND NOT (end_lat BETWEEN 40.0 AND 42.0))
                    OR (end_lng IS NOT NULL AND NOT (end_lng BETWEEN -75.0 AND -72.0))
            """,
            expected={"lat": [40.0, 42.0], "lon": [-75.0, -72.0]},
        ),
        _type_check(
            engine,
            source_name="citibike_trips",
            dataset_name=dataset,
            schema_name="raw",
            table_name="citibike_trips",
            expected_types={
                "ride_id": "text",
                "started_at": "timestamp with time zone",
                "ended_at": "timestamp with time zone",
                "start_lat": "double precision",
                "start_lng": "double precision",
            },
        ),
    ]

    sla = int(cfg.get("freshness_hours", {}).get("citibike_trips", 1488))
    checks.append(
        _freshness_check(
            engine,
            source_name="citibike_trips",
            dataset_name=dataset,
            check_name="citibike_monthly_freshness",
            max_timestamp_sql="SELECT MAX(started_at) AS value_ts FROM raw.citibike_trips",
            sla_hours=sla,
        )
    )
    return checks


def _weather_checks(engine: Engine, cfg: dict[str, Any]) -> list[DQResult]:
    dataset = "raw.weather_hourly"
    checks = [
        _simple_count_check(
            engine,
            source_name="weather",
            dataset_name=dataset,
            check_type="COMPLETENESS",
            check_name="weather_required_values",
            column_name="observed_at,temperature_2m,relative_humidity_2m",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.weather_hourly
                WHERE observed_at IS NULL
                   OR temperature_2m IS NULL
                   OR relative_humidity_2m IS NULL
            """,
        ),
        _simple_count_check(
            engine,
            source_name="weather",
            dataset_name=dataset,
            check_type="UNIQUENESS",
            check_name="weather_timestamp_unique",
            column_name="observed_at",
            fail_sql="""
                SELECT COUNT(*)
                FROM (
                    SELECT observed_at
                    FROM raw.weather_hourly
                    GROUP BY observed_at
                    HAVING COUNT(*) > 1
                ) d
            """,
        ),
        _simple_count_check(
            engine,
            source_name="weather",
            dataset_name=dataset,
            check_type="RANGE",
            check_name="weather_physical_ranges",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.weather_hourly
                WHERE (temperature_2m IS NOT NULL AND NOT (temperature_2m BETWEEN -80 AND 60))
                   OR (relative_humidity_2m IS NOT NULL
                       AND NOT (relative_humidity_2m BETWEEN 0 AND 100))
                   OR (precipitation IS NOT NULL AND precipitation < 0)
                   OR (rain IS NOT NULL AND rain < 0)
                   OR (snowfall IS NOT NULL AND snowfall < 0)
                   OR (wind_speed_10m IS NOT NULL AND wind_speed_10m < 0)
            """,
        ),
    ]
    sla = int(cfg.get("freshness_hours", {}).get("weather", 72))
    checks.append(
        _freshness_check(
            engine,
            source_name="weather",
            dataset_name=dataset,
            check_name="weather_hourly_freshness",
            max_timestamp_sql="SELECT MAX(observed_at) AS value_ts FROM raw.weather_hourly",
            sla_hours=sla,
        )
    )
    return checks


def _traffic_checks(engine: Engine, cfg: dict[str, Any]) -> list[DQResult]:
    dataset = "raw.traffic_speed"
    checks = [
        _simple_count_check(
            engine,
            source_name="traffic",
            dataset_name=dataset,
            check_type="COMPLETENESS",
            check_name="traffic_required_fields",
            column_name="link_id,data_as_of,speed,travel_time",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.traffic_speed
                WHERE link_id IS NULL
                   OR data_as_of IS NULL
                   OR speed IS NULL
                   OR travel_time IS NULL
            """,
        ),
        _simple_count_check(
            engine,
            source_name="traffic",
            dataset_name=dataset,
            check_type="UNIQUENESS",
            check_name="traffic_business_key_unique",
            column_name="link_id,data_as_of",
            fail_sql="""
                SELECT COUNT(*)
                FROM (
                    SELECT link_id, data_as_of
                    FROM raw.traffic_speed
                    GROUP BY link_id, data_as_of
                    HAVING COUNT(*) > 1
                ) d
            """,
        ),
        _simple_count_check(
            engine,
            source_name="traffic",
            dataset_name=dataset,
            check_type="RANGE",
            check_name="traffic_measure_ranges",
            column_name="speed,travel_time",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.traffic_speed
                WHERE (speed IS NOT NULL AND NOT (speed BETWEEN 0 AND 150))
                   OR (travel_time IS NOT NULL AND NOT (travel_time BETWEEN 0 AND 86400))
            """,
            expected={"speed_mph": [0, 150], "travel_time_seconds": [0, 86400]},
        ),
    ]
    sla = int(cfg.get("freshness_hours", {}).get("traffic", 12))
    checks.append(
        _freshness_check(
            engine,
            source_name="traffic",
            dataset_name=dataset,
            check_name="traffic_freshness",
            max_timestamp_sql="SELECT MAX(data_as_of) AS value_ts FROM raw.traffic_speed",
            sla_hours=sla,
        )
    )
    return checks


def _gbfs_checks(engine: Engine, cfg: dict[str, Any]) -> list[DQResult]:
    dataset = "raw.gbfs_station_status"
    checks = [
        _simple_count_check(
            engine,
            source_name="citibike_gbfs",
            dataset_name=dataset,
            check_type="REFERENTIAL_INTEGRITY",
            check_name="gbfs_status_has_station_information",
            column_name="station_id",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.gbfs_station_status s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM raw.gbfs_station_information i
                    WHERE i.station_id = s.station_id
                )
            """,
            details="Every station-status record must resolve to station information.",
        ),
        _simple_count_check(
            engine,
            source_name="citibike_gbfs",
            dataset_name=dataset,
            check_type="VALIDITY",
            check_name="gbfs_availability_non_negative",
            column_name="num_bikes_available,num_docks_available",
            fail_sql="""
                SELECT COUNT(*)
                FROM raw.gbfs_station_status
                WHERE num_bikes_available < 0
                   OR num_docks_available < 0
            """,
        ),
    ]
    sla = int(cfg.get("freshness_hours", {}).get("citibike_gbfs", 2))
    checks.append(
        _freshness_check(
            engine,
            source_name="citibike_gbfs",
            dataset_name=dataset,
            check_name="gbfs_freshness",
            max_timestamp_sql="SELECT MAX(observed_at) AS value_ts FROM raw.gbfs_station_status",
            sla_hours=sla,
        )
    )
    return checks


RUNNERS: dict[str, Callable[[Engine, dict[str, Any]], list[DQResult]]] = {
    "citibike_trips": _citibike_checks,
    "weather": _weather_checks,
    "traffic": _traffic_checks,
    "gbfs": _gbfs_checks,
}


def run_quality_checks(
    config: dict[str, Any],
    *,
    dataset: str = "all",
    engine: Engine | None = None,
) -> list[DQResult]:
    """Run selected database checks and persist every result."""
    db = engine or get_engine()
    quality_cfg = config.get("quality", {})

    names = list(RUNNERS) if dataset == "all" else [dataset]
    results: list[DQResult] = []

    for name in names:
        runner = RUNNERS.get(name)
        if runner is None:
            raise ValueError(f"Unknown DQ dataset: {name}")
        for result in runner(db, quality_cfg):
            _persist(db, result)
            results.append(result)

    return results


def summarize(results: list[DQResult]) -> dict[str, int]:
    summary = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return summary
