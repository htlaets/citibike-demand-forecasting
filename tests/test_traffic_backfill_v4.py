from pathlib import Path

def test_historical_backfill_uses_single_daily_page_and_resume_guard() -> None:
    source = Path("src/citibike_pipeline/ingestion/traffic.py").read_text(encoding="utf-8")
    assert "page_size = 50000" in source
    assert "_historical_day_is_complete" in source
    assert "already complete -> skipped" in source
