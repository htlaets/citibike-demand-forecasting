# Мониторинг спроса на Citi Bike

Pet project прогнозно-аналитической системы по теме **«Мониторинг динамики спроса на прокат велосипедов в зависимости от погодных условий и дорожной ситуации в Нью-Йорке»**.

Система собирает оперативные данные о доступности велосипедов на станциях Citi Bike, погоде и скорости дорожного движения. Этот репозиторий содержит первый рабочий контур: ingestion, сохранение RAW-снимков и автоматические проверки качества данных.

## Источники данных

| Источник | Что загружается | Назначение |
|---|---|---|
| [Citi Bike GBFS](https://citibikenyc.com/system-data) | станции, число доступных велосипедов и доков | оценка текущего спроса и доступности |
| [Open-Meteo](https://open-meteo.com/en/docs) | температура, осадки, ветер, влажность и погодный код | анализ влияния погодных условий |
| [NYC DOT Traffic Speeds](https://data.cityofnewyork.us/Transportation/Real-Time-Traffic-Speed-Data/i4gi-tjb9) | скорость и время проезда по дорожным сегментам | анализ дорожной ситуации |

```text
Citi Bike GBFS ─────┐
Open-Meteo ─────────┼──> ingestion CLI ──> data/raw ──> data/quality
NYC DOT Traffic ────┘
```

## Что уже реализовано

- конфигурация источников в YAML;
- HTTP-клиент с таймаутами, повторными попытками и понятными ошибками;
- загрузчики Citi Bike, Open-Meteo и NYC DOT Traffic;
- сохранение атомарных JSON-снимков с UTC-временем загрузки;
- проверки наличия строк и полей, NULL, дубликатов, типов, диапазонов и временного диапазона;
- CLI для загрузки всех или одного источника и повторной проверки сохранённого файла;
- PostgreSQL DDL для метаданных запусков и результатов проверок;
- unit-тесты и GitHub Actions CI.

## Быстрый старт

Требуется Python 3.10 или новее.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Токен NYC Open Data необязателен для небольших запросов, но повышает лимиты API. Если он есть, экспортируйте значение из `.env`:

```bash
set -a; source .env; set +a
```

Загрузить все три источника и сразу выполнить проверки качества:

```bash
citibike-pipeline ingest --source all
```

Загрузить один источник:

```bash
citibike-pipeline ingest --source weather
```

Повторно проверить сохранённый RAW-файл:

```bash
citibike-pipeline quality data/raw/weather/<имя-файла>.json --source weather
```

Путь к конфигурации можно задать флагом `--config` или переменной `PIPELINE_CONFIG`. Каталог назначения переопределяется через `--output-dir`.

## Структура

```text
.
├── config/config.yaml
├── data/
│   ├── raw/                 # JSON-снимки источников (не коммитятся)
│   └── quality/             # JSON-отчёты проверок (не коммитятся)
├── sql/init_metadata.sql
├── src/citibike_pipeline/
│   ├── ingestion/           # загрузчики трёх API
│   ├── quality/             # правила и отчёты качества
│   ├── cli.py
│   ├── config.py
│   ├── http.py
│   └── storage.py
└── tests/test_quality.py
```

## Проверки для разработки

```bash
make lint
make test
```

Команда `make ingest` запускает полный ingestion. CI выполняет линтер и тесты на Python 3.10 и 3.12; сетевые API в unit-тестах не вызываются.

## Следующие этапы

После стабилизации ingestion: загрузка Bronze/Silver/Gold в PostgreSQL, исторические поездки Citi Bike, оркестрация, витрины по станциям и часам, модель прогноза спроса и дашборд мониторинга.
