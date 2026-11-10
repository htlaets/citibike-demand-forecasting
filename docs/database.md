# Database architecture

The PostgreSQL database is divided into five explicit layers.

- `raw` — source records with minimal transformation.
- `silver` — cleaned and conformed entities.
- `gold` — analytical marts, forecasts and monitoring views.
- `meta` — watermarks, load logs, data-quality results, schema registry and lineage.
- `quarantine` — rejected records preserved with rejection reasons.

## Idempotency keys

- Citi Bike trips: `ride_id`.
- Weather: `observed_at`.
- NYC DOT traffic: `(link_id, data_as_of)`.
- GBFS station snapshots: `(station_id, observed_at)`.

## SCD Type 2

`silver.dim_station` stores station history using `valid_from`, `valid_to`,
`is_current` and a content `record_hash`.

## Operational monitoring

`gold.pipeline_monitoring` reads from `meta.etl_load_log`.

`gold.dq_monitoring` reads from `meta.dq_results`.

Both are intended to become datasets in the operational Apache Superset dashboard.
