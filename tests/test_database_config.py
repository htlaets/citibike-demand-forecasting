from pathlib import Path


def test_required_database_files_exist() -> None:
    required = [
        Path("docker-compose.yml"),
        Path("sql/init/001_init.sql"),
        Path(".env.example"),
        Path("config/config.yaml"),
    ]
    missing = [str(path) for path in required if not path.exists()]
    assert not missing, f"Missing required database foundation files: {missing}"
