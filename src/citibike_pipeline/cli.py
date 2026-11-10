"""Command-line interface for the Citi Bike data platform."""

from __future__ import annotations

import argparse
import json
import sys

from citibike_pipeline.config import ConfigError, load_config
from citibike_pipeline.database.connection import database_healthcheck, get_engine
from citibike_pipeline.database.metadata import list_watermarks
from citibike_pipeline.http import HttpClient, SourceRequestError
from citibike_pipeline.ingestion import citibike_trips, gbfs, traffic, weather
from citibike_pipeline.quality import (
    check_all_schemas,
    quarantine_invalid_records,
    run_quality_checks,
    summarize,
)

SOURCES = ("citibike_trips", "citibike_gbfs", "weather", "traffic")
DQ_DATASETS = ("citibike_trips", "weather", "traffic", "gbfs")


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
                start_date=args.traffic_start_date,
                end_date=args.traffic_end_date,
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


def _dq(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    engine = get_engine()
    print(f"Running warehouse DQ checks: dataset={args.dataset}")
    results = run_quality_checks(config, dataset=args.dataset, engine=engine)

    for result in results:
        failed = result.failed_rows if result.failed_rows is not None else "-"
        print(
            f"[{result.status:<4}] "
            f"{result.check_type:<22} "
            f"{result.dataset_name:<32} "
            f"{result.check_name} failed={failed}"
        )

    summary = summarize(results)
    print(
        "\nDQ summary: "
        f"PASS={summary.get('PASS', 0)} "
        f"WARN={summary.get('WARN', 0)} "
        f"FAIL={summary.get('FAIL', 0)}"
    )

    if args.quarantine:
        quarantined = quarantine_invalid_records(dataset=args.dataset, engine=engine)
        print("\nQuarantine:")
        for name, count in quarantined.items():
            print(f"  {name}: inserted={count}")
    return 0


def _schema_check(_: argparse.Namespace) -> int:
    results = check_all_schemas()
    breaking = False
    for item in results:
        print(
            f"[{item['status']:<10}] {item['dataset']:<36} "
            f"version={item['version']} breaking={item['breaking']}"
        )
        breaking = breaking or bool(item["breaking"])

    if breaking:
        print(
            "\nBreaking schema drift was registered. "
            "Review meta.schema_changes before downstream processing."
        )
    return 0


def _dbt(args: argparse.Namespace) -> int:
    from citibike_pipeline.transform import run_dbt

    return run_dbt((args.command,))


def _transform(_: argparse.Namespace) -> int:
    from citibike_pipeline.transform import load_fact_trips, run_dbt, sync_station_dimension
    from citibike_pipeline.transform.core import warehouse_counts

    engine = get_engine()

    print("\n==> Synchronizing SCD2 station dimension")
    _print_result("silver.dim_station", sync_station_dimension(engine))

    print("\n==> Loading valid SILVER trip fact")
    _print_result("silver.fact_trip", load_fact_trips(engine))

    print("\n==> Running dbt build")
    run_dbt(("build",))

    print("\n==> Warehouse counts")
    _print_result("warehouse", warehouse_counts(engine))
    return 0


def _train(args: argparse.Namespace) -> int:
    from citibike_pipeline.ml import train_forecasting_pipeline

    config = load_config(args.config)
    result = train_forecasting_pipeline(
        config,
        top_stations=args.top_stations,
        iterations=args.iterations,
        smoke=args.smoke,
        persist=not args.no_persist,
        engine=get_engine(),
    )
    _print_result(
        "forecast_training",
        {
            "model_version": result["model_version"],
            "top_stations": result["top_stations"],
            "train_rows": result["train_rows"],
            "validation_rows": result["validation_rows"],
            "test_rows": result["test_rows"],
            "coverage": result["coverage"],
            "baseline_test": result["baseline_test"],
            "selected_feature_set": result["selected_feature_set"],
            "catboost_test": result["catboost_test"],
            "persisted": result["persisted"],
        },
    )
    return 0


def _model_metrics(args: argparse.Namespace) -> int:
    from citibike_pipeline.ml.persistence import list_metrics

    _print_result("model_metrics", list_metrics(limit=args.limit, engine=get_engine()))
    return 0


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
    ingest_parser.add_argument("--traffic-since-hours", type=int)
    ingest_parser.add_argument("--traffic-start-date")
    ingest_parser.add_argument("--traffic-end-date")
    ingest_parser.set_defaults(handler=_ingest)

    wm_parser = sub.add_parser("watermarks", help="show incremental source watermarks")
    wm_parser.set_defaults(handler=_watermarks)

    health_parser = sub.add_parser("db-health", help="check PostgreSQL connectivity")
    health_parser.set_defaults(handler=_health)

    dq_parser = sub.add_parser("dq", help="run persisted PostgreSQL data-quality checks")
    dq_parser.add_argument("--dataset", choices=("all", *DQ_DATASETS), default="all")
    dq_parser.add_argument("--quarantine", action="store_true")
    dq_parser.add_argument("--config", help="path to config YAML")
    dq_parser.set_defaults(handler=_dq)

    schema_parser = sub.add_parser(
        "schema-check", help="register schemas and detect schema drift"
    )
    schema_parser.set_defaults(handler=_schema_check)

    dbt_parser = sub.add_parser("dbt", help="run repository-local dbt command")
    dbt_parser.add_argument(
        "--command",
        choices=("debug", "run", "test", "build", "compile"),
        default="build",
    )
    dbt_parser.set_defaults(handler=_dbt)

    transform_parser = sub.add_parser(
        "transform",
        help="build SCD2 dimension, SILVER fact and dbt SILVER/GOLD marts",
    )
    transform_parser.set_defaults(handler=_transform)

    train_parser = sub.add_parser(
        "train",
        help="train Seasonal Naive and CatBoost demand forecasting models",
    )
    train_parser.add_argument("--config", help="path to config YAML")
    train_parser.add_argument("--top-stations", type=int)
    train_parser.add_argument("--iterations", type=int)
    train_parser.add_argument(
        "--smoke",
        action="store_true",
        help="fast 20-station/25-iteration validation without persistence",
    )
    train_parser.add_argument(
        "--no-persist",
        action="store_true",
        help="do not write model metrics, forecasts or artifacts",
    )
    train_parser.set_defaults(handler=_train)

    metrics_parser = sub.add_parser(
        "model-metrics",
        help="show the latest persisted model evaluation metrics",
    )
    metrics_parser.add_argument("--limit", type=int, default=30)
    metrics_parser.set_defaults(handler=_model_metrics)

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
