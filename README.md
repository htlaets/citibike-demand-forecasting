# Прогнозно-аналитическая система мониторинга спроса на Citi Bike

Проект реализует полный цикл прогнозно-аналитической системы по теме:

**«Мониторинг динамики спроса на прокат велосипедов в зависимости от погодных условий и дорожной ситуации в Нью-Йорке».**

Система автоматически получает данные из нескольких внешних источников, сохраняет историю загрузок, контролирует качество и изменение схем данных, формирует аналитические слои PostgreSQL, рассчитывает прогноз спроса на уровне `станция × час` и предоставляет результаты через Apache Superset.

## Основные возможности

- инкрементальная загрузка данных из четырёх внешних источников;
- идемпотентная запись и хранение watermark для каждого источника;
- архитектура хранения `RAW → SILVER → GOLD`;
- журналирование всех загрузок в `meta.etl_load_log`;
- семь категорий контроля качества данных;
- карантин некорректных записей;
- контроль schema drift и ведение реестра схем;
- SCD Type 2 для истории изменений станций;
- трансформации и тесты dbt;
- оркестрация ежедневного и ежемесячного процессов в Apache Airflow;
- Seasonal Naive baseline и CatBoost для прогнозирования спроса;
- временное разделение `train → validation → test` без перемешивания;
- абляционный эксперимент по группам признаков;
- сохранение метрик и прогнозов в GOLD-слое;
- два русскоязычных дашборда Apache Superset;
- автоматические тесты и GitHub Actions CI.

## Архитектура

```mermaid
flowchart LR
    CB[Citi Bike Trip Histories]
    GBFS[Citi Bike GBFS]
    W[Open-Meteo]
    T[NYC DOT Traffic Speeds]

    ING[Python ingestion]
    RAW[(PostgreSQL RAW)]
    DQ[Data Quality]
    Q[(Quarantine)]
    META[(META)]
    SILVER[(PostgreSQL SILVER)]
    DBT[dbt]
    GOLD[(PostgreSQL GOLD)]
    ML[Seasonal Naive + CatBoost]
    AIR[Apache Airflow]
    SUP[Apache Superset]

    CB --> ING
    GBFS --> ING
    W --> ING
    T --> ING

    ING --> RAW
    ING --> META
    RAW --> DQ
    DQ --> Q
    DQ --> SILVER
    DQ --> META
    SILVER --> DBT
    DBT --> GOLD
    GOLD --> ML
    ML --> GOLD
    GOLD --> SUP
    META --> SUP

    AIR -. оркестрация .-> ING
    AIR -. оркестрация .-> DQ
    AIR -. оркестрация .-> DBT
```

Подробное описание приведено в [docs/architecture.md](docs/architecture.md).

## Источники данных

