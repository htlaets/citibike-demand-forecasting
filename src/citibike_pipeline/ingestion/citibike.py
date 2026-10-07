"""Citi Bike GBFS loader."""

from __future__ import annotations

from typing import Any

from citibike_pipeline.http import HttpClient, SourceRequestError


def _feed_list(discovery: dict[str, Any]) -> list[dict[str, Any]]:
    data = discovery.get("data", {})
    if isinstance(data, dict) and isinstance(data.get("feeds"), list):
        return data["feeds"]
    if isinstance(data, dict):
        for locale in ("en", *data):
            locale_data = data.get(locale)
            if isinstance(locale_data, dict) and isinstance(locale_data.get("feeds"), list):
                return locale_data["feeds"]
    raise SourceRequestError("Citi Bike discovery response has no GBFS feed list")


def load(client: HttpClient, config: dict[str, Any]) -> dict[str, Any]:
    """Discover and download configured Citi Bike GBFS feeds."""
    discovery_url = str(config["discovery_url"])
    requested = [str(name) for name in config.get("feeds", [])]
    discovery = client.get_json(discovery_url)
    if not isinstance(discovery, dict):
        raise SourceRequestError("Citi Bike discovery response must be an object")

    available = {
        str(feed.get("name")): str(feed.get("url"))
        for feed in _feed_list(discovery)
        if isinstance(feed, dict) and feed.get("name") and feed.get("url")
    }
    missing = set(requested) - set(available)
    if missing:
        raise SourceRequestError(f"Citi Bike feeds not found: {', '.join(sorted(missing))}")

    feeds = {name: client.get_json(available[name]) for name in requested}
    return {"discovery_url": discovery_url, "feeds": feeds}
