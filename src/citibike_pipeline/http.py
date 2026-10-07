"""Shared HTTP client with retry behavior."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SourceRequestError(RuntimeError):
    """Raised when a source cannot be requested or decoded."""


class HttpClient:
    """Small JSON HTTP client configured for transient API failures."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.timeout = float(config.get("timeout_seconds", 30))
        retries = int(config.get("retries", 3))
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=float(config.get("backoff_factor", 0.5)),
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = str(
            config.get("user_agent", "citibike-demand-forecasting/0.1.0")
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET an endpoint, validate the response and decode JSON."""
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise SourceRequestError(f"GET {url} failed: {exc}") from exc
