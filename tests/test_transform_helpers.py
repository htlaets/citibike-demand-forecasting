from sqlalchemy.engine import make_url

from citibike_pipeline.transform.dbt_runner import _dbt_env


def test_database_url_can_be_parsed(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://citibike:secret@127.0.0.1:5433/citibike",
    )
    env = _dbt_env()
    assert env["DBT_HOST"] == "127.0.0.1"
    assert env["DBT_PORT"] == "5433"
    assert env["DBT_USER"] == "citibike"
    assert env["DBT_PASSWORD"] == "secret"
    assert env["DBT_DBNAME"] == "citibike"
