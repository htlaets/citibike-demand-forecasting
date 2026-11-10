# Data lineage

## Основной поток

| Этап | Объект-источник | Объект-результат | Преобразование |
|---|---|---|---|
| 1 | Citi Bike Trip Histories | `raw.citibike_trips` | ZIP/CSV ingestion, ключ `ride_id` |
| 1 | Citi Bike GBFS | `raw.gbfs_station_information` | REST/JSON snapshot |
| 1 | Citi Bike GBFS | `raw.gbfs_station_status` | REST/JSON snapshot |
| 1 | Open-Meteo | `raw.weather_hourly` | почасовой REST/JSON ingestion |
| 1 | NYC DOT Traffic | `raw.traffic_speed` | Socrata ingestion |
| 2 | RAW | `meta.dq_results` | проверки качества |
| 2 | RAW | `quarantine.rejected_records` | копирование нарушающих правил записей |
| 3 | RAW Citi Bike/GBFS | `silver.dim_station` | согласование + SCD Type 2 |
| 3 | `raw.citibike_trips` | `silver.fact_trip` | фильтрация DQ + разрешение станций |
| 3 | `raw.weather_hourly` | `silver.weather_hourly` | dbt normalization |
| 3 | `raw.traffic_speed` | `silver.traffic_hourly` | почасовая агрегация |
| 4 | SILVER | `gold.station_hourly_demand` | агрегация `station × hour` + enrichment |
| 5 | `gold.station_hourly_demand` | ML feature frame | lag/rolling/calendar/weather/traffic |
| 5 | feature frame | `gold.model_metrics` | оценка Seasonal Naive/CatBoost |
| 5 | feature frame | `gold.forecast_results` | test predictions |
| 6 | GOLD | Superset «Спрос и прогноз» | serving views |
| 6 | META/GOLD | Superset «Мониторинг платформы данных» | operational views |

## Метаданные

Отдельный lineage-поток фиксирует состояние платформы:

```text
external sources
      ↓
meta.etl_load_log
      ↓
gold.pipeline_monitoring
      ↓
Superset Operations

RAW
 ↓
meta.dq_results
 ↓
gold.dq_monitoring
 ↓
Superset Operations
```

## Хранение lineage

Ключевые связи дополнительно регистрируются в `meta.data_lineage`. Таблица содержит:

- upstream object;
- upstream type;
- downstream object;
- downstream type;
- описание преобразования;
- компонент-владелец.

Это позволяет проследить путь от внешнего источника до конечного дашборда.
