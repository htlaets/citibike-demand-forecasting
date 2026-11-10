# Архитектура системы

## Общая схема

Система построена как последовательный конвейер обработки данных от внешних источников до прогнозов и BI-панелей.

```mermaid
flowchart TB
    subgraph Sources[Внешние источники]
        A[Citi Bike Trip Histories]
        B[Citi Bike GBFS]
        C[Open-Meteo]
        D[NYC DOT Traffic Speeds]
    end

    subgraph Orchestration[Оркестрация]
        AF[Apache Airflow]
    end

    subgraph Processing[Обработка]
        ING[Python ingestion]
        DQ[Data Quality]
        SCHEMA[Schema drift]
        TRANS[Python + dbt]
        ML[Seasonal Naive + CatBoost]
    end

    subgraph PostgreSQL[PostgreSQL]
        RAW[(raw)]
        SILVER[(silver)]
        GOLD[(gold)]
        META[(meta)]
        Q[(quarantine)]
    end

    subgraph BI[Представление]
        SUP[Apache Superset]
    end

    A --> ING
    B --> ING
    C --> ING
    D --> ING

    AF -. управляет .-> ING
    AF -. управляет .-> DQ
    AF -. управляет .-> SCHEMA
    AF -. управляет .-> TRANS

    ING --> RAW
    ING --> META
    RAW --> DQ
    DQ --> Q
    DQ --> META
    RAW --> TRANS
    TRANS --> SILVER
    SILVER --> GOLD
    GOLD --> ML
    ML --> GOLD
    GOLD --> SUP
    META --> SUP
```

## Компоненты

### Python ingestion

Загрузчики отвечают за получение внешних данных, повторные запросы, обработку ошибок, дедупликацию и продвижение watermark. Каждый запуск регистрируется в `meta.etl_load_log`.

### PostgreSQL

PostgreSQL используется как единое хранилище бизнес-данных и метаданных проекта. Разделение по схемам позволяет явно отделить исходный слой, очищенные данные, аналитические витрины и служебную информацию.

### Data Quality

DQ выполняется до использования данных в аналитике. Проверки сохраняются в `meta.dq_results`, а некорректные записи дополнительно копируются в `quarantine.rejected_records`.

### dbt

dbt формирует воспроизводимые SQL-преобразования SILVER/GOLD и автоматически проверяет ограничения моделей.

### Apache Airflow

Airflow оркестрирует ежедневный и ежемесячный процессы. Метаданные Airflow хранятся в отдельном PostgreSQL-контейнере и не смешиваются с предметными данными.

### ML

Прогнозный модуль использует временное разделение и сравнивает Seasonal Naive с CatBoost. Результаты сохраняются в `gold.model_metrics` и `gold.forecast_results`.

### Apache Superset

Superset работает с компактными GOLD serving views. Его служебные метаданные также вынесены в отдельный PostgreSQL-контейнер.

## Принципы

- идемпотентность повторных загрузок;
- разделение бизнес-данных и служебных метаданных;
- сохранение исходных RAW-записей;
- воспроизводимые SQL-преобразования;
- временная валидация модели без shuffle;
- автоматизированное журналирование;
- наблюдаемость через Airflow, META-таблицы и Superset;
- контейнеризация инфраструктурных компонентов.
