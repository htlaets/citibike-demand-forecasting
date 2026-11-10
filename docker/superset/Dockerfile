FROM apache/superset:6.0.0

USER root

# Superset 6.0.0's plain/lean image intentionally contains no database
# drivers. PostgreSQL is used both for Superset metadata and the Citi Bike
# warehouse, so bake the DB-API driver into a small derived image.
RUN . /app/.venv/bin/activate && \
    uv pip install --no-cache psycopg2-binary

USER superset
