FROM apache/airflow:3.4.0-python3.12

WORKDIR /opt/citibike

COPY --chown=airflow:root pyproject.toml README.md /opt/citibike/
COPY --chown=airflow:root src /opt/citibike/src
COPY --chown=airflow:root config /opt/citibike/config
COPY --chown=airflow:root dbt /opt/citibike/dbt
COPY --chown=airflow:root airflow /opt/citibike/airflow

# Keep Airflow pinned to the exact version shipped by the base image while
# installing the project and dbt dependencies.
RUN pip install --no-cache-dir \
    "apache-airflow==3.4.0" \
    ".[transform]"

ENV CITIBIKE_PROJECT_ROOT=/opt/citibike
ENV PIPELINE_CONFIG=/opt/citibike/config/config.yaml
