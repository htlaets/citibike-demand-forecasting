#!/usr/bin/env bash
set -euo pipefail

echo "==> Migrating Superset metadata database"
superset db upgrade

echo "==> Creating/updating admin account"
superset fab create-admin \
  --username "${SUPERSET_ADMIN_USERNAME}" \
  --firstname "Citi" \
  --lastname "Bike Admin" \
  --email "${SUPERSET_ADMIN_EMAIL}" \
  --password "${SUPERSET_ADMIN_PASSWORD}" \
  || true

echo "==> Initializing roles and permissions"
superset init

echo "==> Creating Citi Bike datasets, charts and dashboards"
python /app/pythonpath/bootstrap_assets.py

echo "==> Superset bootstrap complete"
