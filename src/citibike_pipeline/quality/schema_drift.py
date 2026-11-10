"""Schema registry and drift detection for managed PostgreSQL datasets."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import Engine, text

from citibike_pipeline.database.connection import get_engine

MANAGED_DATASETS = (
    ("raw", "citibike_trips"),
    ("raw", "weather_hourly"),
    ("raw", "traffic_speed"),
    ("raw", "gbfs_station_information"),
    ("raw", "gbfs_station_status"),
)


def schema_diff(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    old = {str(x["column_name"]): x for x in previous}
    new = {str(x["column_name"]): x for x in current}

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = {
        name: {
            "before": old[name],
            "after": new[name],
        }
        for name in sorted(set(old) & set(new))
        if (
            old[name].get("data_type"),
            old[name].get("is_nullable"),
        )
        != (
            new[name].get("data_type"),
            new[name].get("is_nullable"),
        )
    }
    return {"added": added, "removed": removed, "changed": changed}


def _definition(engine: Engine, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    ordinal_position
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                ORDER BY ordinal_position
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        ).mappings()
        return [dict(row) for row in rows]


def _fingerprint(definition: list[dict[str, Any]]) -> str:
    payload = json.dumps(definition, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def check_dataset_schema(
    schema_name: str,
    table_name: str,
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db = engine or get_engine()
    dataset_name = f"{schema_name}.{table_name}"
    current = _definition(db, schema_name, table_name)
    if not current:
        raise ValueError(f"Dataset does not exist: {dataset_name}")

    current_hash = _fingerprint(current)

    with db.connect() as connection:
        previous = connection.execute(
            text(
                """
                SELECT schema_version, schema_definition, schema_hash
                FROM meta.schema_registry
                WHERE dataset_name = :dataset_name
                  AND is_current
                """
            ),
            {"dataset_name": dataset_name},
        ).mappings().one_or_none()

    if previous is None:
        with db.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO meta.schema_registry (
                        dataset_name, schema_version, schema_definition,
                        schema_hash, is_current
                    )
                    VALUES (
                        :dataset_name, 1, CAST(:definition AS jsonb),
                        :schema_hash, TRUE
                    )
                    """
                ),
                {
                    "dataset_name": dataset_name,
                    "definition": json.dumps(current, default=str),
                    "schema_hash": current_hash,
                },
            )
        return {
            "dataset": dataset_name,
            "status": "REGISTERED",
            "version": 1,
            "breaking": False,
            "changes": {"added": [], "removed": [], "changed": {}},
        }

    previous_definition = previous["schema_definition"]
    if isinstance(previous_definition, str):
        previous_definition = json.loads(previous_definition)

    if str(previous["schema_hash"]) == current_hash:
        return {
            "dataset": dataset_name,
            "status": "UNCHANGED",
            "version": int(previous["schema_version"]),
            "breaking": False,
            "changes": {"added": [], "removed": [], "changed": {}},
        }

    diff = schema_diff(list(previous_definition), current)
    breaking = bool(diff["removed"] or diff["changed"])
    new_version = int(previous["schema_version"]) + 1
    action = (
        "Breaking schema drift registered; downstream compatibility must be reviewed."
        if breaking
        else "Compatible additive schema change registered."
    )

    with db.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE meta.schema_registry
                SET is_current = FALSE,
                    effective_to = CURRENT_TIMESTAMP
                WHERE dataset_name = :dataset_name
                  AND is_current
                """
            ),
            {"dataset_name": dataset_name},
        )
        connection.execute(
            text(
                """
                INSERT INTO meta.schema_registry (
                    dataset_name, schema_version, schema_definition,
                    schema_hash, is_current
                )
                VALUES (
                    :dataset_name, :version, CAST(:definition AS jsonb),
                    :schema_hash, TRUE
                )
                """
            ),
            {
                "dataset_name": dataset_name,
                "version": new_version,
                "definition": json.dumps(current, default=str),
                "schema_hash": current_hash,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO meta.schema_changes (
                    dataset_name, previous_version, new_version,
                    change_type, changed_columns, is_breaking, action_taken
                )
                VALUES (
                    :dataset_name, :previous_version, :new_version,
                    'SCHEMA_DRIFT', CAST(:changes AS jsonb), :is_breaking, :action_taken
                )
                """
            ),
            {
                "dataset_name": dataset_name,
                "previous_version": int(previous["schema_version"]),
                "new_version": new_version,
                "changes": json.dumps(diff, default=str),
                "is_breaking": breaking,
                "action_taken": action,
            },
        )

    return {
        "dataset": dataset_name,
        "status": "CHANGED",
        "version": new_version,
        "breaking": breaking,
        "changes": diff,
    }


def check_all_schemas(engine: Engine | None = None) -> list[dict[str, Any]]:
    db = engine or get_engine()
    return [
        check_dataset_schema(schema, table, engine=db)
        for schema, table in MANAGED_DATASETS
    ]
