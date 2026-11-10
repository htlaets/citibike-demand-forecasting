"""Common ingestion utilities."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Connection, text


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_month(value: str) -> date:
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def month_string(value: date) -> str:
    return value.strftime("%Y-%m")


def next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def iter_months(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current = next_month(current)


def previous_month(today: date | None = None) -> date:
    current = today or date.today()
    first = current.replace(day=1)
    if first.month == 1:
        return date(first.year - 1, 12, 1)
    return date(first.year, first.month - 1, 1)


def ny_local_to_utc(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        parsed = parsed.dt.tz_localize(
            "America/New_York", ambiguous="NaT", nonexistent="shift_forward"
        )
    return parsed.dt.tz_convert("UTC")


def raw_path(base: str | Path, source: str, *parts: str) -> Path:
    path = Path(base) / source
    for part in parts:
        path /= part
    path.mkdir(parents=True, exist_ok=True)
    return path


def execute_batch(
    connection: Connection,
    sql: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    result = connection.execute(text(sql), rows)
    return max(0, int(result.rowcount or 0))
