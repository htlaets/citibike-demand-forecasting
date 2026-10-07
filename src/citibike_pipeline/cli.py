"""Command-line entry point for ingestion and quality checks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from citibike_pipeline.config import ConfigError, load_config
from citibike_pipeline.http import HttpClient, SourceRequestError
from citibike_pipeline.ingestion import citibike, traffic, weather
from citibike_pipeline.quality import QualityReport, check_source
from citibike_pipeline.storage import build_snapshot, read_json, write_json

Loader = Callable[[HttpClient, dict[str, Any]], Any]
LOADERS: dict[str, Loader] = {
    "citibike": citibike.load,
    "weather": weather.load,
    "traffic": traffic.load,
}


def _print_report(report: QualityReport) -> None:
    state = "PASS" if report.passed else "FAIL"
    print(f"[{state}] {report.source}: {report.row_count} rows")
    for issue in report.issues:
        print(f"  - {issue.severity.upper()} {issue.check}: {issue.message}")


def _ingest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    client = HttpClient(config["http"])
    source_names = list(LOADERS) if args.source == "all" else [args.source]
    raw_dir = Path(args.output_dir or config["project"]["raw_data_dir"])
    quality_dir = Path(config["project"]["quality_data_dir"])
    failed = False

    for source in source_names:
        payload = LOADERS[source](client, config["sources"][source])
        snapshot = build_snapshot(source, payload)
        raw_path = write_json(snapshot, raw_dir, source)
        report = check_source(source, snapshot)
        report_data = report.to_dict() | {"raw_path": str(raw_path)}
        report_path = write_json(report_data, quality_dir, source, suffix="-quality")
        print(f"Saved {source}: {raw_path}")
        print(f"Quality report: {report_path}")
        _print_report(report)
        failed = failed or not report.passed
    return 1 if failed else 0


def _quality(args: argparse.Namespace) -> int:
    snapshot = read_json(args.path)
    report = check_source(args.source, snapshot)
    _print_report(report)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citibike-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="download RAW source snapshots")
    ingest_parser.add_argument(
        "--source", choices=("all", *LOADERS), default="all", help="source to download"
    )
    ingest_parser.add_argument("--config", help="path to YAML configuration")
    ingest_parser.add_argument("--output-dir", help="override RAW output directory")
    ingest_parser.set_defaults(handler=_ingest)

    quality_parser = subparsers.add_parser("quality", help="check an existing RAW JSON file")
    quality_parser.add_argument("path", help="path to the RAW JSON snapshot")
    quality_parser.add_argument("--source", choices=tuple(LOADERS), required=True)
    quality_parser.add_argument(
        "--json", action="store_true", help="print the complete JSON report"
    )
    quality_parser.set_defaults(handler=_quality)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (ConfigError, SourceRequestError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
