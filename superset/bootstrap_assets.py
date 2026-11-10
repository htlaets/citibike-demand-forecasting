"""Idempotently bootstrap the two project dashboards in Apache Superset 6.0."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import text
from superset.app import create_app


DATABASE_NAME = "Citi Bike Warehouse"


COLUMN_VERBOSE_NAMES = {
    "observed_hour": "Дата и час",
    "forecast_for": "Дата и час прогноза",
    "station_id": "ID станции",
    "station_name": "Станция",
    "rides_started": "Начатые поездки",
    "rides_ended": "Завершённые поездки",
    "temperature_2m": "Температура, °C",
    "relative_humidity_2m": "Относительная влажность, %",
    "precipitation": "Осадки, мм",
    "wind_speed_10m": "Скорость ветра, м/с",
    "avg_traffic_speed": "Средняя скорость движения",
    "avg_travel_time": "Среднее время в пути",
    "actual": "Фактический спрос",
    "prediction": "Прогноз",
    "absolute_error": "Абсолютная ошибка",
    "model_name": "Модель",
    "split_name": "Выборка",
    "mae": "MAE",
    "rmse": "RMSE",
    "wape": "WAPE, %",
    "rows_evaluated": "Число наблюдений",
    "evaluated_at": "Время оценки",
    "catboost_wape": "WAPE CatBoost, %",
    "baseline_wape": "WAPE базовой модели, %",
    "wape_improvement_percent": "Улучшение WAPE, %",
    "successful_loads": "Успешные загрузки",
    "failed_loads": "Неуспешные загрузки",
    "rows_inserted": "Загружено строк",
    "rows_rejected": "Отклонено строк",
    "load_id": "ID загрузки",
    "source_name": "Источник",
    "pipeline_name": "Конвейер",
    "started_at": "Время начала",
    "finished_at": "Время завершения",
    "status": "Статус",
    "rows_received": "Получено строк",
    "rows_updated": "Обновлено строк",
    "retry_count": "Повторные попытки",
    "error_type": "Тип ошибки",
    "error_message": "Сообщение об ошибке",
    "duration_seconds": "Длительность, с",
    "dataset_name": "Набор данных",
    "check_type": "Тип проверки",
    "check_name": "Проверка",
    "rows_checked": "Проверено строк",
    "failed_rows": "Строк с ошибками",
    "checked_at": "Время проверки",
    "details": "Описание",
    "checks": "Количество проверок",
}


LEGACY_CHART_NAMES = {
    "Всего начатых поездок": "Total rides started",
    "WAPE модели CatBoost на тесте": "CatBoost test WAPE",
    "Фактический спрос и прогноз CatBoost": "Actual vs CatBoost forecast",
    "Топ станций по числу начатых поездок": "Top stations by rides started",
    "Динамика спроса и дорожной ситуации": "Demand and traffic over time",
    "Сравнение качества моделей": "Model evaluation table",
    "Успешные запуски загрузки данных": "Successful ingestion runs",
    "Неуспешные запуски загрузки данных": "Failed ingestion runs",
    "Загруженные строки по источникам": "Rows inserted by source",
    "Длительность загрузки по источникам": "Pipeline duration by source",
    "Ошибки качества данных по типам проверок": "DQ failed rows by check type",
    "Последние запуски конвейера": "Recent pipeline runs",
    "Результаты контроля качества данных": "Data quality results",
}



SERVING_SQL = """
CREATE OR REPLACE VIEW gold.superset_hourly_demand AS
SELECT
    observed_hour,
    SUM(rides_started)::BIGINT AS rides_started,
    SUM(rides_ended)::BIGINT AS rides_ended,
    AVG(temperature_2m) AS temperature_2m,
    AVG(relative_humidity_2m) AS relative_humidity_2m,
    AVG(precipitation) AS precipitation,
    AVG(wind_speed_10m) AS wind_speed_10m,
    AVG(avg_traffic_speed) AS avg_traffic_speed,
    AVG(avg_travel_time) AS avg_travel_time
