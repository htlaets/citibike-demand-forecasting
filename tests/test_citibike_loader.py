import zipfile
from datetime import date
from pathlib import Path

from citibike_pipeline.ingestion.citibike_trips import (
    _valid_zip,
    archive_candidates,
)


def test_citibike_archive_candidates() -> None:
    urls = archive_candidates("https://s3.amazonaws.com/tripdata", date(2026, 9, 1))
    assert urls[0].endswith("/202609-citibike-tripdata.zip")
    assert urls[1].endswith("/202609-citibike-tripdata.csv.zip")


def test_valid_zip_requires_csv(tmp_path: Path) -> None:
    archive = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("data.csv", "ride_id\nabc\n")
    assert _valid_zip(archive)


def test_zip_without_csv_is_not_valid(tmp_path: Path) -> None:
    archive = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    assert not _valid_zip(archive)
