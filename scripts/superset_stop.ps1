$compose = @(
    "-f", "docker-compose.yml",
    "-f", "docker-compose.superset.yml"
)

docker compose @compose stop superset superset-db
