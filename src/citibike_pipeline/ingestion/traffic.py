"""NYC DOT real-time traffic speed loader."""

from __future__ import annotations

import os
from typing import Any

from citibike_pipeline.http import HttpClient, SourceRequestError


def load(client: HttpClient, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Download the latest known traffic observation for every road link."""
    url = str(config["url"])
    params: dict[str, Any] = {
        "$limit": int(config.get("limit", 5000)),
        "$order": "data_as_of DESC",
    }
    headers = {}
    app_token = os.getenv("NYC_OPEN_DATA_APP_TOKEN")
    if app_token:
        headers["X-App-Token"] = app_token

    payload = client.get_json(url, params=params, headers=headers or None)
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise SourceRequestError("NYC DOT response must be a list of objects")
    if config.get("latest_per_link", True):
        latest_by_link: dict[str, dict[str, Any]] = {}
        for row in payload:
            link_id = row.get("link_id")
            if link_id is not None and str(link_id) not in latest_by_link:
                latest_by_link[str(link_id)] = row
        return list(latest_by_link.values())
    return payload
