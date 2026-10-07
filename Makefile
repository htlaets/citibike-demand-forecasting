.PHONY: install lint test ingest

install:
	python -m pip install -e ".[dev]"

lint:
	python -m ruff check src tests

test:
	python -m pytest

ingest:
	python -m citibike_pipeline.cli ingest --source all
