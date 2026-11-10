$ErrorActionPreference = "Stop"

$compose = @(
    "-f", "docker-compose.yml",
    "-f", "docker-compose.superset.yml"
)

Write-Host "Superset version:"
docker compose @compose exec superset superset version

Write-Host ""
Write-Host "Health endpoint:"
docker compose @compose exec superset python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8088/health', timeout=10).read().decode())"

Write-Host ""
Write-Host "Bootstrap asset counts:"
docker compose @compose exec superset python /app/pythonpath/check_assets.py