FROM gold.station_hourly_demand
GROUP BY observed_hour;

CREATE OR REPLACE VIEW gold.superset_top_stations AS
SELECT
    station_id,
    station_name,
    SUM(rides_started)::BIGINT AS rides_started,
    SUM(rides_ended)::BIGINT AS rides_ended
FROM gold.station_hourly_demand
GROUP BY station_id, station_name;

CREATE OR REPLACE VIEW gold.superset_forecast_comparison AS
WITH latest AS (
    SELECT model_version
    FROM gold.model_metrics
    WHERE model_name = 'catboost_global'
      AND split_name = 'test'
    ORDER BY evaluated_at DESC
    LIMIT 1
)
SELECT
    f.forecast_for,
    SUM(f.actual) AS actual,
    SUM(f.prediction) AS prediction,
    SUM(ABS(f.actual - f.prediction)) AS absolute_error
FROM gold.forecast_results AS f
JOIN latest AS l USING (model_version)
WHERE f.model_name = 'catboost_global'
GROUP BY f.forecast_for;

CREATE OR REPLACE VIEW gold.superset_model_metrics AS
WITH latest AS (
    SELECT model_version
    FROM gold.model_metrics
    ORDER BY evaluated_at DESC
    LIMIT 1
)
SELECT
    CASE m.model_name
        WHEN 'seasonal_naive_168h' THEN 'Сезонная наивная модель (168 ч)'
        WHEN 'catboost_history' THEN 'CatBoost: история спроса'
        WHEN 'catboost_calendar' THEN 'CatBoost: + календарные признаки'
        WHEN 'catboost_weather' THEN 'CatBoost: + погода'
        WHEN 'catboost_traffic' THEN 'CatBoost: + дорожная ситуация'
        WHEN 'catboost_global' THEN 'Итоговая модель CatBoost'
        ELSE m.model_name
    END AS model_name,
    CASE m.split_name
        WHEN 'test' THEN 'Тестовая'
        WHEN 'validation' THEN 'Валидационная'
        WHEN 'train' THEN 'Обучающая'
        ELSE m.split_name
    END AS split_name,
    m.mae,
    m.rmse,
    m.wape,
    m.rows_evaluated,
    m.evaluated_at
FROM gold.model_metrics AS m
JOIN latest AS l USING (model_version);

CREATE OR REPLACE VIEW gold.superset_model_kpi AS
WITH latest AS (
    SELECT model_version
    FROM gold.model_metrics
    ORDER BY evaluated_at DESC
    LIMIT 1
),
metrics AS (
    SELECT m.*
    FROM gold.model_metrics m
    JOIN latest l USING (model_version)
)
SELECT
    MAX(wape) FILTER (
        WHERE model_name = 'catboost_global' AND split_name = 'test'
    ) AS catboost_wape,
    MAX(wape) FILTER (
        WHERE model_name = 'seasonal_naive_168h' AND split_name = 'test'
    ) AS baseline_wape,
    CASE
        WHEN MAX(wape) FILTER (
            WHERE model_name = 'seasonal_naive_168h' AND split_name = 'test'
        ) > 0
        THEN 100.0 * (
            1.0 -
            MAX(wape) FILTER (
                WHERE model_name = 'catboost_global' AND split_name = 'test'
            )
            /
            MAX(wape) FILTER (
                WHERE model_name = 'seasonal_naive_168h' AND split_name = 'test'
            )
        )
    END AS wape_improvement_percent
FROM metrics;


CREATE OR REPLACE VIEW gold.superset_pipeline_monitoring AS
SELECT
    load_id,
    CASE source_name
        WHEN 'citibike_trips' THEN 'Поездки Citi Bike'
        WHEN 'citibike_gbfs' THEN 'Станции Citi Bike (GBFS)'
        WHEN 'weather' THEN 'Погода'
        WHEN 'traffic' THEN 'Дорожная ситуация'
        ELSE source_name
    END AS source_name,
    pipeline_name,
    started_at,
    finished_at,
    CASE status
        WHEN 'SUCCESS' THEN 'Успешно'
        WHEN 'FAILED' THEN 'Ошибка'
        WHEN 'RUNNING' THEN 'Выполняется'
        WHEN 'SKIPPED' THEN 'Пропущено'
        WHEN 'PARTIAL' THEN 'Частично'
        ELSE status
    END AS status,
    rows_received,
    rows_inserted,
    rows_updated,
    rows_rejected,
    retry_count,
    error_type,
    error_message,
    duration_seconds
