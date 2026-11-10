BEGIN;

-- ============================================================
-- 1. Logical storage layers
-- ============================================================
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS quarantine;

-- ============================================================
-- 2. Metadata and pipeline-control layer
-- ============================================================
CREATE TABLE IF NOT EXISTS meta.data_sources (
    source_name         TEXT PRIMARY KEY,
    source_type         TEXT NOT NULL,
    source_url          TEXT,
    description         TEXT NOT NULL,
    incremental_key     TEXT,
    freshness_sla_hours INTEGER CHECK (freshness_sla_hours IS NULL OR freshness_sla_hours > 0),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta.etl_watermark (
    source_name       TEXT PRIMARY KEY REFERENCES meta.data_sources(source_name),
    watermark_value   TEXT,
    watermark_ts      TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meta.etl_load_log (
    load_id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name        TEXT NOT NULL REFERENCES meta.data_sources(source_name),
    pipeline_name      TEXT NOT NULL DEFAULT 'main_ingestion',
    run_key            TEXT,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at        TIMESTAMPTZ,
    status             TEXT NOT NULL DEFAULT 'RUNNING'
                       CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'SKIPPED', 'PARTIAL')),
    watermark_from     TEXT,
    watermark_to       TEXT,
    rows_received      BIGINT NOT NULL DEFAULT 0 CHECK (rows_received >= 0),
    rows_inserted      BIGINT NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0),
    rows_updated       BIGINT NOT NULL DEFAULT 0 CHECK (rows_updated >= 0),
    rows_rejected      BIGINT NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
    retry_count        INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    raw_location       TEXT,
    error_type         TEXT,
    error_message      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_etl_load_log_source_started
    ON meta.etl_load_log (source_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_etl_load_log_status
    ON meta.etl_load_log (status, started_at DESC);

CREATE TABLE IF NOT EXISTS meta.dq_results (
    dq_result_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    load_id            BIGINT REFERENCES meta.etl_load_log(load_id) ON DELETE CASCADE,
    source_name        TEXT NOT NULL REFERENCES meta.data_sources(source_name),
    dataset_name       TEXT NOT NULL,
    check_type         TEXT NOT NULL CHECK (
        check_type IN (
            'COMPLETENESS',
            'UNIQUENESS',
            'VALIDITY',
            'TYPE',
            'RANGE',
            'REFERENTIAL_INTEGRITY',
            'FRESHNESS'
        )
    ),
    check_name         TEXT NOT NULL,
    column_name        TEXT,
    status             TEXT NOT NULL CHECK (status IN ('PASS', 'WARN', 'FAIL')),
    rows_checked       BIGINT CHECK (rows_checked IS NULL OR rows_checked >= 0),
    failed_rows        BIGINT CHECK (failed_rows IS NULL OR failed_rows >= 0),
    observed_value     JSONB,
    expected_value     JSONB,
    details            TEXT,
    checked_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dq_results_dataset_checked
    ON meta.dq_results (dataset_name, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_dq_results_status
    ON meta.dq_results (status, checked_at DESC);

CREATE TABLE IF NOT EXISTS meta.schema_registry (
    dataset_name       TEXT NOT NULL,
    schema_version     INTEGER NOT NULL CHECK (schema_version > 0),
    schema_definition  JSONB NOT NULL,
    schema_hash        TEXT NOT NULL,
    effective_from     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    effective_to       TIMESTAMPTZ,
    is_current         BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (dataset_name, schema_version),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_schema_registry_current
    ON meta.schema_registry (dataset_name)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS meta.schema_changes (
    change_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_name       TEXT NOT NULL,
    detected_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    previous_version   INTEGER,
    new_version        INTEGER,
    change_type        TEXT NOT NULL,
    changed_columns    JSONB,
    is_breaking        BOOLEAN NOT NULL DEFAULT FALSE,
    action_taken       TEXT
);

CREATE TABLE IF NOT EXISTS meta.data_lineage (
    lineage_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    upstream_object    TEXT NOT NULL,
    upstream_type      TEXT NOT NULL,
    downstream_object  TEXT NOT NULL,
    downstream_type    TEXT NOT NULL,
    transformation     TEXT,
    owner_component    TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (upstream_object, downstream_object)
);

-- ============================================================
-- 3. RAW layer: minimally transformed source records
-- ============================================================
CREATE TABLE IF NOT EXISTS raw.citibike_trips (
    ride_id             TEXT PRIMARY KEY,
    rideable_type       TEXT,
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    start_station_name  TEXT,
    start_station_id    TEXT,
    end_station_name    TEXT,
    end_station_id      TEXT,
    start_lat           DOUBLE PRECISION,
    start_lng           DOUBLE PRECISION,
    end_lat             DOUBLE PRECISION,
    end_lng             DOUBLE PRECISION,
    member_casual       TEXT,
    source_file         TEXT NOT NULL,
    source_month        DATE NOT NULL,
    load_id             BIGINT REFERENCES meta.etl_load_log(load_id),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload         JSONB
);

CREATE INDEX IF NOT EXISTS idx_raw_trips_started
    ON raw.citibike_trips (started_at);

CREATE INDEX IF NOT EXISTS idx_raw_trips_start_station
    ON raw.citibike_trips (start_station_id, started_at);

CREATE TABLE IF NOT EXISTS raw.weather_hourly (
    observed_at         TIMESTAMPTZ PRIMARY KEY,
    temperature_2m      DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    precipitation       DOUBLE PRECISION,
    rain                DOUBLE PRECISION,
    snowfall            DOUBLE PRECISION,
    weather_code        INTEGER,
    wind_speed_10m      DOUBLE PRECISION,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    load_id             BIGINT REFERENCES meta.etl_load_log(load_id),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload         JSONB
);

CREATE TABLE IF NOT EXISTS raw.traffic_speed (
    link_id             TEXT NOT NULL,
    data_as_of          TIMESTAMPTZ NOT NULL,
    speed               DOUBLE PRECISION,
    travel_time         DOUBLE PRECISION,
    borough             TEXT,
    link_name           TEXT,
    encoded_poly_line   TEXT,
    load_id             BIGINT REFERENCES meta.etl_load_log(load_id),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload         JSONB,
    PRIMARY KEY (link_id, data_as_of)
);

CREATE INDEX IF NOT EXISTS idx_raw_traffic_time
    ON raw.traffic_speed (data_as_of);

CREATE TABLE IF NOT EXISTS raw.gbfs_station_information (
    station_id          TEXT NOT NULL,
    observed_at         TIMESTAMPTZ NOT NULL,
    station_name        TEXT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    capacity            INTEGER,
    load_id             BIGINT REFERENCES meta.etl_load_log(load_id),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload         JSONB,
    PRIMARY KEY (station_id, observed_at)
);

CREATE TABLE IF NOT EXISTS raw.gbfs_station_status (
    station_id          TEXT NOT NULL,
    observed_at         TIMESTAMPTZ NOT NULL,
    num_bikes_available INTEGER,
    num_docks_available INTEGER,
    is_installed        BOOLEAN,
    is_renting          BOOLEAN,
    is_returning        BOOLEAN,
    load_id             BIGINT REFERENCES meta.etl_load_log(load_id),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload         JSONB,
    PRIMARY KEY (station_id, observed_at)
);

-- ============================================================
-- 4. Quarantine: invalid records are preserved, not silently lost
-- ============================================================
CREATE TABLE IF NOT EXISTS quarantine.rejected_records (
    rejected_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name         TEXT NOT NULL,
    dataset_name        TEXT NOT NULL,
    load_id             BIGINT REFERENCES meta.etl_load_log(load_id),
    natural_key         TEXT,
    rejection_reason    TEXT NOT NULL,
    failed_checks       JSONB,
    record_payload      JSONB NOT NULL,
    rejected_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rejected_source_time
    ON quarantine.rejected_records (source_name, rejected_at DESC);

-- ============================================================
-- 5. SILVER layer: cleaned/conformed model
-- ============================================================
CREATE TABLE IF NOT EXISTS silver.dim_station (
    station_sk          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    station_id          TEXT NOT NULL,
    station_name        TEXT NOT NULL,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    capacity            INTEGER,
    valid_from          TIMESTAMPTZ NOT NULL,
    valid_to            TIMESTAMPTZ,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    record_hash         TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_station_current
    ON silver.dim_station (station_id)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_dim_station_history
    ON silver.dim_station (station_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS silver.fact_trip (
    ride_id             TEXT PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ NOT NULL,
    start_station_sk    BIGINT REFERENCES silver.dim_station(station_sk),
    end_station_sk      BIGINT REFERENCES silver.dim_station(station_sk),
    rideable_type       TEXT,
    member_casual       TEXT,
    duration_seconds    INTEGER CHECK (duration_seconds >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fact_trip_start
    ON silver.fact_trip (started_at, start_station_sk);

CREATE TABLE IF NOT EXISTS silver.weather_hourly (
    observed_at          TIMESTAMPTZ PRIMARY KEY,
    temperature_2m       DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    precipitation        DOUBLE PRECISION,
    rain                 DOUBLE PRECISION,
    snowfall             DOUBLE PRECISION,
    weather_code         INTEGER,
    wind_speed_10m       DOUBLE PRECISION,
    processed_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver.traffic_hourly (
    observed_hour       TIMESTAMPTZ NOT NULL,
    borough             TEXT NOT NULL DEFAULT 'UNKNOWN',
    avg_speed           DOUBLE PRECISION,
    avg_travel_time     DOUBLE PRECISION,
    links_observed      INTEGER NOT NULL DEFAULT 0,
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (observed_hour, borough)
);

-- ============================================================
-- 6. GOLD layer: analytics and forecasting marts
-- ============================================================
CREATE TABLE IF NOT EXISTS gold.station_hourly_demand (
    observed_hour        TIMESTAMPTZ NOT NULL,
    station_sk           BIGINT NOT NULL REFERENCES silver.dim_station(station_sk),
    station_id           TEXT NOT NULL,
    station_name         TEXT NOT NULL,
    rides_started        INTEGER NOT NULL DEFAULT 0 CHECK (rides_started >= 0),
    rides_ended          INTEGER NOT NULL DEFAULT 0 CHECK (rides_ended >= 0),
    temperature_2m       DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    precipitation        DOUBLE PRECISION,
    snowfall             DOUBLE PRECISION,
    wind_speed_10m       DOUBLE PRECISION,
    avg_traffic_speed    DOUBLE PRECISION,
    avg_travel_time      DOUBLE PRECISION,
    hour_of_day          SMALLINT CHECK (hour_of_day BETWEEN 0 AND 23),
    day_of_week          SMALLINT CHECK (day_of_week BETWEEN 0 AND 6),
    month_num            SMALLINT CHECK (month_num BETWEEN 1 AND 12),
    is_weekend           BOOLEAN,
    refreshed_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (observed_hour, station_sk)
);

CREATE INDEX IF NOT EXISTS idx_gold_demand_station_hour
    ON gold.station_hourly_demand (station_id, observed_hour DESC);

CREATE TABLE IF NOT EXISTS gold.forecast_results (
    forecast_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name           TEXT NOT NULL,
    model_version        TEXT NOT NULL,
    trained_at           TIMESTAMPTZ NOT NULL,
    forecast_generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    forecast_for         TIMESTAMPTZ NOT NULL,
    station_sk           BIGINT NOT NULL REFERENCES silver.dim_station(station_sk),
    prediction           DOUBLE PRECISION NOT NULL CHECK (prediction >= 0),
    actual               DOUBLE PRECISION,
    horizon_hours        INTEGER NOT NULL CHECK (horizon_hours > 0),
    feature_set_version  TEXT NOT NULL,
    UNIQUE (model_name, model_version, forecast_for, station_sk, horizon_hours)
);

CREATE INDEX IF NOT EXISTS idx_forecast_results_station_time
    ON gold.forecast_results (station_sk, forecast_for DESC);

CREATE TABLE IF NOT EXISTS gold.model_metrics (
    evaluation_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name           TEXT NOT NULL,
    model_version        TEXT NOT NULL,
    split_name           TEXT NOT NULL,
    evaluation_from      TIMESTAMPTZ NOT NULL,
    evaluation_to        TIMESTAMPTZ NOT NULL,
    mae                  DOUBLE PRECISION,
    rmse                 DOUBLE PRECISION,
    wape                 DOUBLE PRECISION,
    rows_evaluated       BIGINT NOT NULL CHECK (rows_evaluated >= 0),
    evaluated_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (model_name, model_version, split_name, evaluation_from, evaluation_to)
);

-- ============================================================
-- 7. Views used by the operational dashboard
-- ============================================================
CREATE OR REPLACE VIEW gold.pipeline_monitoring AS
SELECT
    l.load_id,
    l.source_name,
    l.pipeline_name,
    l.started_at,
    l.finished_at,
    l.status,
    l.rows_received,
    l.rows_inserted,
    l.rows_updated,
    l.rows_rejected,
    l.retry_count,
    l.error_type,
    l.error_message,
    CASE
        WHEN l.finished_at IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (l.finished_at - l.started_at))
    END AS duration_seconds
FROM meta.etl_load_log AS l;

CREATE OR REPLACE VIEW gold.dq_monitoring AS
SELECT
    source_name,
    dataset_name,
    check_type,
    check_name,
    status,
    rows_checked,
    failed_rows,
    checked_at,
    details
FROM meta.dq_results;

-- ============================================================
-- 8. Seed source metadata
-- ============================================================
INSERT INTO meta.data_sources (
    source_name, source_type, source_url, description, incremental_key, freshness_sla_hours
)
VALUES
    (
        'citibike_trips',
        'ZIP/CSV',
        'https://s3.amazonaws.com/tripdata',
        'Historical Citi Bike trip histories used as the main demand source.',
        'source_month',
        744
    ),
    (
        'citibike_gbfs',
        'REST/JSON',
        'https://gbfs.citibikenyc.com/gbfs/gbfs.json',
        'Citi Bike GBFS station information and real-time station status.',
        'observed_at',
        1
    ),
    (
        'weather',
        'REST/JSON',
        'https://open-meteo.com/',
        'Open-Meteo historical and forecast hourly weather for New York City.',
        'observed_at',
        48
    ),
    (
        'traffic',
        'Socrata REST/JSON',
        'https://data.cityofnewyork.us/resource/i4gi-tjb9.json',
        'NYC DOT traffic speed and travel-time observations.',
        'data_as_of',
        48
    )
ON CONFLICT (source_name) DO UPDATE SET
    source_type = EXCLUDED.source_type,
    source_url = EXCLUDED.source_url,
    description = EXCLUDED.description,
    incremental_key = EXCLUDED.incremental_key,
    freshness_sla_hours = EXCLUDED.freshness_sla_hours,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO meta.etl_watermark (source_name)
SELECT source_name
FROM meta.data_sources
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================
-- 9. Initial lineage graph
-- ============================================================
INSERT INTO meta.data_lineage (
    upstream_object, upstream_type, downstream_object, downstream_type,
    transformation, owner_component
)
VALUES
    ('Citi Bike Trip History', 'SOURCE', 'raw.citibike_trips', 'RAW_TABLE',
     'ZIP/CSV ingestion with idempotent ride_id key', 'Python ingestion'),
    ('Open-Meteo', 'SOURCE', 'raw.weather_hourly', 'RAW_TABLE',
     'REST/JSON incremental hourly ingestion', 'Python ingestion'),
    ('NYC DOT Traffic Speeds', 'SOURCE', 'raw.traffic_speed', 'RAW_TABLE',
     'Socrata paginated incremental ingestion', 'Python ingestion'),
    ('raw.citibike_trips', 'RAW_TABLE', 'silver.fact_trip', 'SILVER_TABLE',
     'DQ, validation, station resolution, duration derivation', 'dbt/Python'),
    ('raw.weather_hourly', 'RAW_TABLE', 'silver.weather_hourly', 'SILVER_TABLE',
     'Type normalization and DQ', 'dbt'),
    ('raw.traffic_speed', 'RAW_TABLE', 'silver.traffic_hourly', 'SILVER_TABLE',
     'Hourly/borough aggregation', 'dbt'),
    ('silver.fact_trip', 'SILVER_TABLE', 'gold.station_hourly_demand', 'GOLD_MART',
     'Hourly demand aggregation and feature enrichment', 'dbt'),
    ('silver.weather_hourly', 'SILVER_TABLE', 'gold.station_hourly_demand', 'GOLD_MART',
     'Hourly weather enrichment', 'dbt'),
    ('silver.traffic_hourly', 'SILVER_TABLE', 'gold.station_hourly_demand', 'GOLD_MART',
     'Traffic enrichment', 'dbt'),
    ('gold.station_hourly_demand', 'GOLD_MART', 'gold.forecast_results', 'MODEL_OUTPUT',
     'Seasonal Naive and CatBoost forecasting', 'Python ML'),
    ('gold.forecast_results', 'MODEL_OUTPUT', 'Superset: Demand Dashboard', 'DASHBOARD',
     'Actual vs forecast and decision-support visualizations', 'Apache Superset'),
    ('meta.etl_load_log', 'METADATA_TABLE', 'Superset: Operations Dashboard', 'DASHBOARD',
     'Pipeline health and load monitoring', 'Apache Superset'),
    ('meta.dq_results', 'METADATA_TABLE', 'Superset: Operations Dashboard', 'DASHBOARD',
     'DQ status and failed-check monitoring', 'Apache Superset')
ON CONFLICT (upstream_object, downstream_object) DO NOTHING;

COMMIT;
