"""Run dbt with connection values derived from the project's DATABASE_URL."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from sqlalchemy.engine import make_url

from citibike_pipeline.database.connection import get_database_url


def _dbt_env() -> dict[str, str]:
    url = make_url(get_database_url())
    if url.get_backend_name() not in {"postgresql", "postgres"}:
        raise RuntimeError("dbt package currently supports the project's PostgreSQL target only")

    env = os.environ.copy()
    env.update(
        {
            "DBT_HOST": str(url.host or "127.0.0.1"),
            "DBT_PORT": str(url.port or 5432),
            "DBT_USER": str(url.username or ""),
            "DBT_PASSWORD": str(url.password or ""),
            "DBT_DBNAME": str(url.database or ""),
        }
    )
    return env


def run_dbt(arguments: Sequence[str] = ("build",)) -> int:
    """Execute dbt in the repository-local project/profile directories."""
    project_dir = Path("dbt")
    profiles_dir = project_dir / "profiles"

    if not project_dir.exists():
        raise RuntimeError("dbt project directory not found: ./dbt")

    command = [
        sys.executable,
        "-m",
        "dbt.cli.main",
        *arguments,
        "--project-dir",
        str(project_dir),
        "--profiles-dir",
        str(profiles_dir),
    ]
    completed = subprocess.run(command, env=_dbt_env(), check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"dbt {' '.join(arguments)} failed with code {completed.returncode}")
    return completed.returncode