FROM gold.pipeline_monitoring;

CREATE OR REPLACE VIEW gold.superset_dq_monitoring AS
SELECT
    CASE source_name
        WHEN 'citibike_trips' THEN 'Поездки Citi Bike'
        WHEN 'citibike_gbfs' THEN 'Станции Citi Bike (GBFS)'
        WHEN 'weather' THEN 'Погода'
        WHEN 'traffic' THEN 'Дорожная ситуация'
        ELSE source_name
    END AS source_name,
    dataset_name,
    CASE check_type
        WHEN 'COMPLETENESS' THEN 'Полнота'
        WHEN 'UNIQUENESS' THEN 'Уникальность'
        WHEN 'VALIDITY' THEN 'Корректность'
        WHEN 'TYPE' THEN 'Типы данных'
        WHEN 'RANGE' THEN 'Допустимые диапазоны'
        WHEN 'REFERENTIAL_INTEGRITY' THEN 'Ссылочная целостность'
        WHEN 'FRESHNESS' THEN 'Актуальность'
        ELSE check_type
    END AS check_type,
    check_name,
    CASE status
        WHEN 'PASS' THEN 'Успешно'
        WHEN 'WARN' THEN 'Предупреждение'
        WHEN 'FAIL' THEN 'Ошибка'
        ELSE status
    END AS status,
    rows_checked,
    failed_rows,
    checked_at,
    details
FROM gold.dq_monitoring;

CREATE OR REPLACE VIEW gold.superset_pipeline_kpi AS
SELECT
    COUNT(*) FILTER (WHERE status = 'SUCCESS')::BIGINT AS successful_loads,
    COUNT(*) FILTER (WHERE status = 'FAILED')::BIGINT AS failed_loads,
    COALESCE(SUM(rows_inserted), 0)::BIGINT AS rows_inserted,
    COALESCE(SUM(rows_rejected), 0)::BIGINT AS rows_rejected
FROM gold.pipeline_monitoring;

CREATE OR REPLACE VIEW gold.superset_dq_summary AS
SELECT
    CASE check_type
        WHEN 'COMPLETENESS' THEN 'Полнота'
        WHEN 'UNIQUENESS' THEN 'Уникальность'
        WHEN 'VALIDITY' THEN 'Корректность'
        WHEN 'TYPE' THEN 'Типы данных'
        WHEN 'RANGE' THEN 'Допустимые диапазоны'
        WHEN 'REFERENTIAL_INTEGRITY' THEN 'Ссылочная целостность'
        WHEN 'FRESHNESS' THEN 'Актуальность'
        ELSE check_type
    END AS check_type,
    CASE status
        WHEN 'PASS' THEN 'Успешно'
        WHEN 'WARN' THEN 'Предупреждение'
        WHEN 'FAIL' THEN 'Ошибка'
        ELSE status
    END AS status,
    COUNT(*)::BIGINT AS checks,
    COALESCE(SUM(failed_rows), 0)::BIGINT AS failed_rows
