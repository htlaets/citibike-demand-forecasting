"""Smoke-check the assets created by bootstrap_assets.py."""

from __future__ import annotations

from superset.app import create_app


EXPECTED_DASHBOARDS = {
    "citibike-demand-forecast": 6,
    "citibike-platform-operations": 7,
}


def main() -> None:
    # Superset ORM models must be imported only after create_app() initializes
    # encrypted fields and the rest of the Flask extensions.
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        for slug, expected_charts in EXPECTED_DASHBOARDS.items():
            dashboard = db.session.query(Dashboard).filter_by(slug=slug).one_or_none()
            assert dashboard is not None, f"Missing dashboard: {slug}"
            expected_title = {
                "citibike-demand-forecast": "Citi Bike — Спрос и прогноз",
                "citibike-platform-operations": "Citi Bike — Мониторинг платформы данных",
            }[slug]
            assert dashboard.dashboard_title == expected_title, (
                f"{slug}: expected Russian title {expected_title!r}, "
                f"got {dashboard.dashboard_title!r}"
            )
            assert len(dashboard.slices) == expected_charts, (
                f"{slug}: expected {expected_charts} charts, got {len(dashboard.slices)}"
            )
            print(
                f"[OK] {dashboard.dashboard_title}: "
                f"id={dashboard.id} charts={len(dashboard.slices)} published={dashboard.published}"
            )

        expected_chart_count = sum(EXPECTED_DASHBOARDS.values())
        names = [
            "Всего начатых поездок",
            "WAPE модели CatBoost на тесте",
            "Фактический спрос и прогноз CatBoost",
            "Топ станций по числу начатых поездок",
            "Динамика спроса и дорожной ситуации",
            "Сравнение качества моделей",
            "Успешные запуски загрузки данных",
            "Неуспешные запуски загрузки данных",
            "Загруженные строки по источникам",
            "Длительность загрузки по источникам",
            "Ошибки качества данных по типам проверок",
            "Последние запуски конвейера",
            "Результаты контроля качества данных",
        ]
        count = db.session.query(Slice).filter(Slice.slice_name.in_(names)).count()
        assert count == expected_chart_count, (
            f"Expected {expected_chart_count} project charts, got {count}"
        )
        print(f"[OK] project charts: {count}")


if __name__ == "__main__":
    main()
