# Data quality, quarantine and schema management

The project implements every data-quality category required by the course methodology.

| Type | Example |
|---|---|
| Completeness | required timestamps, station IDs, weather and traffic measures |
| Uniqueness | `ride_id`, weather timestamp, `(link_id, data_as_of)` |
| Validity | positive, plausible trip duration; non-negative GBFS availability |
| Type | PostgreSQL physical types of analytics-critical Citi Bike columns |
| Range | coordinates, weather measures, traffic speed/travel time |
| Referential integrity | GBFS station status resolves to station information |
| Freshness | source-specific SLA against latest RAW event |

Every execution writes its results to `meta.dq_results`.

## Bad-data behavior

RAW is immutable from the DQ perspective. Records that cannot safely participate in
downstream analytics are copied to `quarantine.rejected_records` with:

- source and dataset;
- natural key;
- rejection reason;
- failed check categories;
- a JSON representation of the relevant source values;
- rejection timestamp.

The original RAW record remains available for auditability.

Run:

```bash
citibike-pipeline dq --dataset all --quarantine
```

## Schema drift

`citibike-pipeline schema-check` snapshots the physical schema of managed RAW tables.

The first run registers version 1 in `meta.schema_registry`. Later runs compare the
current schema with the registered version. Additive changes are recorded as compatible.
Removed columns or type/nullability changes are marked as breaking and written to
`meta.schema_changes`.

This provides explicit schema-evolution history instead of silently accepting drift.
