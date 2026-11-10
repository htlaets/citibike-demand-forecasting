# Apache Airflow orchestration

The project uses Apache Airflow 3.4 with LocalExecutor inside Linux containers.
Airflow metadata is isolated in its own PostgreSQL service (`airflow-db`);
business data remains in the existing `citibike-postgres` service.

## DAGs

### `citibike_daily_pipeline`

Schedule: `06:15 America/New_York`, daily.

Flow:

```text
database_health
      |
      +------------------+------------------+
      |                  |                  |
 ingest_gbfs       ingest_weather     ingest_traffic
      |                  |                  |
      +------------------+------------------+
                         |
                  run_data_quality
                         |
                  schema_drift_guard
                         |
                 build_incremental_marts
```

The daily DAG intentionally does **not** rebuild `silver.fact_trip`; that table
contains millions of rows and changes only when a new monthly Citi Bike trip
archive arrives.

### `citibike_monthly_trips`

Schedule: 05:00 America/New_York on the 7th of each month.

```text
database_health
      |
ingest_next_trip_month
      |
validate_trip_data
      |
schema_drift_guard
      |
rebuild_trip_models
  - SCD2 station sync
  - incremental fact load
  - dbt build
```

Both DAGs use `catchup=False`, `max_active_runs=1`, retries and retry delays.

## Start on Windows / Docker Desktop

Airflow itself runs inside Linux containers; do not install it into the Windows
project virtual environment.

```powershell
.\scripts\airflow_start.ps1
```

Then open:

```text
http://localhost:8080
```

User: `admin`.

The SimpleAuthManager generates the password on first API-server startup. Read it:

```powershell
docker compose -f docker-compose.yml -f docker-compose.airflow.yml exec airflow-api-server cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

## Smoke test

```powershell
.\scripts\airflow_check.ps1
```

Expected:
- Airflow version 3.4.0;
- both project DAG IDs are listed;
- no DAG import errors;
- project PostgreSQL health check succeeds;
- dbt debug succeeds.

DAGs are paused at creation deliberately. For the first demonstration, trigger
`citibike_daily_pipeline` manually in the UI. Leave the monthly DAG paused until
you actually want to download the next large Citi Bike monthly archive.

## Stop

```powershell
.\scripts\airflow_stop.ps1
```

The metadata DB and Airflow home use named Docker volumes, so stopping containers
does not delete metadata, task history, logs, or the generated admin password.
