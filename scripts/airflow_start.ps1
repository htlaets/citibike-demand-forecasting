$ErrorActionPreference = "Stop"

$compose = @(
    "-f", "docker-compose.yml",
    "-f", "docker-compose.airflow.yml"
)

Write-Host "Building Airflow image..."
docker compose @compose build airflow-init

Write-Host "Starting Airflow metadata DB and project PostgreSQL..."
docker compose @compose up -d airflow-db postgres

Write-Host "Running Airflow DB migration..."
docker compose @compose run --rm airflow-init

Write-Host "Starting Airflow components..."
docker compose @compose up -d `
    airflow-api-server `
    airflow-scheduler `
    airflow-dag-processor `
    airflow-triggerer

Write-Host ""
Write-Host "Airflow containers:"
docker compose @compose ps
Write-Host ""
Write-Host "UI: http://localhost:8080"
Write-Host "Username: admin"
Write-Host "Get generated password with:"
Write-Host 'docker compose -f docker-compose.yml -f docker-compose.airflow.yml exec airflow-api-server cat /opt/airflow/simple_auth_manager_passwords.json.generated'
