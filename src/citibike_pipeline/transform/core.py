"""PostgreSQL transformations that preserve warehouse constraints.

Station dimension management is implemented in Python/SQL because the project
already owns a constrained SCD2 table with a surrogate identity key. dbt builds
the remaining SILVER/GOLD analytical relations on top of that dimension.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from citibike_pipeline.database.connection import get_engine

STATION_CANDIDATES_SQL = """
CREATE TEMP TABLE tmp_station_candidates ON COMMIT DROP AS
WITH trip_start AS (
    SELECT DISTINCT ON (start_station_id)
        start_station_id AS station_id,
        COALESCE(NULLIF(BTRIM(start_station_name), ''), start_station_id) AS station_name,
        start_lat AS latitude,
        start_lng AS longitude,
        NULL::INTEGER AS capacity,
        started_at AS observed_at,
        1 AS source_priority
    FROM raw.citibike_trips
    WHERE start_station_id IS NOT NULL
      AND BTRIM(start_station_id) <> ''
      AND started_at IS NOT NULL
    ORDER BY start_station_id, started_at DESC
),
trip_end AS (
    SELECT DISTINCT ON (end_station_id)
        end_station_id AS station_id,
        COALESCE(NULLIF(BTRIM(end_station_name), ''), end_station_id) AS station_name,
        end_lat AS latitude,
        end_lng AS longitude,
        NULL::INTEGER AS capacity,
        ended_at AS observed_at,
        1 AS source_priority
    FROM raw.citibike_trips
    WHERE end_station_id IS NOT NULL
      AND BTRIM(end_station_id) <> ''
      AND ended_at IS NOT NULL
    ORDER BY end_station_id, ended_at DESC
),
gbfs AS (
    SELECT DISTINCT ON (station_id)
        station_id,
        COALESCE(NULLIF(BTRIM(station_name), ''), station_id) AS station_name,
        latitude,
        longitude,
        capacity,
        observed_at,
        2 AS source_priority
    FROM raw.gbfs_station_information
    WHERE station_id IS NOT NULL
      AND BTRIM(station_id) <> ''
    ORDER BY station_id, observed_at DESC
),
combined AS (
    SELECT * FROM trip_start
    UNION ALL
    SELECT * FROM trip_end
    UNION ALL
    SELECT * FROM gbfs
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY station_id
            ORDER BY source_priority DESC, observed_at DESC
        ) AS rn
    FROM combined
)
SELECT
    station_id,
    station_name,
    latitude,
    longitude,
    capacity,
    observed_at AS valid_from,
    MD5(
        COALESCE(station_name, '') || '|' ||
        COALESCE(ROUND(latitude::numeric, 6)::text, '') || '|' ||
        COALESCE(ROUND(longitude::numeric, 6)::text, '') || '|' ||
        COALESCE(capacity::text, '')
    ) AS record_hash
FROM ranked
WHERE rn = 1;
"""

CLOSE_CHANGED_STATIONS_SQL = """
UPDATE silver.dim_station d
SET
    valid_to = GREATEST(c.valid_from, d.valid_from + INTERVAL '1 microsecond'),
    is_current = FALSE
FROM tmp_station_candidates c
WHERE d.station_id = c.station_id
  AND d.is_current
  AND d.record_hash <> c.record_hash;
"""

INSERT_STATIONS_SQL = """
INSERT INTO silver.dim_station (
    station_id,
    station_name,
    latitude,
    longitude,
    capacity,
    valid_from,
    valid_to,
    is_current,
    record_hash
)
SELECT
    c.station_id,
    c.station_name,
    c.latitude,
    c.longitude,
    c.capacity,
    c.valid_from,
    NULL,
    TRUE,
    c.record_hash
FROM tmp_station_candidates c
LEFT JOIN silver.dim_station d
  ON d.station_id = c.station_id
 AND d.is_current
WHERE d.station_sk IS NULL
   OR d.record_hash <> c.record_hash;
"""

FACT_TRIP_SQL = """
INSERT INTO silver.fact_trip (
    ride_id,
    started_at,
    ended_at,
    start_station_sk,
    end_station_sk,
    rideable_type,
    member_casual,
    duration_seconds
)
SELECT
    t.ride_id,
    t.started_at,
    t.ended_at,
    ds.station_sk,
    de.station_sk,
    t.rideable_type,
    t.member_casual,
    EXTRACT(EPOCH FROM (t.ended_at - t.started_at))::INTEGER AS duration_seconds
