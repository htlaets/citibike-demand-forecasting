"""Command-line interface for the end-to-end ingestion layer."""

from __future__ import annotations

import argparse
import json
import sys

from citibike_pipeline.config import ConfigError, load_config
from citibike_pipeline.database.connection import database_healthcheck, get_engine
from citibike_pipeline.database.metadata import list_watermarks
from citibike_pipeline.http import HttpClient, SourceRequestError
from citibike_pipeline.ingestion import citibike_trips, gbfs, traffic, weather

SOURCES = ("citibike_trips", "citibike_gbfs", "weather", "traffic")


def _print_result(name: str, value: object) -> None:
    print(f"\n[{name}]")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _ingest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    client = HttpClient(config["http"])
    engine = get_engine()
    names = SOURCES if args.source == "all" else (args.source,)

    for name in names:
        print(f"\n==> Ingesting {name}")
        if name == "citibike_trips":
            result = citibike_trips.ingest(
                client,
                config,
                start_month=args.start_month,
                end_month=args.end_month,
                engine=engine,
            )
        elif name == "citibike_gbfs":
            result = gbfs.ingest(client, config, engine=engine)
        elif name == "weather":
            result = weather.ingest(
                client,
                config,
                start_date=args.start_date,
                end_date=args.end_date,
                engine=engine,
            )
        else:
            result = traffic.ingest(
                client,
                config,
                since_hours=args.traffic_since_hours,
                engine=engine,
            )
        _print_result(name, result)
    return 0


def _watermarks(_: argparse.Namespace) -> int:
    for item in list_watermarks():
        print(
            f"{item['source_name']:<18} value={item['watermark_value']!s:<12} "
            f"timestamp={item['watermark_ts']!s:<28} updated={item['updated_at']}"
        )
    return 0


def _health(_: argparse.Namespace) -> int:
    if database_healthcheck():
        print("[OK] PostgreSQL is reachable and SELECT 1 succeeded.")
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citibike-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_parser = sub.add_parser("ingest", help="incrementally ingest external sources")
    ingest_parser.add_argument("--source", choices=("all", *SOURCES), default="all")
    ingest_parser.add_argument("--config", help="path to config YAML")
    ingest_parser.add_argument("--start-month", help="Citi Bike first month, YYYY-MM")
    ingest_parser.add_argument("--end-month", help="Citi Bike last month, YYYY-MM")
    ingest_parser.add_argument("--start-date", help="Weather first date, YYYY-MM-DD")
    ingest_parser.add_argument("--end-date", help="Weather last date, YYYY-MM-DD")
    ingest_parser.add_argument(
        "--traffic-since-hours",
        type=int,
        help="Traffic bootstrap lookback when no watermark exists",
    )
    ingest_parser.set_defaults(handler=_ingest)

    wm_parser = sub.add_parser("watermarks", help="show incremental source watermarks")
    wm_parser.set_defaults(handler=_watermarks)

    health_parser = sub.add_parser("db-health", help="check PostgreSQL connectivity")
    health_parser.set_defaults(handler=_health)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (ConfigError, SourceRequestError, OSError, ValueError, RuntimeError) as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
