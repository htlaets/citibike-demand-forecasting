"""Daily operational orchestration for the Citi Bike forecasting platform."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task


@task(retries=2, retry_delay=timedelta(minutes=2))
def database_health() -> dict[str, bool]:
    from citibike_pipeline.database.connection import database_healthcheck

    healthy = database_healthcheck()
    if not healthy:
        raise RuntimeError("Project PostgreSQL health check failed")
    return {"database_healthy": True}


@task(retries=3, retry_delay=timedelta(minutes=3))
def ingest_gbfs() -> object:
    from citibike_pipeline.config import load_config
    from citibike_pipeline.database.connection import get_engine
    from citibike_pipeline.http import HttpClient
    from citibike_pipeline.ingestion import gbfs

    config = load_config()
    return gbfs.ingest(HttpClient(config["http"]), config, engine=get_engine())


@task(retries=3, retry_delay=timedelta(minutes=3))
def ingest_weather() -> object:
    from citibike_pipeline.config import load_config
    from citibike_pipeline.database.connection import get_engine
    from citibike_pipeline.http import HttpClient
    from citibike_pipeline.ingestion import weather

    config = load_config()
    return weather.ingest(HttpClient(config["http"]), config, engine=get_engine())


@task(retries=3, retry_delay=timedelta(minutes=3))
def ingest_traffic() -> object:
    from citibike_pipeline.config import load_config
    from citibike_pipeline.database.connection import get_engine
    from citibike_pipeline.http import HttpClient
    from citibike_pipeline.ingestion import traffic

    config = load_config()
    return traffic.ingest(HttpClient(config["http"]), config, engine=get_engine())


@task(retries=1, retry_delay=timedelta(minutes=2))
def run_data_quality() -> dict[str, int]:
    from citibike_pipeline.config import load_config
    from citibike_pipeline.database.connection import get_engine
    from citibike_pipeline.quality import (
        quarantine_invalid_records,
        run_quality_checks,
        summarize,
    )

    config = load_config()
    engine = get_engine()
    results = run_quality_checks(config, dataset="all", engine=engine)
    quarantine_invalid_records(dataset="all", engine=engine)
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


@task(retries=1, retry_delay=timedelta(minutes=3))
def build_incremental_marts() -> dict[str, str]:
    from citibike_pipeline.transform import run_dbt

    run_dbt(("build",))
    return {"dbt": "build completed"}


@dag(
    dag_id="citibike_daily_pipeline",
    description="Daily GBFS/weather/traffic ingestion, DQ, schema guard and dbt marts",
    schedule="15 06 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="America/New_York"),
    catchup=False,
    max_active_runs=1,
    tags=["citibike", "daily", "data-engineering"],
)
def citibike_daily_pipeline():
    health = database_health()

    gbfs_task = ingest_gbfs()
    weather_task = ingest_weather()
    traffic_task = ingest_traffic()

    health >> [gbfs_task, weather_task, traffic_task]

    quality = run_data_quality()
    [gbfs_task, weather_task, traffic_task] >> quality

    schema = schema_drift_guard()
    marts = build_incremental_marts()

    quality >> schema >> marts


citibike_daily_pipeline()
