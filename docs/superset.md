# Apache Superset

Проект использует Apache Superset 6 в Docker.

Метаданные Superset хранятся в отдельном `superset-db`, а аналитические данные читаются из `citibike-postgres`.

## Запуск

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_start.ps1
```

UI:

```text
http://localhost:8088
```

Локальные учётные данные по умолчанию:

```text
admin / admin
```

Их можно переопределить через `.env`.

Bootstrap идемпотентен: повторный запуск обновляет подключение, serving views, datasets, charts и dashboards, не создавая дубли.

## Дашборд «Citi Bike — Спрос и прогноз»

Содержит:

- общее количество начатых поездок;
- WAPE CatBoost на тесте;
- фактический спрос и прогноз;
- топ станций;
- динамику спроса и дорожной ситуации;
- таблицу MAE/RMSE/WAPE.

## Дашборд «Citi Bike — Мониторинг платформы данных»

Содержит:

- успешные загрузки;
- неуспешные загрузки;
- загруженные строки по источникам;
- длительность загрузки;
- нарушения DQ по типам;
- последние запуски;
- подробные результаты контроля качества.

## Serving views

Для ускорения BI используются компактные представления:

- `gold.superset_hourly_demand`;
- `gold.superset_top_stations`;
- `gold.superset_forecast_comparison`;
- `gold.superset_model_metrics`;
- `gold.superset_model_kpi`;
- `gold.superset_pipeline_monitoring`;
- `gold.superset_pipeline_kpi`;
- `gold.superset_dq_monitoring`;
- `gold.superset_dq_summary`.

## Проверка

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_check.ps1
```

Ожидается:

```text
Superset 6.0.0
Health endpoint: OK
[OK] Citi Bike — Спрос и прогноз: ... charts=6 published=True
[OK] Citi Bike — Мониторинг платформы данных: ... charts=7 published=True
[OK] project charts: 13
```

## Остановка

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\superset_stop.ps1
```

Named volumes сохраняют метаданные между перезапусками.
