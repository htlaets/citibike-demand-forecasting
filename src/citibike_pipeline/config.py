"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/config.yaml")


class ConfigError(ValueError):
    """Raised when the pipeline configuration is invalid."""


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML configuration and validate its required top-level sections."""
    config_path = Path(path or os.getenv("PIPELINE_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        raise ConfigError(f"Configuration file does not exist: {config_path}")

    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    if not isinstance(config, dict):
        raise ConfigError("Configuration must contain a YAML mapping")

    for section in ("project", "http", "sources"):
        if not isinstance(config.get(section), dict):
            raise ConfigError(f"Missing or invalid configuration section: {section}")

    missing_sources = {"citibike", "weather", "traffic"} - set(config["sources"])
    if missing_sources:
        names = ", ".join(sorted(missing_sources))
        raise ConfigError(f"Missing source configuration: {names}")
    return config
