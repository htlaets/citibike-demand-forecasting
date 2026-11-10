# Ingestion architecture

The ingestion layer implements four source pipelines:

1. **Citi Bike Trip Histories** — monthly ZIP/CSV archives. `ride_id` is the
   idempotency key and the monthly watermark is stored in `meta.etl_watermark`.
2. **Citi Bike GBFS** — station information and station status REST/JSON feeds.
   Feed timestamps make snapshot inserts idempotent.
3. **Open-Meteo Historical Weather** — hourly REST/JSON data. `observed_at` is
   the idempotency key and the completed date is the watermark.
4. **NYC DOT Traffic Speeds** — paginated Socrata REST/JSON data.
   `(link_id, data_as_of)` is the idempotency key; the latest timestamp is the
   watermark.

Every source writes one record per attempt to `meta.etl_load_log`. A watermark
is advanced only after the database transaction has succeeded. HTTP requests
use timeouts, retry/backoff and explicit handling for rate-limit/server errors.

## Smoke-test commands

```powershell
citibike-pipeline ingest --source citibike_gbfs
citibike-pipeline ingest --source weather --start-date 2026-09-01 --end-date 2026-09-02
citibike-pipeline ingest --source traffic --traffic-since-hours 1
citibike-pipeline ingest --source citibike_trips --start-month 2026-09 --end-month 2026-09
citibike-pipeline watermarks
```

Running the same commands again should not create duplicate business records.
The second run still creates a new load-log entry, which is intentional because
the journal records every execution attempt.