FROM gold.dq_monitoring
GROUP BY check_type, status;
"""


def _metric(sql_expression: str, label: str) -> dict[str, Any]:
    return {
        "expressionType": "SQL",
        "sqlExpression": sql_expression,
        "label": label,
        "hasCustomLabel": True,
    }


def _params(dataset: SqlaTable, viz_type: str, **kwargs: Any) -> str:
    value = {
        "datasource": f"{dataset.id}__table",
        "viz_type": viz_type,
        "adhoc_filters": [],
        "row_limit": 10000,
        "color_scheme": "supersetColors",
    }
    value.update(kwargs)
    return json.dumps(value)


def _database_uri() -> str:
    user = quote_plus(os.environ["CITIBIKE_DB_USER"])
    password = quote_plus(os.environ["CITIBIKE_DB_PASSWORD"])
    host = os.environ["CITIBIKE_DB_HOST"]
    port = os.environ["CITIBIKE_DB_PORT"]
    database = quote_plus(os.environ["CITIBIKE_DB_NAME"])
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def ensure_database() -> Database:
    database = db.session.query(Database).filter_by(database_name=DATABASE_NAME).one_or_none()
    uri = _database_uri()

    if database is None:
        database = Database(
            database_name=DATABASE_NAME,
            expose_in_sqllab=True,
            allow_dml=False,
            allow_ctas=False,
            allow_cvas=False,
        )
        db.session.add(database)

    database.set_sqlalchemy_uri(uri)
    database.expose_in_sqllab = True
    db.session.commit()
    return database


def ensure_serving_views(database: Database) -> None:
    # Superset 6 exposes get_sqla_engine() as a context manager so SSH/OAuth
    # resources and the private engine can be cleaned up correctly.
    with database.get_sqla_engine() as engine:
        with engine.begin() as connection:
            for statement in SERVING_SQL.split(";"):
                sql = statement.strip()
                if sql:
                    connection.execute(text(sql))


def ensure_dataset(database: Database, table_name: str) -> SqlaTable:
    dataset = (
        db.session.query(SqlaTable)
        .filter_by(
            database_id=database.id,
            schema="gold",
            table_name=table_name,
        )
        .one_or_none()
    )
    if dataset is None:
        dataset = SqlaTable(
            database=database,
            schema="gold",
            table_name=table_name,
        )
        db.session.add(dataset)
        db.session.flush()

    # Re-sync columns on every bootstrap so an evolved serving view is reflected.
    dataset.fetch_metadata()

    # Russian labels are UI metadata only; physical warehouse column names stay stable.
    for column in dataset.columns:
        russian_name = COLUMN_VERBOSE_NAMES.get(column.column_name)
        if russian_name:
            column.verbose_name = russian_name

    db.session.commit()
    return dataset


def ensure_chart(
    *,
    name: str,
    dataset: SqlaTable,
    viz_type: str,
    params: str,
    description: str,
) -> Slice:
    chart = db.session.query(Slice).filter_by(slice_name=name).one_or_none()
    if chart is None:
        legacy_name = LEGACY_CHART_NAMES.get(name)
        if legacy_name:
            chart = db.session.query(Slice).filter_by(slice_name=legacy_name).one_or_none()

    if chart is None:
        chart = Slice(slice_name=name)
        db.session.add(chart)

    chart.slice_name = name
    chart.datasource_id = dataset.id
    chart.datasource_type = "table"
    chart.datasource_name = f"{dataset.schema}.{dataset.table_name}"
    chart.viz_type = viz_type
    chart.params = params
    chart.description = description
    chart.cache_timeout = 300
    db.session.commit()
    return chart


def _layout(title: str, charts: list[Slice]) -> str:
    layout: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {
            "children": ["GRID_ID"],
            "id": "ROOT_ID",
            "type": "ROOT",
        },
        "GRID_ID": {
            "children": [],
            "id": "GRID_ID",
            "parents": ["ROOT_ID"],
            "type": "GRID",
        },
        "HEADER_ID": {
            "id": "HEADER_ID",
            "meta": {"text": title},
            "type": "HEADER",
        },
    }

    row_ids: list[str] = []
    for row_index in range(0, len(charts), 2):
        row_id = f"ROW-{row_index // 2 + 1}"
        row_ids.append(row_id)
        row_charts = charts[row_index : row_index + 2]
        chart_ids: list[str] = []

        for chart in row_charts:
            chart_key = f"CHART-{chart.id}"
            chart_ids.append(chart_key)
            width = 12 if len(row_charts) == 1 else 6
            layout[chart_key] = {
                "children": [],
                "id": chart_key,
                "meta": {
                    "chartId": chart.id,
                    "height": 48,
                    "sliceName": chart.slice_name,
                    "uuid": str(chart.uuid),
                    "width": width,
                },
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "type": "CHART",
            }

        layout[row_id] = {
            "children": chart_ids,
            "id": row_id,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "parents": ["ROOT_ID", "GRID_ID"],
            "type": "ROW",
        }

    layout["GRID_ID"]["children"] = row_ids
    return json.dumps(layout)


def ensure_dashboard(
    *,
    title: str,
    slug: str,
    description: str,
    charts: list[Slice],
    owner: Any,
) -> Dashboard:
    dashboard = db.session.query(Dashboard).filter_by(slug=slug).one_or_none()
    if dashboard is None:
        dashboard = Dashboard(slug=slug)
        db.session.add(dashboard)

    dashboard.dashboard_title = title
    dashboard.description = description
    dashboard.published = True
    dashboard.slices = charts
    dashboard.position_json = _layout(title, charts)
    dashboard.json_metadata = json.dumps(
        {
            "filter_scopes": {},
            "expanded_slices": {},
            "refresh_frequency": 0,
            "timed_refresh_immune_slices": [],
            "color_scheme": "supersetColors",
            "label_colors": {},
            "shared_label_colors": {},
            "cross_filters_enabled": True,
            "native_filter_configuration": [],
            "global_chart_configuration": {
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []}
            },
            "chart_configuration": {},
        }
    )
    if owner is not None:
        dashboard.owners = [owner]
    db.session.commit()
    return dashboard


def main() -> None:
    # Superset 6 model classes use extensions (including encrypted fields)
    # that are initialized by create_app(). Import ORM models only after the
    # Flask application context exists. This mirrors Superset's own Docker
    # initialization pattern.
    app = create_app()
    with app.app_context():
        global db, security_manager, Database, Dashboard, Slice, SqlaTable

        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.extensions import security_manager
        from superset.models.core import Database
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        database = ensure_database()
        ensure_serving_views(database)

        dataset_names = [
            "superset_hourly_demand",
            "superset_top_stations",
            "superset_forecast_comparison",
            "superset_model_metrics",
            "superset_model_kpi",
            "superset_pipeline_monitoring",
            "superset_pipeline_kpi",
            "superset_dq_monitoring",
            "superset_dq_summary",
        ]
        datasets = {
            name: ensure_dataset(database, name)
            for name in dataset_names
        }

        demand_charts = [
            ensure_chart(
                name="Всего начатых поездок",
                dataset=datasets["superset_hourly_demand"],
                viz_type="big_number_total",
                params=_params(
                    datasets["superset_hourly_demand"],
                    "big_number_total",
                    metric=_metric("SUM(rides_started)", "Начатые поездки"),
                    y_axis_format="SMART_NUMBER",
                    header_font_size=0.45,
                ),
                description="Общее количество поездок Citi Bike, представленных в аналитической витрине.",
            ),
            ensure_chart(
                name="WAPE модели CatBoost на тесте",
                dataset=datasets["superset_model_kpi"],
                viz_type="big_number_total",
                params=_params(
                    datasets["superset_model_kpi"],
                    "big_number_total",
                    metric=_metric("MAX(catboost_wape)", "WAPE CatBoost"),
                    y_axis_format=".2f",
                    header_font_size=0.45,
                ),
                description="Итоговая ошибка WAPE модели CatBoost на хронологическом тестовом интервале. Чем меньше значение, тем точнее прогноз.",
            ),
            ensure_chart(
                name="Фактический спрос и прогноз CatBoost",
                dataset=datasets["superset_forecast_comparison"],
                viz_type="echarts_timeseries_line",
                params=_params(
                    datasets["superset_forecast_comparison"],
                    "echarts_timeseries_line",
                    x_axis="forecast_for",
                    time_grain_sqla="PT1H",
                    metrics=[
                        _metric("SUM(actual)", "Фактический спрос"),
                        _metric("SUM(prediction)", "Прогноз"),
                    ],
                    groupby=[],
                    show_legend=True,
                    legendType="scroll",
                    rich_tooltip=True,
                    x_axis_time_format="smart_date",
                    y_axis_format="SMART_NUMBER",
                ),
                description="Сравнение фактического почасового спроса и итогового прогноза CatBoost.",
            ),
            ensure_chart(
                name="Топ станций по числу начатых поездок",
                dataset=datasets["superset_top_stations"],
                viz_type="echarts_timeseries_bar",
                params=_params(
                    datasets["superset_top_stations"],
                    "echarts_timeseries_bar",
                    x_axis="station_name",
                    metrics=[_metric("SUM(rides_started)", "Начатые поездки")],
                    groupby=[],
                    row_limit=15,
                    series_limit=15,
                    order_desc=True,
                    orientation="horizontal",
                    show_legend=False,
                    y_axis_format="SMART_NUMBER",
                ),
                description="Станции Citi Bike с наибольшим спросом за анализируемый период.",
            ),
            ensure_chart(
                name="Динамика спроса и дорожной ситуации",
                dataset=datasets["superset_hourly_demand"],
                viz_type="echarts_timeseries_line",
                params=_params(
                    datasets["superset_hourly_demand"],
                    "echarts_timeseries_line",
                    x_axis="observed_hour",
                    time_grain_sqla="PT1H",
                    metrics=[
                        _metric("SUM(rides_started)", "Начатые поездки"),
                        _metric("AVG(avg_traffic_speed)", "Средняя скорость движения"),
                    ],
                    groupby=[],
                    show_legend=True,
                    rich_tooltip=True,
                    y_axis_format="SMART_NUMBER",
                ),
                description="Почасовая динамика спроса совместно с показателем средней скорости дорожного движения NYC DOT.",
            ),
            ensure_chart(
                name="Сравнение качества моделей",
                dataset=datasets["superset_model_metrics"],
                viz_type="table",
                params=_params(
                    datasets["superset_model_metrics"],
                    "table",
                    query_mode="raw",
                    all_columns=[
                        "model_name",
                        "split_name",
                        "mae",
                        "rmse",
                        "wape",
                        "rows_evaluated",
                    ],
                    order_by_cols=[],
                    row_limit=20,
                    server_pagination=False,
                ),
                description="Метрики MAE, RMSE и WAPE для базовой модели, абляционных экспериментов и итоговой модели.",
            ),
        ]

        operations_charts = [
            ensure_chart(
                name="Успешные запуски загрузки данных",
                dataset=datasets["superset_pipeline_kpi"],
                viz_type="big_number_total",
                params=_params(
                    datasets["superset_pipeline_kpi"],
                    "big_number_total",
                    metric=_metric("MAX(successful_loads)", "Успешные загрузки"),
                    y_axis_format="SMART_NUMBER",
                    header_font_size=0.45,
                ),
                description="Количество успешно завершённых запусков загрузки данных из внешних источников.",
            ),
            ensure_chart(
                name="Неуспешные запуски загрузки данных",
                dataset=datasets["superset_pipeline_kpi"],
                viz_type="big_number_total",
                params=_params(
                    datasets["superset_pipeline_kpi"],
                    "big_number_total",
                    metric=_metric("MAX(failed_loads)", "Неуспешные загрузки"),
                    y_axis_format="SMART_NUMBER",
                    header_font_size=0.45,
                ),
                description="Количество завершившихся ошибкой запусков загрузки данных.",
            ),
            ensure_chart(
                name="Загруженные строки по источникам",
                dataset=datasets["superset_pipeline_monitoring"],
                viz_type="echarts_timeseries_bar",
                params=_params(
                    datasets["superset_pipeline_monitoring"],
                    "echarts_timeseries_bar",
                    x_axis="source_name",
                    metrics=[_metric("SUM(rows_inserted)", "Загружено строк")],
                    groupby=[],
                    order_desc=True,
                    show_legend=False,
                    y_axis_format="SMART_NUMBER",
                ),
                description="Объём успешно загруженных данных в разрезе внешних источников.",
            ),
            ensure_chart(
                name="Длительность загрузки по источникам",
                dataset=datasets["superset_pipeline_monitoring"],
                viz_type="echarts_timeseries_line",
                params=_params(
                    datasets["superset_pipeline_monitoring"],
                    "echarts_timeseries_line",
                    x_axis="started_at",
                    time_grain_sqla="PT1H",
                    metrics=[_metric("AVG(duration_seconds)", "Средняя длительность, с")],
                    groupby=["source_name"],
                    show_legend=True,
                    rich_tooltip=True,
                    y_axis_format=".1f",
                ),
                description="Динамика длительности выполнения загрузки данных по каждому источнику.",
            ),
            ensure_chart(
                name="Ошибки качества данных по типам проверок",
                dataset=datasets["superset_dq_summary"],
                viz_type="echarts_timeseries_bar",
                params=_params(
                    datasets["superset_dq_summary"],
                    "echarts_timeseries_bar",
                    x_axis="check_type",
                    metrics=[_metric("SUM(failed_rows)", "Строк с ошибками")],
                    groupby=["status"],
                    order_desc=True,
                    show_legend=True,
                    y_axis_format="SMART_NUMBER",
                ),
                description="Количество строк с ошибками по каждой из семи категорий контроля качества данных.",
            ),
            ensure_chart(
                name="Последние запуски конвейера",
                dataset=datasets["superset_pipeline_monitoring"],
                viz_type="table",
                params=_params(
                    datasets["superset_pipeline_monitoring"],
                    "table",
                    query_mode="raw",
                    all_columns=[
                        "load_id",
                        "source_name",
                        "started_at",
                        "finished_at",
                        "status",
                        "rows_received",
                        "rows_inserted",
                        "rows_rejected",
                        "duration_seconds",
                    ],
                    order_by_cols=[],
                    row_limit=100,
                    server_pagination=False,
                ),
                description="Журнал последних запусков конвейера загрузки и обработки данных.",
            ),
            ensure_chart(
                name="Результаты контроля качества данных",
                dataset=datasets["superset_dq_monitoring"],
                viz_type="table",
                params=_params(
                    datasets["superset_dq_monitoring"],
                    "table",
                    query_mode="raw",
                    all_columns=[
                        "source_name",
                        "dataset_name",
                        "check_type",
                        "check_name",
                        "status",
                        "rows_checked",
                        "failed_rows",
                        "checked_at",
                    ],
                    order_by_cols=[],
                    row_limit=100,
                    server_pagination=False,
                ),
                description="Сохранённые результаты проверок качества данных по всем обязательным категориям.",
            ),
        ]

        admin_username = os.environ.get("SUPERSET_ADMIN_USERNAME", "admin")
        owner = (
            db.session.query(security_manager.user_model)
            .filter_by(username=admin_username)
            .one_or_none()
        )

        demand_dashboard = ensure_dashboard(
            title="Citi Bike — Спрос и прогноз",
            slug="citibike-demand-forecast",
            description=(
                "Аналитическая панель динамики спроса, итогового прогноза CatBoost, "
                "концентрации спроса по станциям и дорожной ситуации."
            ),
            charts=demand_charts,
            owner=owner,
        )
        operations_dashboard = ensure_dashboard(
            title="Citi Bike — Мониторинг платформы данных",
            slug="citibike-platform-operations",
            description=(
                "Операционная панель состояния загрузки данных, объёмов, длительности выполнения "
                "и всех семи категорий контроля качества данных."
            ),
            charts=operations_charts,
            owner=owner,
        )

        print(
            json.dumps(
                {
                    "database_id": database.id,
                    "datasets": {name: dataset.id for name, dataset in datasets.items()},
                    "demand_dashboard": {
                        "id": demand_dashboard.id,
                        "slug": demand_dashboard.slug,
                        "charts": len(demand_charts),
                    },
                    "operations_dashboard": {
                        "id": operations_dashboard.id,
                        "slug": operations_dashboard.slug,
                        "charts": len(operations_charts),
                    },
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
