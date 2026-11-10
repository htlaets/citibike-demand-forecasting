import ast
from pathlib import Path

import yaml


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_airflow_dags_are_valid_python() -> None:
    dag_dir = Path("airflow/dags")
    dag_files = sorted(dag_dir.glob("*.py"))
    assert {p.name for p in dag_files} == {
        "citibike_daily_pipeline.py",
        "citibike_monthly_trips.py",
    }
    for path in dag_files:
        ast.parse(path.read_text(encoding="utf-8"))


def test_expected_dag_ids_and_safety_options_exist() -> None:
    daily = _read("airflow/dags/citibike_daily_pipeline.py")
    monthly = _read("airflow/dags/citibike_monthly_trips.py")

    assert 'dag_id="citibike_daily_pipeline"' in daily
    assert 'dag_id="citibike_monthly_trips"' in monthly
    assert "catchup=False" in daily
    assert "catchup=False" in monthly
    assert "max_active_runs=1" in daily
    assert "max_active_runs=1" in monthly


def test_daily_dag_does_not_run_heavy_fact_rebuild() -> None:
    daily = _read("airflow/dags/citibike_daily_pipeline.py")
    assert "load_fact_trips" not in daily
    assert "sync_station_dimension" not in daily
    assert "run_dbt" in daily


def test_airflow_compose_is_valid_yaml_and_has_required_services() -> None:
    data = yaml.safe_load(_read("docker-compose.airflow.yml"))
    services = data["services"]
    assert {
        "airflow-db",
        "airflow-init",
        "airflow-api-server",
        "airflow-scheduler",
        "airflow-dag-processor",
        "airflow-triggerer",
    }.issubset(services)
    assert services["airflow-api-server"]["ports"] == ["${AIRFLOW_PORT:-8080}:8080"]


def test_dockerignore_excludes_large_local_data() -> None:
    dockerignore = _read(".dockerignore")
    assert "data/raw" in dockerignore
    assert ".venv" in dockerignore
    assert ".env" in dockerignore
