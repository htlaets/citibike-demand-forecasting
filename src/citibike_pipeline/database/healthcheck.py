"""CLI-style database health check used during local setup and CI."""

from citibike_pipeline.database.connection import database_healthcheck


def main() -> int:
    try:
        ok = database_healthcheck()
    except Exception as exc:
        print(f"[FAIL] PostgreSQL connection failed: {exc}")
        return 1

    if ok:
        print("[OK] PostgreSQL is reachable and SELECT 1 succeeded.")
        return 0

    print("[FAIL] PostgreSQL health check returned an unexpected result.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
