BEGIN;

CREATE SCHEMA IF NOT EXISTS metadata;

CREATE TABLE IF NOT EXISTS metadata.ingestion_runs (
    run_id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name         TEXT NOT NULL CHECK (source_name IN ('citibike', 'weather', 'traffic')),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at         TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'success', 'failed')),
    row_count           INTEGER CHECK (row_count >= 0),
    raw_path            TEXT,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source_started
    ON metadata.ingestion_runs (source_name, started_at DESC);

CREATE TABLE IF NOT EXISTS metadata.data_quality_results (
    result_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              BIGINT NOT NULL REFERENCES metadata.ingestion_runs(run_id) ON DELETE CASCADE,
    check_name          TEXT NOT NULL,
    passed              BOOLEAN NOT NULL,
    severity            TEXT NOT NULL CHECK (severity IN ('warning', 'error')),
    observed_value      JSONB,
    message             TEXT,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quality_results_run
    ON metadata.data_quality_results (run_id, passed);

COMMIT;
