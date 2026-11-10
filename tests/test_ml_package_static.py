from pathlib import Path


def test_pyproject_pins_current_catboost_family() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "catboost>=1.2.10,<2" in text


def test_artifacts_are_gitignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "artifacts/models/**" in text
    assert "artifacts/metrics/**" in text
