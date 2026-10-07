"""Open-Meteo forecast loader."""

from __future__ import annotations

from typing import Any

from citibike_pipeline.http import HttpClient, SourceRequestError


def load(client: HttpClient, config: dict[str, Any]) -> dict[str, Any]:
    """Download an hourly forecast for the configured NYC coordinates."""
    variables = config.get("hourly", [])
    if not isinstance(variables, list) or not variables:
        raise SourceRequestError("Open-Meteo hourly variables must be a non-empty list")
    params = {
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "timezone": config.get("timezone", "America/New_York"),
        "forecast_days": config.get("forecast_days", 7),
        "hourly": ",".join(str(variable) for variable in variables),
    }
    payload = client.get_json(str(config["url"]), params=params)
    if not isinstance(payload, dict):
        raise SourceRequestError("Open-Meteo response must be an object")
    return payload
