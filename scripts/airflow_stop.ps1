$compose = @(
    "-f", "docker-compose.yml",
    "-f", "docker-compose.airflow.yml"
)

docker compose @compose stop `
    airflow-api-server `
    airflow-scheduler `
    airflow-dag-processor `
    airflow-triggerer `
    airflow-db
