"""RAW snapshot and quality report persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


def build_snapshot(source: str, payload: Any, fetched_at: datetime | None = None) -> dict[str, Any]:
    """Wrap a source response in a stable ingestion envelope."""
    timestamp = fetched_at or utc_now()
    return {
        "source": source,
        "fetched_at_utc": timestamp.isoformat(),
        "payload": payload,
    }


def write_json(data: Any, directory: str | Path, source: str, *, suffix: str = "") -> Path:
    """Atomically write JSON using a collision-resistant UTC filename."""
    target_dir = Path(directory) / source
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    target = target_dir / f"{timestamp}{suffix}.json"
    temporary = target.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(target)
    return target


def read_json(path: str | Path) -> Any:
    """Read a UTF-8 JSON file."""
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)
