$ErrorActionPreference = "Stop"

function Assert-NativeCommand {
    param([string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "${Step} failed with exit code $LASTEXITCODE"
    }
}

Write-Host "=== 1/8 Python ===" -ForegroundColor Cyan
python --version
Assert-NativeCommand "Python"

Write-Host "`n=== 2/8 Ruff ===" -ForegroundColor Cyan
python -m ruff check src tests
Assert-NativeCommand "Ruff"

Write-Host "`n=== 3/8 pytest ===" -ForegroundColor Cyan
python -m pytest
Assert-NativeCommand "pytest"

Write-Host "`n=== 4/8 PostgreSQL ===" -ForegroundColor Cyan
citibike-pipeline db-health
Assert-NativeCommand "PostgreSQL healthcheck"

Write-Host "`n=== 5/8 dbt tests ===" -ForegroundColor Cyan
citibike-pipeline dbt --command test
Assert-NativeCommand "dbt tests"

Write-Host "`n=== 6/8 Warehouse and ML ===" -ForegroundColor Cyan

docker exec citibike-postgres psql -U citibike -d citibike -c @"
SELECT
    (SELECT COUNT(*) FROM raw.citibike_trips) AS raw_trips,
    (SELECT COUNT(*) FROM silver.fact_trip) AS silver_trips,
    (SELECT COUNT(*) FROM gold.station_hourly_demand) AS gold_rows,
    (SELECT COUNT(*) FROM gold.model_metrics) AS model_metrics,
    (SELECT COUNT(*) FROM gold.forecast_results) AS forecasts;
"@
Assert-NativeCommand "Warehouse counts"

docker exec citibike-postgres psql -U citibike -d citibike -c @"
SELECT
    model_name,
    split_name,
    ROUND(mae::numeric, 3) AS mae,
    ROUND(rmse::numeric, 3) AS rmse,
    ROUND(wape::numeric, 2) AS wape,
    rows_evaluated
FROM gold.model_metrics
ORDER BY evaluated_at DESC, model_name
LIMIT 10;
"@
Assert-NativeCommand "Model metrics"

$containers = @(docker ps --format "{{.Names}}")
Assert-NativeCommand "docker ps"

Write-Host "`n=== 7/8 Airflow ===" -ForegroundColor Cyan
if ($containers -contains "citibike-airflow-api") {
    powershell -ExecutionPolicy Bypass -File .\scripts\airflow_check.ps1
    if ($LASTEXITCODE -ne 0) {
        throw "Airflow check failed with exit code $LASTEXITCODE"
    }
} else {
    Write-Host "[SKIP] Airflow is not running. Start it with scripts\airflow_start.ps1 for a full check." -ForegroundColor Yellow
}

Write-Host "`n=== 8/8 Superset ===" -ForegroundColor Cyan
if ($containers -contains "citibike-superset") {
    powershell -ExecutionPolicy Bypass -File .\scripts\superset_check.ps1
    if ($LASTEXITCODE -ne 0) {
        throw "Superset check failed with exit code $LASTEXITCODE"
    }
} else {
    Write-Host "[SKIP] Superset is not running. Start it with scripts\superset_start.ps1 for a full check." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== FINAL CHECK COMPLETED ===" -ForegroundColor Green
Write-Host "Code, tests, PostgreSQL, dbt and available services were checked." -ForegroundColor Green
