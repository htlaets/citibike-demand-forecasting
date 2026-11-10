# Архитектура базы данных

PostgreSQL разделён на пять логических схем.

- `raw` — исходные записи с минимальными преобразованиями;
- `silver` — очищенные и согласованные сущности;
- `gold` — аналитические витрины, прогнозы и представления мониторинга;
- `meta` — watermark, журналы загрузок, DQ, schema registry и lineage;
- `quarantine` — отклонённые записи с сохранением причины.

## Ключи идемпотентности

- поездки Citi Bike — `ride_id`;
- погода — `observed_at`;
- NYC DOT Traffic — `(link_id, data_as_of)`;
- GBFS — `(station_id, observed_at)`.

Повторный запуск загрузчика не создаёт дубликаты бизнес-записей. При этом новая попытка выполнения всё равно фиксируется в журнале загрузок.

## Основные RAW-таблицы

- `raw.citibike_trips`;
- `raw.weather_hourly`;
- `raw.traffic_speed`;
- `raw.gbfs_station_information`;
- `raw.gbfs_station_status`.

## SILVER

`silver.dim_station` хранит историю станции по SCD Type 2.

Основные поля:

- `station_sk` — суррогатный ключ;
- `station_id` — естественный ключ;
- `valid_from`;
- `valid_to`;
- `is_current`;
- `record_hash`.

`silver.fact_trip` содержит только поездки, прошедшие правила отбора.

## GOLD

Основные объекты:

- `gold.station_hourly_demand` — почасовая витрина спроса;
- `gold.forecast_results` — прогнозы и фактические значения;
- `gold.model_metrics` — MAE/RMSE/WAPE;
- `gold.pipeline_monitoring` — представление журнала загрузок;
- `gold.dq_monitoring` — представление результатов DQ;
- `gold.superset_*` — serving views для BI.

## META

- `meta.data_sources`;
- `meta.etl_watermark`;
- `meta.etl_load_log`;
- `meta.dq_results`;
- `meta.schema_registry`;
- `meta.schema_changes`;
- `meta.data_lineage`.

## Quarantine

`quarantine.rejected_records` хранит:

- источник;
- набор данных;
- natural key;
- причину отклонения;
- категории нарушенных проверок;
- JSON-представление записи;
- время помещения в карантин.

RAW-запись при этом сохраняется.
