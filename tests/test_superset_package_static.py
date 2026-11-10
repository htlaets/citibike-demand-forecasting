import ast
from pathlib import Path

import yaml


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_superset_compose_is_valid_yaml() -> None:
    data = yaml.safe_load(_read("docker-compose.superset.yml"))

    assert {"superset-db", "superset-init", "superset"}.issubset(data["services"])

    superset = data["services"]["superset"]
    assert superset["image"] == "citibike-superset:6.0.0"
    assert superset["build"]["dockerfile"] == "docker/superset/Dockerfile"
    assert superset["ports"] == ["${SUPERSET_PORT:-8088}:8088"]


def test_bootstrap_is_valid_python_and_declares_two_dashboards() -> None:
    source = _read("superset/bootstrap_assets.py")
    ast.parse(source)

    assert "citibike-demand-forecast" in source
    assert "citibike-platform-operations" in source

    # Пользовательские названия визуализаций в итоговой версии русифицированы.
    assert 'name="Фактический спрос и прогноз CatBoost"' in source
    assert 'name="Ошибки качества данных по типам проверок"' in source

    assert 'title="Citi Bike — Спрос и прогноз"' in source
    assert 'title="Citi Bike — Мониторинг платформы данных"' in source


def test_bootstrap_creates_compact_gold_views() -> None:
    source = _read("superset/bootstrap_assets.py")

    for name in (
        "gold.superset_hourly_demand",
        "gold.superset_top_stations",
        "gold.superset_forecast_comparison",
        "gold.superset_model_metrics",
        "gold.superset_pipeline_monitoring",
        "gold.superset_pipeline_kpi",
        "gold.superset_dq_monitoring",
        "gold.superset_dq_summary",
    ):
        assert name in source


def test_check_assets_is_valid_python() -> None:
    source = _read("superset/check_assets.py")
    ast.parse(source)

    assert "citibike-demand-forecast" in source
    assert "citibike-platform-operations" in source
    assert "Citi Bike — Спрос и прогноз" in source
    assert "Citi Bike — Мониторинг платформы данных" in source
