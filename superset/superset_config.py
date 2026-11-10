"""Local Apache Superset configuration for the Citi Bike PAS project."""

from __future__ import annotations

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_METADATA_DB_URI"]

# Local/demo deployment. The project is intentionally run behind Docker Desktop
# on localhost rather than as a public production service.
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = True

# The dashboards query compact GOLD serving views, so a lightweight cache is enough.
CACHE_CONFIG = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
}
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
}

FEATURE_FLAGS = {
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
}

ENABLE_PROXY_FIX = True
ROW_LIMIT = 50000
SQL_MAX_ROW = 100000
SUPERSET_WEBSERVER_TIMEOUT = 120
