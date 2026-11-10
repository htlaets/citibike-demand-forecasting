.PHONY: install lint test db-up db-down db-health ingest-smoke watermarks

install:
	python -m pip install -e ".[dev]"

lint:
	python -m ruff check src tests

test:
	python -m pytest

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-health:
	python -m citibike_pipeline.database.healthcheck

ingest-smoke:
	citibike-pipeline ingest --source citibike_gbfs
	citibike-pipeline ingest --source weather --start-date 2026-09-01 --end-date 2026-09-02
	citibike-pipeline ingest --source traffic --traffic-since-hours 1

watermarks:
	citibike-pipeline watermarks
