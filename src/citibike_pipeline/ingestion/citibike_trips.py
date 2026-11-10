"""Incremental Citi Bike monthly Trip History ingestion."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine

from citibike_pipeline.database.connection import get_engine
from citibike_pipeline.database.metadata import (
    finish_load,
    get_watermark,
    set_watermark,
    start_load,
)
from citibike_pipeline.http import HttpClient, SourceRequestError
from citibike_pipeline.ingestion.common import (
    execute_batch,
    iter_months,
    month_string,
    next_month,
    ny_local_to_utc,
    parse_month,
    previous_month,
    raw_path,
)

INSERT_SQL = """
INSERT INTO raw.citibike_trips (
    ride_id, rideable_type, started_at, ended_at,
    start_station_name, start_station_id, end_station_name, end_station_id,
    start_lat, start_lng, end_lat, end_lng, member_casual,
    source_file, source_month, load_id
)
VALUES (
    :ride_id, :rideable_type, :started_at, :ended_at,
    :start_station_name, :start_station_id, :end_station_name, :end_station_id,
    :start_lat, :start_lng, :end_lat, :end_lng, :member_casual,
    :source_file, :source_month, :load_id
)
ON CONFLICT (ride_id) DO NOTHING
"""

REQUIRED_COLUMNS = {
    "ride_id",
    "rideable_type",
    "started_at",
    "ended_at",
    "start_station_name",
    "start_station_id",
    "end_station_name",
    "end_station_id",
    "start_lat",
    "start_lng",
    "end_lat",
    "end_lng",
    "member_casual",
}


def archive_candidates(base_url: str, month: date) -> list[str]:
    code = month.strftime("%Y%m")
    base = base_url.rstrip("/")
    return [
        f"{base}/{code}-citibike-tripdata.zip",
        f"{base}/{code}-citibike-tripdata.csv.zip",
    ]


def _valid_zip(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None and any(
                name.lower().endswith(".csv") for name in zf.namelist()
            )
    except zipfile.BadZipFile:
        return False


def download_month(
    client: HttpClient, base_url: str, month: date, destination: Path
) -> Path:
    errors: list[str] = []

    for url in archive_candidates(base_url, month):
        target = destination / Path(url).name

        if _valid_zip(target):
            print(
                f"Using existing archive: {target} "
                f"({target.stat().st_size / 1024 / 1024:.1f} MB)"
            )
            return target

        target.unlink(missing_ok=True)
        print(f"Trying Citi Bike archive: {url}")

        try:
            downloaded = client.download(url, target, show_progress=True)
            if not _valid_zip(downloaded):
                downloaded.unlink(missing_ok=True)
                raise SourceRequestError(
                    f"Downloaded object is not a valid Citi Bike ZIP archive: {url}"
                )
            return downloaded
        except SourceRequestError as exc:
            errors.append(str(exc))
            print(f"  candidate failed: {exc}")

    raise SourceRequestError(
        f"No Citi Bike archive found for {month_string(month)}. " + " | ".join(errors)
    )


def _normalize_chunk(
    frame: pd.DataFrame, *, source_file: str, source_month: date, load_id: int
) -> tuple[list[dict[str, Any]], int]:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(
            f"Unexpected Citi Bike schema in {source_file}; missing columns: "
            f"{', '.join(sorted(missing))}"
        )

    # Keep the official source schema, but enforce stable target types.
    data = frame[list(REQUIRED_COLUMNS)].copy()
    data["started_at"] = ny_local_to_utc(data["started_at"])
    data["ended_at"] = ny_local_to_utc(data["ended_at"])

    for col in ("start_lat", "start_lng", "end_lat", "end_lng"):
        data[col] = pd.to_numeric(data[col], errors="coerce")

    invalid_key = data["ride_id"].isna() | data["ride_id"].astype(str).str.strip().eq("")
    rejected = int(invalid_key.sum())
    data = data.loc[~invalid_key].copy()

    for col in data.columns:
        data[col] = data[col].astype(object).where(pd.notna(data[col]), None)

    records = data.to_dict(orient="records")
    for row in records:
        row["ride_id"] = str(row["ride_id"])
        row["source_file"] = source_file
        row["source_month"] = source_month
        row["load_id"] = load_id

    return records, rejected


def _mark_failed(
    load_id: int,
    *,
    month: date,
    received: int,
    inserted: int,
    rejected: int,
    archive: Path | None,
    error: BaseException,
    engine: Engine,
) -> None:
    # finish_load expects an Exception for typing, but BaseException works at runtime
    # and lets us correctly record Ctrl+C / KeyboardInterrupt as FAILED.
    finish_load(
        load_id,
        status="FAILED",
        watermark_to=month_string(month),
        rows_received=received,
        rows_inserted=inserted,
        rows_rejected=rejected,
        raw_location=str(archive) if archive else None,
        error=error,  # type: ignore[arg-type]
        engine=engine,
    )


def ingest_month(
    client: HttpClient,
    config: dict[str, Any],
    month: date,
    *,
    engine: Engine | None = None,
    chunk_size: int | None = None,
) -> dict[str, int | str]:
    db = engine or get_engine()
    source = "citibike_trips"
    source_cfg = config["sources"][source]
    effective_chunk_size = int(chunk_size or source_cfg.get("chunk_size", 20_000))

    wm = get_watermark(source, db)
    load_id = start_load(
        source,
        run_key=month_string(month),
        watermark_from=wm.value,
        engine=db,
    )

    received = inserted = rejected = 0
    archive: Path | None = None

    print(
        f"Citi Bike month {month_string(month)}: "
        f"chunk_size={effective_chunk_size:,}, load_id={load_id}"
    )

    try:
        out_dir = raw_path(
            config["project"]["raw_data_dir"],
            source,
            month.strftime("%Y"),
            month.strftime("%m"),
        )
        archive = download_month(
            client,
            str(source_cfg["base_url"]),
            month,
            out_dir,
        )

        with zipfile.ZipFile(archive) as zf:
            csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError(f"{archive.name} contains no CSV files")

            print(f"Archive contains {len(csv_names)} CSV file(s).")

            for file_index, csv_name in enumerate(csv_names, start=1):
                print(f"[{file_index}/{len(csv_names)}] Reading {csv_name}")

                with zf.open(csv_name) as stream:
                    for chunk_index, frame in enumerate(
                        pd.read_csv(
                            stream,
                            chunksize=effective_chunk_size,
                            low_memory=False,
                        ),
                        start=1,
                    ):
                        received += len(frame)
                        rows, chunk_rejected = _normalize_chunk(
                            frame,
                            source_file=f"{archive.name}:{csv_name}",
                            source_month=month,
                            load_id=load_id,
                        )
                        rejected += chunk_rejected

                        # Commit every chunk. This makes progress visible from another
                        # session, bounds transaction size and keeps reruns safe because
                        # ride_id is a primary key with ON CONFLICT DO NOTHING.
                        with db.begin() as connection:
                            chunk_inserted = execute_batch(connection, INSERT_SQL, rows)

                        inserted += chunk_inserted

                        print(
                            f"  chunk {chunk_index:>4}: "
                            f"received={received:,} "
                            f"inserted={inserted:,} "
                            f"rejected={rejected:,}"
                        )

        set_watermark(source, value=month_string(month), engine=db)
        finish_load(
            load_id,
            status="SUCCESS",
            watermark_to=month_string(month),
            rows_received=received,
            rows_inserted=inserted,
            rows_rejected=rejected,
            raw_location=str(archive),
            engine=db,
        )

        print(
            f"Citi Bike {month_string(month)} complete: "
            f"received={received:,}, inserted={inserted:,}, rejected={rejected:,}"
        )

        return {
            "month": month_string(month),
            "received": received,
            "inserted": inserted,
            "rejected": rejected,
        }

    except KeyboardInterrupt as exc:
        print("\nCiti Bike ingestion interrupted by user; marking load as FAILED.")
        _mark_failed(
            load_id,
            month=month,
            received=received,
            inserted=inserted,
            rejected=rejected,
            archive=archive,
            error=exc,
            engine=db,
        )
        raise

    except Exception as exc:
        _mark_failed(
            load_id,
            month=month,
            received=received,
            inserted=inserted,
            rejected=rejected,
            archive=archive,
            error=exc,
            engine=db,
        )
        raise


def ingest(
    client: HttpClient,
    config: dict[str, Any],
    *,
    start_month: str | None = None,
    end_month: str | None = None,
    engine: Engine | None = None,
) -> list[dict[str, int | str]]:
    db = engine or get_engine()
    source_cfg = config["sources"]["citibike_trips"]
    wm = get_watermark("citibike_trips", db)

    if start_month:
        start = parse_month(start_month)
    elif wm.value:
        start = next_month(parse_month(wm.value))
    else:
        start = parse_month(str(source_cfg.get("bootstrap_start_month", "2026-01")))

    end = parse_month(end_month) if end_month else previous_month()
    if start > end:
        return []

    results = []
    for month in iter_months(start, end):
        results.append(ingest_month(client, config, month, engine=db))
    return results