| Источник | Формат | Используемые данные | Назначение |
|---|---|---|---|
| [Citi Bike Trip Histories](https://citibikenyc.com/system-data) | ZIP/CSV | начало и конец поездки, станции, координаты, тип велосипеда, тип пользователя | основной источник исторического спроса |
| [Citi Bike GBFS](https://gbfs.citibikenyc.com/gbfs/gbfs.json) | REST/JSON | сведения о станциях, доступные велосипеды и доки | оперативное состояние станций |
| [Open-Meteo](https://open-meteo.com/) | REST/JSON | температура, влажность, осадки, снег, ветер | оценка влияния погоды |
| [NYC DOT Traffic Speeds](https://data.cityofnewyork.us/Transportation/Real-Time-Traffic-Speed-Data/i4gi-tjb9) | Socrata REST/JSON | скорость движения и время проезда | оценка дорожной ситуации |

Целевая переменная — **`rides_started`**, количество поездок, начавшихся на конкретной станции в течение часа.

## Стек технологий

| Компонент | Технология |
|---|---|
| Язык | Python 3.11+ |
| Хранилище | PostgreSQL 16 |
| Работа с данными | pandas, SQLAlchemy |
| Трансформации | dbt-postgres |
| Оркестрация | Apache Airflow 3.4 |
| Прогнозирование | CatBoost, NumPy |
| BI | Apache Superset 6 |
| Контейнеризация | Docker Compose |
| Тестирование | pytest, Ruff |
| CI | GitHub Actions |

## Слои данных

В PostgreSQL используются пять логических схем.

| Схема | Назначение |
|---|---|
| `raw` | исходные записи с минимальными преобразованиями |
| `silver` | очищенные и согласованные сущности |
| `gold` | аналитические витрины, прогнозы и представления мониторинга |
| `meta` | журнал загрузок, watermark, DQ, schema registry и lineage |
| `quarantine` | некорректные записи с причиной отклонения |

Основная аналитическая витрина — `gold.station_hourly_demand`. Её зерно: **одна строка на `(observed_hour, station_sk)`**.

## Контроль качества данных

Система реализует все семь категорий контроля:

1. полнота;
2. уникальность;
3. корректность;
4. типы данных;
5. допустимые диапазоны;
6. ссылочная целостность;
7. актуальность.

Результаты сохраняются в `meta.dq_results`. Некорректные записи не удаляются из RAW: они дополнительно помещаются в `quarantine.rejected_records`, что сохраняет возможность аудита.

Проверка:

```powershell
citibike-pipeline dq --dataset all --quarantine
citibike-pipeline schema-check
```

Подробнее: [docs/data_quality.md](docs/data_quality.md).

## Преобразование данных

`silver.dim_station` реализует SCD Type 2 и хранит историю изменений станции через:

- `valid_from`;
- `valid_to`;
- `is_current`;
- `record_hash`.

`silver.fact_trip` содержит только допустимые поездки.

dbt формирует промежуточные модели и итоговую почасовую витрину спроса:

```text
RAW
 ├─ Citi Bike trips
 ├─ Weather
 └─ Traffic
       ↓
STAGING
       ↓
SILVER
       ↓
GOLD: station_hourly_demand
```

Запуск:

```powershell
citibike-pipeline transform
```

Подробнее: [docs/transformation.md](docs/transformation.md).

## Прогнозирование

Перед обучением строится полная сетка `станция × час`, включая часы с нулевым спросом. Исторические признаки рассчитываются без утечки целевой переменной:

- `lag_1`;
- `lag_24`;
- `lag_168`;
- rolling mean 3/24/168 часов с предварительным `shift(1)`;
- календарные признаки;
- погодные признаки;
- показатели дорожной ситуации.

Используются две группы моделей:

- **Seasonal Naive**: спрос в тот же час предыдущей недели;
- **CatBoost**: глобальная модель для нескольких станций.

Для выбора признаков выполняется абляционный эксперимент:

```text
history
  ↓
+ calendar
  ↓
+ weather
  ↓
+ traffic
```

Итоговый набор выбирается по минимальному WAPE на validation-части.

### Итоговые результаты

| Модель | Выборка | MAE | RMSE | WAPE |
|---|---|---:|---:|---:|
| Seasonal Naive 168h | test | 5.505 | 8.610 | 69.92% |
| CatBoost | test | **2.751** | **4.309** | **34.94%** |

Лучший набор признаков на validation — **история + календарные + погодные + дорожные признаки** (`traffic`), WAPE = **28.15%**.

Эксперимент выполнялся для 250 наиболее активных станций: 87 500 строк train, 24 000 validation и 30 000 test.

Подробнее: [docs/modeling.md](docs/modeling.md) и [docs/results.md](docs/results.md).

## Оркестрация Airflow

Реализованы два DAG:

- `citibike_daily_pipeline` — ежедневная загрузка GBFS, погоды и дорожной ситуации, DQ, schema drift и обновление dbt-витрин;
- `citibike_monthly_trips` — загрузка следующего месячного архива поездок, DQ, SCD2, SILVER fact и dbt.

Запуск:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\airflow_start.ps1
```

Интерфейс:

```text
http://localhost:8080
```

Проверка:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\airflow_check.ps1
```

Подробнее: [docs/airflow.md](docs/airflow.md).

## Дашборды Apache Superset

Запуск:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_start.ps1
```

Интерфейс:

```text
http://localhost:8088
```

Создаются два дашборда:

**Citi Bike — Спрос и прогноз**
- фактический спрос и прогноз CatBoost;
- WAPE итоговой модели;
- наиболее востребованные станции;
- динамика спроса и дорожной ситуации;
- сравнение качества моделей.

**Citi Bike — Мониторинг платформы данных**
- успешные и неуспешные загрузки;
- объёмы загруженных данных;
- длительность загрузок;
- результаты DQ;
- журнал последних запусков.

Проверка:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_check.ps1
```

Подробнее: [docs/superset.md](docs/superset.md).

## Быстрый запуск на Windows

### 1. Подготовка окружения

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,transform,ml]"
Copy-Item .env.example .env
```

Если порт PostgreSQL `5432` на компьютере занят, укажите в `.env`, например:

```text
POSTGRES_PORT=5433
DATABASE_URL=postgresql+psycopg://citibike:citibike@127.0.0.1:5433/citibike
```

### 2. PostgreSQL

```powershell
docker compose up -d postgres
citibike-pipeline db-health
```

### 3. Загрузка данных

Пример исторического периода:

```powershell
citibike-pipeline ingest --source citibike_trips --start-month 2026-09 --end-month 2026-09
citibike-pipeline ingest --source weather --start-date 2026-09-01 --end-date 2026-09-30
citibike-pipeline ingest --source traffic --traffic-start-date 2026-09-01 --traffic-end-date 2026-09-30
citibike-pipeline ingest --source citibike_gbfs
```

### 4. DQ и преобразования

```powershell
citibike-pipeline dq --dataset all --quarantine
citibike-pipeline schema-check
citibike-pipeline transform
```

### 5. Модель

Быстрая проверка:

```powershell
citibike-pipeline train --smoke
```

Полный эксперимент:

```powershell
citibike-pipeline train
citibike-pipeline model-metrics
```

### 6. Airflow и Superset

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\airflow_start.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\superset_start.ps1
```

Полная последовательность запуска и диагностики приведена в [docs/runbook.md](docs/runbook.md).

## Финальная проверка проекта

При запущенных контейнерах:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\final_check.ps1
```

Скрипт проверяет:

- Python и зависимости;
- Ruff;
- pytest;
- доступность PostgreSQL;
- dbt tests;
- наличие витрин и прогнозов;
- сохранённые метрики моделей;
- Airflow;
- Superset.

## Структура репозитория

```text
.
├── .github/workflows/        # CI
├── airflow/dags/             # DAG Airflow
├── config/                   # конфигурация проекта
├── data/                     # локальные RAW/quarantine данные, не коммитятся
├── dbt/                      # dbt project
├── docker/                   # Dockerfile для Airflow и Superset
├── docs/                     # техническая документация
├── scripts/                  # запуск и проверки сервисов
├── sql/init/                 # инициализация PostgreSQL
├── src/citibike_pipeline/
│   ├── database/
│   ├── ingestion/
│   ├── ml/
│   ├── quality/
│   └── transform/
├── superset/                 # bootstrap дашбордов
├── tests/                    # автоматические тесты
├── docker-compose.yml
├── docker-compose.airflow.yml
├── docker-compose.superset.yml
├── pyproject.toml
└── README.md
```

## Документация

- [Архитектура](docs/architecture.md)
- [Загрузка данных](docs/ingestion.md)
- [Архитектура БД](docs/database.md)
- [Контроль качества](docs/data_quality.md)
- [RAW → SILVER → GOLD](docs/transformation.md)
- [Оркестрация Airflow](docs/airflow.md)
- [Прогнозирование](docs/modeling.md)
- [Результаты эксперимента](docs/results.md)
- [Data lineage](docs/lineage.md)
- [Apache Superset](docs/superset.md)
- [Инструкция запуска и диагностики](docs/runbook.md)
