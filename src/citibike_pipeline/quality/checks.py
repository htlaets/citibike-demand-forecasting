"""Source-specific data-quality rules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class QualityIssue:
    check: str
    message: str
    severity: str = "error"


@dataclass
class QualityReport:
    source: str
    row_count: int = 0
    issues: list[QualityIssue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def add(self, check: str, message: str, severity: str = "error") -> None:
        self.issues.append(QualityIssue(check, message, severity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "passed": self.passed,
            "row_count": self.row_count,
            "metrics": self.metrics,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _unwrap(snapshot: Any) -> Any:
    if isinstance(snapshot, dict) and "payload" in snapshot and "source" in snapshot:
        return snapshot["payload"]
    return snapshot


def _rows_from_gbfs_feed(feed: Any) -> list[dict[str, Any]]:
    if not isinstance(feed, dict):
        return []
    data = feed.get("data", {})
    stations = data.get("stations", []) if isinstance(data, dict) else []
    return [row for row in stations if isinstance(row, dict)] if isinstance(stations, list) else []


def _check_required(
    rows: list[dict[str, Any]], required: Iterable[str], report: QualityReport, prefix: str = ""
) -> None:
    for field_name in required:
        missing = sum(field_name not in row for row in rows)
        nulls = sum(row.get(field_name) is None for row in rows)
        if missing:
            report.add("required_fields", f"{prefix}{field_name}: missing in {missing} rows")
        if nulls:
            report.add("nulls", f"{prefix}{field_name}: NULL in {nulls} rows")


def _check_duplicates(
    rows: list[dict[str, Any]], key: str, report: QualityReport, prefix: str = ""
) -> None:
    values = [row.get(key) for row in rows if row.get(key) is not None]
    duplicates = len(values) - len(set(values))
    if duplicates:
        report.add("duplicates", f"{prefix}{key}: {duplicates} duplicate values")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_numeric_range(
    rows: list[dict[str, Any]],
    field_name: str,
    minimum: float,
    maximum: float,
    report: QualityReport,
    prefix: str = "",
) -> None:
    invalid_type = 0
    out_of_range = 0
    for row in rows:
        value = row.get(field_name)
        if value is None:
            continue
        numeric = _as_float(value)
        if numeric is None:
            invalid_type += 1
        elif not minimum <= numeric <= maximum:
            out_of_range += 1
    if invalid_type:
        report.add("types", f"{prefix}{field_name}: {invalid_type} non-numeric values")
    if out_of_range:
        report.add(
            "ranges",
            f"{prefix}{field_name}: {out_of_range} values outside [{minimum}, {maximum}]",
        )


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _check_times(values: list[Any], report: QualityReport, field_name: str) -> None:
    parsed = [_parse_time(value) for value in values]
    invalid = sum(value is None for value in parsed)
    if invalid:
        report.add("types", f"{field_name}: {invalid} invalid timestamps")
    valid = [value for value in parsed if value is not None]
    if valid:
        report.metrics["time_min"] = min(valid).isoformat()
        report.metrics["time_max"] = max(valid).isoformat()


def check_citibike(snapshot: Any) -> QualityReport:
    payload = _unwrap(snapshot)
    report = QualityReport("citibike")
    feeds = payload.get("feeds", {}) if isinstance(payload, dict) else {}
    if not isinstance(feeds, dict):
        report.add("structure", "feeds must be an object")
        return report

    information = _rows_from_gbfs_feed(feeds.get("station_information"))
    statuses = _rows_from_gbfs_feed(feeds.get("station_status"))
    report.row_count = len(statuses)
    report.metrics.update(
        {"station_information_rows": len(information), "station_status_rows": len(statuses)}
    )
    if not information:
        report.add("row_count", "station_information contains no rows")
    if not statuses:
        report.add("row_count", "station_status contains no rows")

    _check_required(information, ("station_id", "name", "lat", "lon"), report, "info.")
    _check_required(
        statuses,
        ("station_id", "num_bikes_available", "num_docks_available"),
        report,
        "status.",
    )
    _check_duplicates(information, "station_id", report, "info.")
    _check_duplicates(statuses, "station_id", report, "status.")
    _check_numeric_range(information, "lat", 40.0, 42.0, report, "info.")
    _check_numeric_range(information, "lon", -75.0, -72.0, report, "info.")
    _check_numeric_range(statuses, "num_bikes_available", 0, 500, report, "status.")
    _check_numeric_range(statuses, "num_docks_available", 0, 500, report, "status.")

    known = {row.get("station_id") for row in information}
    orphan_count = sum(row.get("station_id") not in known for row in statuses)
    if orphan_count:
        report.add(
            "referential_integrity",
            f"{orphan_count} status rows have no matching station information",
            "warning",
        )
    return report


def check_weather(snapshot: Any) -> QualityReport:
    payload = _unwrap(snapshot)
    report = QualityReport("weather")
    hourly = payload.get("hourly", {}) if isinstance(payload, dict) else {}
    if not isinstance(hourly, dict):
        report.add("structure", "hourly must be an object")
        return report
    times = hourly.get("time", [])
    if not isinstance(times, list) or not times:
        report.add("row_count", "hourly.time contains no rows")
        return report

    report.row_count = len(times)
    _check_times(times, report, "hourly.time")
    rows: list[dict[str, Any]] = []
    for index in range(len(times)):
        rows.append(
            {
                key: values[index] if isinstance(values, list) and index < len(values) else None
                for key, values in hourly.items()
                if key != "time"
            }
        )
    for key, values in hourly.items():
        if not isinstance(values, list):
            report.add("structure", f"hourly.{key} must be an array")
        elif len(values) != len(times):
            report.add(
                "row_count",
                f"hourly.{key} has {len(values)} values; expected {len(times)}",
            )

    variables = [key for key in hourly if key != "time"]
    _check_required(rows, variables, report, "hourly.")
    ranges = {
        "temperature_2m": (-80, 60),
        "relative_humidity_2m": (0, 100),
        "precipitation": (0, 500),
        "weather_code": (0, 99),
        "wind_speed_10m": (0, 300),
    }
    for field_name, (minimum, maximum) in ranges.items():
        if field_name in hourly:
            _check_numeric_range(rows, field_name, minimum, maximum, report, "hourly.")
    if len(set(times)) != len(times):
        report.add("duplicates", "hourly.time contains duplicate timestamps")
    return report


def check_traffic(snapshot: Any) -> QualityReport:
    payload = _unwrap(snapshot)
    report = QualityReport("traffic")
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        report.add("structure", "payload must be a list of objects")
        return report
    rows = payload
    report.row_count = len(rows)
    if not rows:
        report.add("row_count", "traffic response contains no rows")
        return report
    _check_required(rows, ("link_id", "speed", "travel_time", "data_as_of"), report)
    _check_duplicates(rows, "link_id", report)
    _check_numeric_range(rows, "speed", 0, 150, report)
    _check_numeric_range(rows, "travel_time", 0, 86400, report)
    _check_times([row.get("data_as_of") for row in rows], report, "data_as_of")
    return report


CHECKERS = {
    "citibike": check_citibike,
    "weather": check_weather,
    "traffic": check_traffic,
}


def check_source(source: str, snapshot: Any) -> QualityReport:
    """Run the checker registered for a source name."""
    try:
        checker = CHECKERS[source]
    except KeyError as exc:
        raise ValueError(f"Unknown source: {source}") from exc
    return checker(snapshot)
