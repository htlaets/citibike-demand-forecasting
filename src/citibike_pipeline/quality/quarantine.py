"""Persist invalid RAW records into a quarantine layer without deleting source data."""

from __future__ import annotations

from sqlalchemy import Engine, text

from citibike_pipeline.database.connection import get_engine

QUERIES: dict[str, list[tuple[str, str]]] = {
    "citibike_trips": [
        (
            "missing_start_station_or_time",
            """
            INSERT INTO quarantine.rejected_records (
                source_name, dataset_name, load_id, natural_key,
                rejection_reason, failed_checks, record_payload
            )
            SELECT
                'citibike_trips',
                'raw.citibike_trips',
                t.load_id,
                t.ride_id,
                'missing_start_station_or_time',
                '["COMPLETENESS"]'::jsonb,
                jsonb_build_object(
                    'ride_id', t.ride_id,
                    'started_at', t.started_at,
                    'ended_at', t.ended_at,
                    'start_station_id', t.start_station_id,
                    'start_station_name', t.start_station_name
                )
            FROM raw.citibike_trips t
            WHERE (
                    t.started_at IS NULL
                 OR t.ended_at IS NULL
                 OR t.start_station_id IS NULL
                 OR btrim(t.start_station_id) = ''
            )
              AND NOT EXISTS (
                  SELECT 1
                  FROM quarantine.rejected_records q
                  WHERE q.source_name = 'citibike_trips'
                    AND q.dataset_name = 'raw.citibike_trips'
                    AND q.natural_key = t.ride_id
                    AND q.rejection_reason = 'missing_start_station_or_time'
              )
            """,
        ),
        (
            "invalid_trip_duration",
            """
            INSERT INTO quarantine.rejected_records (
                source_name, dataset_name, load_id, natural_key,
                rejection_reason, failed_checks, record_payload
            )
            SELECT
                'citibike_trips',
                'raw.citibike_trips',
                t.load_id,
                t.ride_id,
                'invalid_trip_duration',
                '["VALIDITY"]'::jsonb,
                jsonb_build_object(
                    'ride_id', t.ride_id,
                    'started_at', t.started_at,
                    'ended_at', t.ended_at
                )
            FROM raw.citibike_trips t
            WHERE t.started_at IS NOT NULL
              AND t.ended_at IS NOT NULL
              AND (
                  t.ended_at <= t.started_at
                  OR t.ended_at - t.started_at > INTERVAL '24 hours'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM quarantine.rejected_records q
                  WHERE q.source_name = 'citibike_trips'
                    AND q.dataset_name = 'raw.citibike_trips'
                    AND q.natural_key = t.ride_id
                    AND q.rejection_reason = 'invalid_trip_duration'
              )
            """,
        ),
        (
            "invalid_coordinates",
            """
            INSERT INTO quarantine.rejected_records (
                source_name, dataset_name, load_id, natural_key,
                rejection_reason, failed_checks, record_payload
            )
            SELECT
                'citibike_trips',
                'raw.citibike_trips',
                t.load_id,
                t.ride_id,
                'invalid_coordinates',
                '["RANGE"]'::jsonb,
                jsonb_build_object(
                    'ride_id', t.ride_id,
                    'start_lat', t.start_lat,
                    'start_lng', t.start_lng,
                    'end_lat', t.end_lat,
                    'end_lng', t.end_lng
                )
            FROM raw.citibike_trips t
            WHERE (
                    (t.start_lat IS NOT NULL AND NOT (t.start_lat BETWEEN 40.0 AND 42.0))
                 OR (t.start_lng IS NOT NULL AND NOT (t.start_lng BETWEEN -75.0 AND -72.0))
                 OR (t.end_lat IS NOT NULL AND NOT (t.end_lat BETWEEN 40.0 AND 42.0))
                 OR (t.end_lng IS NOT NULL AND NOT (t.end_lng BETWEEN -75.0 AND -72.0))
            )
              AND NOT EXISTS (
                  SELECT 1
                  FROM quarantine.rejected_records q
                  WHERE q.source_name = 'citibike_trips'
                    AND q.dataset_name = 'raw.citibike_trips'
                    AND q.natural_key = t.ride_id
                    AND q.rejection_reason = 'invalid_coordinates'
              )
            """,
        ),
    ],
    "weather": [
        (
            "invalid_weather_range",
            """
            INSERT INTO quarantine.rejected_records (
                source_name, dataset_name, load_id, natural_key,
                rejection_reason, failed_checks, record_payload
            )
            SELECT
                'weather',
                'raw.weather_hourly',
                w.load_id,
                w.observed_at::text,
                'invalid_weather_range',
                '["RANGE"]'::jsonb,
                jsonb_build_object(
                    'observed_at', w.observed_at,
                    'temperature_2m', w.temperature_2m,
                    'relative_humidity_2m', w.relative_humidity_2m,
                    'precipitation', w.precipitation,
                    'wind_speed_10m', w.wind_speed_10m
                )
            FROM raw.weather_hourly w
            WHERE (
                    (w.temperature_2m IS NOT NULL AND NOT (w.temperature_2m BETWEEN -80 AND 60))
                 OR (w.relative_humidity_2m IS NOT NULL
                     AND NOT (w.relative_humidity_2m BETWEEN 0 AND 100))
                 OR (w.precipitation IS NOT NULL AND w.precipitation < 0)
                 OR (w.rain IS NOT NULL AND w.rain < 0)
                 OR (w.snowfall IS NOT NULL AND w.snowfall < 0)
                 OR (w.wind_speed_10m IS NOT NULL AND w.wind_speed_10m < 0)
            )
              AND NOT EXISTS (
                  SELECT 1
                  FROM quarantine.rejected_records q
                  WHERE q.source_name = 'weather'
                    AND q.dataset_name = 'raw.weather_hourly'
                    AND q.natural_key = w.observed_at::text
                    AND q.rejection_reason = 'invalid_weather_range'
              )
            """,
        ),
    ],
    "traffic": [
        (
            "invalid_traffic_range",
            """
            INSERT INTO quarantine.rejected_records (
                source_name, dataset_name, load_id, natural_key,
                rejection_reason, failed_checks, record_payload
            )
            SELECT
                'traffic',
                'raw.traffic_speed',
                t.load_id,
                t.link_id || ':' || t.data_as_of::text,
                'invalid_traffic_range',
                '["RANGE"]'::jsonb,
                jsonb_build_object(
                    'link_id', t.link_id,
                    'data_as_of', t.data_as_of,
                    'speed', t.speed,
                    'travel_time', t.travel_time
                )
            FROM raw.traffic_speed t
            WHERE (
                    (t.speed IS NOT NULL AND NOT (t.speed BETWEEN 0 AND 150))
                 OR (t.travel_time IS NOT NULL AND NOT (t.travel_time BETWEEN 0 AND 86400))
            )
              AND NOT EXISTS (
                  SELECT 1
                  FROM quarantine.rejected_records q
                  WHERE q.source_name = 'traffic'
                    AND q.dataset_name = 'raw.traffic_speed'
                    AND q.natural_key = t.link_id || ':' || t.data_as_of::text
                    AND q.rejection_reason = 'invalid_traffic_range'
              )
            """,
        ),
    ],
}


def quarantine_invalid_records(
    *,
    dataset: str = "all",
    engine: Engine | None = None,
) -> dict[str, int]:
    db = engine or get_engine()
    names = list(QUERIES) if dataset == "all" else [dataset]
    results: dict[str, int] = {}

    for name in names:
        queries = QUERIES.get(name, [])
        for reason, sql in queries:
            with db.begin() as connection:
                result = connection.execute(text(sql))
                inserted = max(0, int(result.rowcount or 0))
            results[f"{name}:{reason}"] = inserted

    return results