FROM raw.citibike_trips t
LEFT JOIN silver.dim_station ds
  ON ds.station_id = t.start_station_id
 AND ds.is_current
LEFT JOIN silver.dim_station de
  ON de.station_id = t.end_station_id
 AND de.is_current
WHERE t.started_at IS NOT NULL
  AND t.ended_at IS NOT NULL
  AND t.start_station_id IS NOT NULL
  AND BTRIM(t.start_station_id) <> ''
  AND t.ended_at > t.started_at
  AND t.ended_at - t.started_at <= INTERVAL '24 hours'
  AND NOT EXISTS (
      SELECT 1
      FROM quarantine.rejected_records q
      WHERE q.source_name = 'citibike_trips'
        AND q.dataset_name = 'raw.citibike_trips'
        AND q.natural_key = t.ride_id
        AND q.rejection_reason IN (
            'missing_start_station_or_time',
            'invalid_trip_duration',
            'invalid_coordinates'
        )
  )
ON CONFLICT (ride_id) DO NOTHING;
"""


def sync_station_dimension(engine: Engine | None = None) -> dict[str, int]:
    """Synchronize the current station state using SCD Type 2 semantics.

    A changed station closes the previous current version and creates a new
    current version. Re-running with identical source state inserts no versions.
    """
    db = engine or get_engine()
    with db.begin() as connection:
        before = int(
            connection.execute(text("SELECT COUNT(*) FROM silver.dim_station")).scalar_one()
        )
        connection.execute(text(STATION_CANDIDATES_SQL))
        candidate_count = int(
            connection.execute(text("SELECT COUNT(*) FROM tmp_station_candidates")).scalar_one()
        )
        closed = max(
            0, int(connection.execute(text(CLOSE_CHANGED_STATIONS_SQL)).rowcount or 0)
        )
        inserted = max(
            0, int(connection.execute(text(INSERT_STATIONS_SQL)).rowcount or 0)
        )
        after = int(
            connection.execute(text("SELECT COUNT(*) FROM silver.dim_station")).scalar_one()
        )
        current = int(
            connection.execute(
                text("SELECT COUNT(*) FROM silver.dim_station WHERE is_current")
            ).scalar_one()
        )

    return {
        "candidates": candidate_count,
        "versions_before": before,
        "versions_closed": closed,
        "versions_inserted": inserted,
        "versions_after": after,
        "current_stations": current,
    }


def load_fact_trips(engine: Engine | None = None) -> dict[str, int]:
    """Load valid, non-quarantined trips into the constrained SILVER fact."""
    db = engine or get_engine()
    with db.begin() as connection:
        before = int(
            connection.execute(text("SELECT COUNT(*) FROM silver.fact_trip")).scalar_one()
        )
        result = connection.execute(text(FACT_TRIP_SQL))
        inserted = max(0, int(result.rowcount or 0))
        after = int(
            connection.execute(text("SELECT COUNT(*) FROM silver.fact_trip")).scalar_one()
        )
        unresolved_start = int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM silver.fact_trip
                    WHERE start_station_sk IS NULL
                    """
                )
            ).scalar_one()
        )

    return {
        "rows_before": before,
        "rows_inserted": inserted,
        "rows_after": after,
        "unresolved_start_station": unresolved_start,
    }


def warehouse_counts(engine: Engine | None = None) -> dict[str, Any]:
    db = engine or get_engine()
    with db.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM raw.citibike_trips) AS raw_trips,
                    (SELECT COUNT(*) FROM silver.dim_station) AS station_versions,
                    (SELECT COUNT(*) FROM silver.dim_station WHERE is_current) AS current_stations,
                    (SELECT COUNT(*) FROM silver.fact_trip) AS silver_trips,
                    (SELECT COUNT(*) FROM silver.weather_hourly) AS silver_weather,
                    (SELECT COUNT(*) FROM silver.traffic_hourly) AS silver_traffic,
                    (SELECT COUNT(*) FROM gold.station_hourly_demand) AS gold_rows
                """
            )
        ).mappings().one()
    return dict(row)
