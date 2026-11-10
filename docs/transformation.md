# Преобразование RAW → SILVER → GOLD

## Назначение

Трансформационный слой:

- сохраняет исходные данные в RAW;
- исключает записи, которые нельзя безопасно использовать в аналитике;
- согласует справочник станций;
- формирует факты поездок;
- строит почасовую витрину спроса.

## SCD Type 2

`silver.dim_station` хранит версии станции.

Изменение атрибутов определяется по `record_hash`. Если состояние изменилось:

1. текущая версия закрывается;
2. устанавливается `valid_to`;
3. `is_current` становится `false`;
4. создаётся новая версия.

При повторном запуске на неизменившихся данных новые версии не появляются.

## Факт поездок

`silver.fact_trip` содержит валидные поездки. Записи с отсутствующим стартом/временем, недопустимой длительностью или карантинными нарушениями исключаются.

Идемпотентность сохраняется по `ride_id`.

## dbt

dbt формирует:

- `staging.stg_citibike_trips`;
- `staging.stg_weather_hourly`;
- `staging.stg_traffic_speed`;
- `silver.weather_hourly`;
- `silver.traffic_hourly`;
- `gold.station_hourly_demand`.

Зерно GOLD-витрины:

```text
(observed_hour, station_sk)
```

Время календарных признаков рассчитывается в `America/New_York`, а timestamp в хранилище остаются timezone-aware.

## Запуск

```powershell
pip install -e ".[dev,transform,ml]"
citibike-pipeline dbt --command debug
citibike-pipeline transform
```

Повторный запуск безопасен: факты и incremental dbt-модели используют стабильные уникальные ключи.
