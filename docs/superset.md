# Apache Superset dashboards

The project pins Apache Superset 6.0.0 and runs it in Docker on the same
`citibike-network` as PostgreSQL.

Superset has a dedicated PostgreSQL metadata database. Analytical data remains
in the project `citibike` database.

## Start

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_start.ps1
```

Open:

```text
http://localhost:8088
```

Default local credentials:

```text
admin / admin
```

You can override them with `SUPERSET_ADMIN_USERNAME`,
`SUPERSET_ADMIN_PASSWORD` and `SUPERSET_ADMIN_EMAIL` in `.env`.

The bootstrap is idempotent: rerunning the start script updates the connection,
serving views, datasets, chart definitions and dashboard layouts instead of
creating duplicate dashboards.

## Demand & Forecast dashboard

Slug: `citibike-demand-forecast`

Contains:

1. total rides started;
2. final CatBoost test WAPE;
3. actual vs CatBoost forecast by hour;
4. top stations by rides started;
5. demand and traffic over time;
6. model evaluation table with MAE/RMSE/WAPE.

It answers:

- how demand changes over time;
- where demand is concentrated;
- whether the production model improves on the baseline;
- how closely forecasts follow actual demand;
- whether road traffic covaries with demand.

## Data Platform Operations dashboard

Slug: `citibike-platform-operations`

Contains:

1. successful ingestion runs;
2. failed ingestion runs;
3. inserted rows by source;
4. ingestion duration by source;
5. DQ failed rows by check category;
6. recent load journal;
7. persisted data-quality results.

It exposes ingestion reliability, throughput, retries/failures and all required
DQ categories.

## Serving views

The bootstrap creates compact GOLD views so Superset never has to repeatedly
aggregate the million-row station-hour mart for every dashboard render:

- `gold.superset_hourly_demand`;
- `gold.superset_top_stations`;
- `gold.superset_forecast_comparison`;
- `gold.superset_model_metrics`;
- `gold.superset_model_kpi`;
- `gold.superset_pipeline_kpi`;
- `gold.superset_dq_summary`.

## Smoke check

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_check.ps1
```

Expected:

```text
Superset 6.0.0
Health endpoint: OK
[OK] Citi Bike — Demand & Forecast: ... charts=6 published=True
[OK] Citi Bike — Data Platform Operations: ... charts=7 published=True
[OK] project charts: 13
```

## Stop

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_stop.ps1
```

Named Docker volumes preserve Superset metadata between restarts.
