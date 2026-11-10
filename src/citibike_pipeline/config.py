"""Project configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/config.yaml")
REQUIRED_SOURCES = {"citibike_trips", "citibike_gbfs", "weather", "traffic"}


class ConfigError(ValueError):
    """Raised when the pipeline configuration is invalid."""


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or os.getenv("PIPELINE_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        raise ConfigError(f"Configuration file does not exist: {config_path}")

    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    if not isinstance(config, dict):
        raise ConfigError("Configuration must contain a YAML mapping")

    for section in ("project", "database", "http", "sources"):
        if not isinstance(config.get(section), dict):
            raise ConfigError(f"Missing or invalid configuration section: {section}")

    missing = REQUIRED_SOURCES - set(config["sources"])
    if missing:
        raise ConfigError(f"Missing source configuration: {', '.join(sorted(missing))}")

    return config
