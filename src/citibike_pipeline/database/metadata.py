"""Pipeline metadata: load journal and incremental watermarks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from citibike_pipeline.database.connection import get_engine


@dataclass(frozen=True)
class Watermark:
    source_name: str
    value: str | None
    timestamp: datetime | None


def get_watermark(source_name: str, engine: Engine | None = None) -> Watermark:
    db = engine or get_engine()
    with db.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT source_name, watermark_value, watermark_ts
                FROM meta.etl_watermark
                WHERE source_name = :source_name
                """
            ),
            {"source_name": source_name},
        ).mappings().one()
    return Watermark(row["source_name"], row["watermark_value"], row["watermark_ts"])


def set_watermark(
    source_name: str,
    *,
    value: str | None = None,
    timestamp: datetime | None = None,
    engine: Engine | None = None,
) -> None:
    db = engine or get_engine()
    with db.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO meta.etl_watermark
                    (source_name, watermark_value, watermark_ts, updated_at)
                VALUES (:source_name, :value, :timestamp, CURRENT_TIMESTAMP)
                ON CONFLICT (source_name) DO UPDATE SET
                    watermark_value = COALESCE(EXCLUDED.watermark_value,
                                               meta.etl_watermark.watermark_value),
                    watermark_ts = COALESCE(EXCLUDED.watermark_ts,
                                             meta.etl_watermark.watermark_ts),
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"source_name": source_name, "value": value, "timestamp": timestamp},
        )


def start_load(
    source_name: str,
    *,
    run_key: str | None = None,
    watermark_from: str | None = None,
    pipeline_name: str = "main_ingestion",
    engine: Engine | None = None,
) -> int:
    db = engine or get_engine()
    with db.begin() as connection:
        return int(
            connection.execute(
                text(
                    """
                    INSERT INTO meta.etl_load_log
                        (source_name, pipeline_name, run_key, watermark_from, status)
                    VALUES (:source_name, :pipeline_name, :run_key, :watermark_from, 'RUNNING')
                    RETURNING load_id
                    """
                ),
                {
                    "source_name": source_name,
                    "pipeline_name": pipeline_name,
                    "run_key": run_key,
                    "watermark_from": watermark_from,
                },
            ).scalar_one()
        )


def finish_load(
    load_id: int,
    *,
    status: str,
    watermark_to: str | None = None,
    rows_received: int = 0,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_rejected: int = 0,
    raw_location: str | None = None,
    retry_count: int = 0,
    error: Exception | None = None,
    engine: Engine | None = None,
) -> None:
    db = engine or get_engine()
    with db.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE meta.etl_load_log
                SET finished_at = CURRENT_TIMESTAMP,
                    status = :status,
                    watermark_to = :watermark_to,
                    rows_received = :rows_received,
                    rows_inserted = :rows_inserted,
                    rows_updated = :rows_updated,
                    rows_rejected = :rows_rejected,
                    raw_location = :raw_location,
                    retry_count = :retry_count,
                    error_type = :error_type,
                    error_message = :error_message
                WHERE load_id = :load_id
                """
            ),
            {
                "load_id": load_id,
                "status": status,
                "watermark_to": watermark_to,
                "rows_received": max(0, int(rows_received)),
                "rows_inserted": max(0, int(rows_inserted)),
                "rows_updated": max(0, int(rows_updated)),
                "rows_rejected": max(0, int(rows_rejected)),
                "raw_location": raw_location,
                "retry_count": max(0, int(retry_count)),
                "error_type": type(error).__name__ if error else None,
                "error_message": str(error)[:4000] if error else None,
            },
        )


def list_watermarks(engine: Engine | None = None) -> list[dict[str, Any]]:
    db = engine or get_engine()
    with db.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT source_name, watermark_value, watermark_ts, updated_at
                    FROM meta.etl_watermark
                    ORDER BY source_name
                    """
                )
            ).mappings()
        ]
