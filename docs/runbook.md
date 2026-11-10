# Инструкция запуска и диагностики

## Требования

- Windows 10/11 или Linux/macOS;
- Python 3.11+;
- Docker Desktop / Docker Engine;
- Git.

На Windows команды ниже предполагают PowerShell.

## 1. Python

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,transform,ml]"
```

Проверка:

```powershell
pytest
```

## 2. Конфигурация

```powershell
Copy-Item .env.example .env
```

Если `5432` занят:

```text
POSTGRES_PORT=5433
DATABASE_URL=postgresql+psycopg://citibike:citibike@127.0.0.1:5433/citibike
```

Важно: внутри Docker Airflow и Superset подключаются к сервису `postgres:5432`; host-порт `5433` нужен только для доступа с Windows.

## 3. PostgreSQL

```powershell
docker compose up -d postgres
docker compose ps
citibike-pipeline db-health
```

## 4. Ingestion

```powershell
citibike-pipeline ingest --source citibike_trips --start-month 2026-09 --end-month 2026-09
citibike-pipeline ingest --source weather --start-date 2026-09-01 --end-date 2026-09-30
citibike-pipeline ingest --source traffic --traffic-start-date 2026-09-01 --traffic-end-date 2026-09-30
citibike-pipeline ingest --source citibike_gbfs
citibike-pipeline watermarks
```

Повторный запуск того же периода должен быть идемпотентным.

## 5. DQ

```powershell
citibike-pipeline dq --dataset all --quarantine
citibike-pipeline schema-check
```

## 6. SILVER/GOLD

```powershell
citibike-pipeline dbt --command debug
citibike-pipeline transform
```

## 7. ML

```powershell
citibike-pipeline train --smoke
citibike-pipeline train
citibike-pipeline model-metrics
```

## 8. Airflow

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\airflow_start.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\airflow_check.ps1
```

UI:

```text
http://localhost:8080
```

Для демонстрации вручную запустить `citibike_daily_pipeline`.

## 9. Superset

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_start.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\superset_check.ps1
```

UI:

```text
http://localhost:8088
```

## 10. Финальная проверка

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\final_check.ps1
```

## Диагностика

### PostgreSQL не запускается из-за порта

Изменить `POSTGRES_PORT` и `DATABASE_URL` в `.env`.

### Docker пишет `Found orphan containers`

При использовании разных Compose-файлов Docker может считать контейнеры Airflow или Superset orphan-контейнерами. Это предупреждение не означает ошибку.

Не использовать `--remove-orphans`, если требуется сохранить параллельно запущенные компоненты проекта.

### Airflow

Логи:

```powershell
docker compose -f docker-compose.yml -f docker-compose.airflow.yml logs --tail=100 airflow-scheduler
docker compose -f docker-compose.yml -f docker-compose.airflow.yml logs --tail=100 airflow-api-server
```

### Superset

Логи:

```powershell
docker compose -f docker-compose.yml -f docker-compose.superset.yml logs --tail=100 superset
```

Bootstrap вручную:

```powershell
docker compose -f docker-compose.yml -f docker-compose.superset.yml run --rm superset-init
```

### Состояние всех контейнеров

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
