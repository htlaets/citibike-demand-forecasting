# Загрузка данных

В проекте реализованы четыре независимых контура ingestion.

## Citi Bike Trip Histories

Источник публикует месячные ZIP/CSV-архивы исторических поездок.

Ключ идемпотентности: `ride_id`.

Watermark: последний обработанный месяц.

Пример:

```powershell
citibike-pipeline ingest --source citibike_trips --start-month 2026-09 --end-month 2026-09
```

## Citi Bike GBFS

Используются оперативные REST/JSON feeds:

- station information;
- station status.

Ключ: `(station_id, observed_at)`.

```powershell
citibike-pipeline ingest --source citibike_gbfs
```

## Open-Meteo

Загружаются почасовые:

- температура;
- относительная влажность;
- осадки;
- дождь;
- снег;
- погодный код;
- скорость ветра.

Ключ: `observed_at`.

```powershell
citibike-pipeline ingest --source weather --start-date 2026-09-01 --end-date 2026-09-30
```

## NYC DOT Traffic Speeds

Источник доступен через Socrata REST API.

Используются:

- link ID;
- время наблюдения;
- скорость;
- время проезда;
- borough;
- название дорожного сегмента.

Ключ: `(link_id, data_as_of)`.

Историческая загрузка:

```powershell
citibike-pipeline ingest --source traffic --traffic-start-date 2026-09-01 --traffic-end-date 2026-09-30
```

## Надёжность

HTTP-клиент использует:

- connect/read timeout;
- retry;
- backoff;
- явную обработку ошибок источника.

Watermark изменяется только после успешной транзакции.

Каждая попытка фиксируется в `meta.etl_load_log` с количеством полученных, вставленных, обновлённых и отклонённых строк.

## Проверка идемпотентности

Повторная загрузка того же периода должна дать `inserted=0` для уже существующих бизнес-записей. Это ожидаемое поведение.
