"""Monthly orchestration for the heavy Citi Bike trip-history source."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task


@task(retries=2, retry_delay=timedelta(minutes=2))
def database_health() -> dict[str, bool]:
    from citibike_pipeline.database.connection import database_healthcheck

    if not database_healthcheck():
        raise RuntimeError("Project PostgreSQL health check failed")
    return {"database_healthy": True}


@task(retries=3, retry_delay=timedelta(minutes=10))
def ingest_next_trip_month() -> object:
    from citibike_pipeline.config import load_config
    from citibike_pipeline.database.connection import get_engine
    from citibike_pipeline.http import HttpClient
    from citibike_pipeline.ingestion import citibike_trips

    config = load_config()
    return citibike_trips.ingest(
        HttpClient(config["http"]),
        config,
        engine=get_engine(),
    )


@task(retries=1, retry_delay=timedelta(minutes=3))
def validate_trip_data() -> dict[str, int]:
    from citibike_pipeline.config import load_config
    from citibike_pipeline.database.connection import get_engine
    from citibike_pipeline.quality import (
        quarantine_invalid_records,
        run_quality_checks,
        summarize,
    )

    config = load_config()
    engine = get_engine()
    results = run_quality_checks(config, dataset="citibike_trips", engine=engine)
    quarantine_invalid_records(dataset="citibike_trips", engine=engine)
    return summarize(results)


@task(retries=1, retry_delay=timedelta(minutes=2))
def schema_drift_guard() -> list[dict[str, object]]:
    from citibike_pipeline.quality import check_all_schemas

    results = check_all_schemas()
    breaking = [item for item in results if bool(item.get("breaking"))]
    if breaking:
        names = ", ".join(str(item["dataset"]) for item in breaking)
        raise RuntimeError(f"Breaking schema drift detected: {names}")
    return results


@task(retries=1, retry_delay=timedelta(minutes=5))
def rebuild_trip_models() -> dict[str, object]:
    from citibike_pipeline.database.connection import get_engine
    from citibike_pipeline.transform import load_fact_trips, run_dbt, sync_station_dimension

    engine = get_engine()
    stations = sync_station_dimension(engine)
    facts = load_fact_trips(engine)
    run_dbt(("build",))
    return {"stations": stations, "facts": facts, "dbt": "build completed"}


@dag(
    dag_id="citibike_monthly_trips",
    description="Monthly historical trip ingestion followed by SCD2, fact and dbt refresh",
    schedule="00 05 07 * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="America/New_York"),
    catchup=False,
    max_active_runs=1,
    tags=["citibike", "monthly", "history"],
)
def citibike_monthly_trips():
    health = database_health()
    trips = ingest_next_trip_month()
    quality = validate_trip_data()
    schema = schema_drift_guard()
    models = rebuild_trip_models()

    health >> trips >> quality >> schema >> models


citibike_monthly_trips()
