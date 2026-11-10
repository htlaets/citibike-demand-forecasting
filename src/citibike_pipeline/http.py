"""Shared HTTP client with retry, timeout and streaming-download support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SourceRequestError(RuntimeError):
    """Raised when an external source cannot be requested or decoded."""


class HttpClient:
    """HTTP client configured for transient failures and rate limits."""

    def __init__(self, config: dict[str, Any]) -> None:
        base_timeout = float(config.get("timeout_seconds", 30))
        self.connect_timeout = float(config.get("connect_timeout_seconds", min(base_timeout, 15)))
        self.read_timeout = float(config.get("read_timeout_seconds", base_timeout))
        self.download_read_timeout = float(config.get("download_read_timeout_seconds", 300))

        retries = int(config.get("retries", 4))
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=float(config.get("backoff_factor", 1.0)),
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
        )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = str(
            config.get("user_agent", "citibike-demand-forecasting/1.0")
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=(self.connect_timeout, self.read_timeout),
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise SourceRequestError(f"GET {url} failed: {exc}") from exc

    def download(
        self,
        url: str,
        target: str | Path,
        *,
        headers: dict[str, str] | None = None,
        chunk_size: int = 1024 * 1024,
        show_progress: bool = False,
    ) -> Path:
        """Stream a remote object to disk atomically with optional progress output."""
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = target_path.with_suffix(target_path.suffix + ".part")
        temporary.unlink(missing_ok=True)

        try:
            with self.session.get(
                url,
                headers=headers,
                timeout=(self.connect_timeout, self.download_read_timeout),
                stream=True,
            ) as response:
                response.raise_for_status()

                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                last_reported_mb = -25

                if show_progress:
                    if total:
                        print(f"Downloading {target_path.name}: {total / 1024 / 1024:.1f} MB")
                    else:
                        print(f"Downloading {target_path.name}...")

                with temporary.open("wb") as stream:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        stream.write(chunk)
                        downloaded += len(chunk)

                        if show_progress:
                            downloaded_mb = int(downloaded / 1024 / 1024)
                            if downloaded_mb - last_reported_mb >= 25:
                                last_reported_mb = downloaded_mb
                                if total:
                                    pct = downloaded / total * 100
                                    print(
                                        f"  downloaded {downloaded / 1024 / 1024:.1f} MB "
                                        f"({pct:.1f}%)"
                                    )
                                else:
                                    print(
                                        f"  downloaded {downloaded / 1024 / 1024:.1f} MB"
                                    )

            temporary.replace(target_path)
            if show_progress:
                print(
                    f"Download complete: {target_path} "
                    f"({target_path.stat().st_size / 1024 / 1024:.1f} MB)"
                )
            return target_path

        except requests.RequestException as exc:
            temporary.unlink(missing_ok=True)
            raise SourceRequestError(f"Download {url} failed: {exc}") from exc
