# Оркестрация Apache Airflow

Проект использует Apache Airflow 3.4 с LocalExecutor в Docker.

Метаданные Airflow хранятся отдельно в `airflow-db`. Предметные данные остаются в `citibike-postgres`.

## DAG `citibike_daily_pipeline`

Расписание: ежедневно в `06:15 America/New_York`.

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

Ежедневный DAG не перестраивает многомиллионный `silver.fact_trip`, поскольку архив поездок обновляется помесячно.

## DAG `citibike_monthly_trips`

Расписание: 7-го числа каждого месяца в 05:00.

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
      |
SCD2 + fact + dbt
```

Для обоих DAG настроены:

- `catchup=False`;
- `max_active_runs=1`;
- retries;
- retry delay.

## Запуск

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\airflow_start.ps1
```

UI:

```text
http://localhost:8080
```

Пользователь: `admin`.

Получить сгенерированный пароль:

```powershell
docker compose -f docker-compose.yml -f docker-compose.airflow.yml exec airflow-api-server cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

## Проверка

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\airflow_check.ps1
```

Проверяются:

- версия Airflow;
- оба DAG;
- отсутствие import errors;
- доступность проектной БД из scheduler;
- `dbt debug`.

Для демонстрации достаточно вручную запустить `citibike_daily_pipeline`. Ежемесячный DAG рекомендуется не запускать без необходимости, поскольку он загружает крупный архив поездок.
