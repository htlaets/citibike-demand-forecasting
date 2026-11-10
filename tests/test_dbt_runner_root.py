from pathlib import Path

from citibike_pipeline.transform.dbt_runner import _project_root


def test_project_root_can_be_overridden(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CITIBIKE_PROJECT_ROOT", str(tmp_path))
    assert _project_root() == tmp_path.resolve()
