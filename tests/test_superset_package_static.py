import ast
from pathlib import Path

import yaml


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_superset_compose_is_valid_yaml() -> None:
    data = yaml.safe_load(_read("docker-compose.superset.yml"))
    assert {"superset-db", "superset-init", "superset"}.issubset(data["services"])
    assert data["services"]["superset"]["image"] == "apache/superset:6.0.0"
    assert data["services"]["superset"]["ports"] == ["${SUPERSET_PORT:-8088}:8088"]


def test_bootstrap_is_valid_python_and_declares_two_dashboards() -> None:
    source = _read("superset/bootstrap_assets.py")
    ast.parse(source)
    assert "citibike-demand-forecast" in source
    assert "citibike-platform-operations" in source
    assert 'name="Actual vs CatBoost forecast"' in source
    assert 'name="DQ failed rows by check type"' in source


def test_bootstrap_creates_compact_gold_views() -> None:
    source = _read("superset/bootstrap_assets.py")
    for name in (
        "gold.superset_hourly_demand",
        "gold.superset_top_stations",
        "gold.superset_forecast_comparison",
        "gold.superset_model_metrics",
        "gold.superset_pipeline_kpi",
        "gold.superset_dq_summary",
    ):
        assert name in source


def test_check_assets_is_valid_python() -> None:
    ast.parse(_read("superset/check_assets.py"))
