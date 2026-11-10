.PHONY: install lint test check db-up db-down db-health dbt-debug dbt-test ml-smoke watermarks

install:
	python -m pip install -e ".[dev,transform,ml]"

lint:
	python -m ruff check src tests

test:
	python -m pytest

check: lint test

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-health:
	citibike-pipeline db-health

dbt-debug:
	citibike-pipeline dbt --command debug

dbt-test:
	citibike-pipeline dbt --command test

ml-smoke:
	citibike-pipeline train --smoke

watermarks:
	citibike-pipeline watermarks
