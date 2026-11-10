$ErrorActionPreference = "Stop"

$compose = @(
    "-f", "docker-compose.yml",
    "-f", "docker-compose.airflow.yml"
)

Write-Host "Airflow version:"
docker compose @compose exec airflow-api-server airflow version

Write-Host ""
Write-Host "DAGs:"
docker compose @compose exec airflow-api-server airflow dags list

Write-Host ""
Write-Host "Import errors:"
docker compose @compose exec airflow-api-server airflow dags list-import-errors

Write-Host ""
Write-Host "Project DB health from scheduler container:"
docker compose @compose exec airflow-scheduler python -c "from citibike_pipeline.database.connection import database_healthcheck; assert database_healthcheck(); print('PROJECT DB OK')"

Write-Host ""
Write-Host "dbt debug from scheduler container:"
docker compose @compose exec airflow-scheduler python -c "from citibike_pipeline.transform import run_dbt; raise SystemExit(run_dbt(('debug',)))"
