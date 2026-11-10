$ErrorActionPreference = "Stop"

$compose = @(
    "-f", "docker-compose.yml",
    "-f", "docker-compose.superset.yml"
)

function Assert-ExitCode {
    param([string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Building Superset image with PostgreSQL driver..."
docker compose @compose build superset-init superset
Assert-ExitCode "Superset image build"

Write-Host "Starting Superset metadata PostgreSQL and project PostgreSQL..."
docker compose @compose up -d superset-db postgres
Assert-ExitCode "PostgreSQL startup"

Write-Host "Running idempotent Superset bootstrap..."
docker compose @compose run --rm superset-init
Assert-ExitCode "Superset bootstrap"

Write-Host "Starting Superset web application..."
docker compose @compose up -d superset
Assert-ExitCode "Superset web startup"

Write-Host ""
docker compose @compose ps
Assert-ExitCode "Compose status"

Write-Host ""
Write-Host "Superset: http://localhost:8088"
Write-Host "Username: admin"
Write-Host "Password: admin (unless overridden in .env)"
