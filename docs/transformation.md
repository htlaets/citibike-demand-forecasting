# Transformation layer: RAW -> SILVER -> GOLD

## Purpose

The transformation layer keeps source data unchanged in RAW, excludes records
that cannot safely participate in analytics, resolves stations through an SCD
Type 2 dimension, and produces the station-hour demand mart used by forecasting
and Apache Superset.

## SCD Type 2

`silver.dim_station` uses:

- `station_sk` — surrogate key;
- `station_id` — natural source key;
- `valid_from` / `valid_to`;
- `is_current`;
- `record_hash`.

The transformation selects the latest known station state. A changed hash closes
the previous current version and inserts a new one. Re-running against the same
source state inserts zero new versions.

## Fact

`silver.fact_trip` contains valid trips only. Rows with missing station/time,
invalid duration, or quarantined defects are excluded. `ride_id` remains the
idempotency key.

## dbt

dbt creates:

- `staging.stg_citibike_trips`;
- `staging.stg_weather_hourly`;
- `staging.stg_traffic_speed`;
- `silver.weather_hourly`;
- `silver.traffic_hourly`;
- `gold.station_hourly_demand`.

The GOLD grain is exactly one row per `(observed_hour, station_sk)`.

Calendar features use `America/New_York`, while warehouse timestamps remain
timezone-aware.

## Run

Install transformation dependencies:

```bash
pip install -e ".[dev,transform]"
```

Validate dbt:

```bash
citibike-pipeline dbt --command debug
```

Build the complete transformation layer:

```bash
citibike-pipeline transform
```

Re-running the command is expected and safe. Facts and dbt incremental models
use stable unique keys, while SCD2 creates a version only if station attributes
change.
