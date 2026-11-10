"""End-to-end demand forecasting experiment and model selection."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from citibike_pipeline.database.connection import get_engine
from citibike_pipeline.ml.data import build_modeling_data
from citibike_pipeline.ml.features import FEATURE_SETS, engineer_features, time_split
from citibike_pipeline.ml.metrics import evaluate
from citibike_pipeline.ml.persistence import persist_forecasts, persist_metric


def _catboost_regressor(
    *,
    iterations: int,
    depth: int,
    learning_rate: float,
    l2_leaf_reg: float,
    random_seed: int,
    thread_count: int,
    verbose: int | bool,
):
    try:
        from catboost import CatBoostRegressor
    except ImportError as exc:
        raise RuntimeError(
            'CatBoost is not installed. Run: pip install -e ".[dev,transform,ml]"'
        ) from exc

    return CatBoostRegressor(
        iterations=int(iterations),
        depth=int(depth),
        learning_rate=float(learning_rate),
        l2_leaf_reg=float(l2_leaf_reg),
        loss_function="RMSE",
        eval_metric="RMSE",
        random_seed=int(random_seed),
        thread_count=int(thread_count),
        verbose=verbose,
        allow_writing_files=False,
        task_type="CPU",
    )


def _fit_ablation(
    split,
    *,
    feature_name: str,
    features: list[str],
    params: dict[str, Any],
    iterations: int,
) -> tuple[Any, dict[str, float], int]:
    model = _catboost_regressor(
        iterations=iterations,
        depth=int(params["depth"]),
        learning_rate=float(params["learning_rate"]),
        l2_leaf_reg=float(params["l2_leaf_reg"]),
        random_seed=int(params["random_seed"]),
        thread_count=int(params["thread_count"]),
        verbose=int(params.get("verbose", 50)),
    )

    train_x = split.train[features].copy()
    validation_x = split.validation[features].copy()
    train_y = split.train["rides_started"].to_numpy(dtype=float)
    validation_y = split.validation["rides_started"].to_numpy(dtype=float)

    model.fit(
        train_x,
        train_y,
        cat_features=["station_id"],
        eval_set=(validation_x, validation_y),
        use_best_model=True,
        early_stopping_rounds=int(params["early_stopping_rounds"]),
    )

    prediction = np.clip(model.predict(validation_x), 0.0, None)
    metrics = evaluate(validation_y, prediction)
    best_iteration = int(getattr(model, "best_iteration_", iterations - 1) or 0) + 1
    best_iteration = max(20, best_iteration)

    return model, metrics, best_iteration


def _artifact_directories(config: dict[str, Any]) -> tuple[Path, Path]:
    base = Path(str(config["project"].get("artifacts_dir", "artifacts")))
    model_dir = base / "models"
    metrics_dir = base / "metrics"
    model_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return model_dir, metrics_dir


def train_forecasting_pipeline(
    config: dict[str, Any],
    *,
    top_stations: int | None = None,
    iterations: int | None = None,
    smoke: bool = False,
    persist: bool = True,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Run baseline, CatBoost ablation, final model and GOLD persistence."""
    db = engine or get_engine()
    cfg = dict(config.get("modeling", {}))
    cat_cfg = dict(cfg.get("catboost", {}))

    requested_stations = int(top_stations or cfg.get("top_stations", 250))
    requested_iterations = int(iterations or cat_cfg.get("iterations", 180))

    if smoke:
        requested_stations = min(requested_stations, 20)
        requested_iterations = min(requested_iterations, 25)
        persist = False

    print(
        f"Building modeling grid: top_stations={requested_stations}, "
        f"iterations={requested_iterations}, smoke={smoke}"
    )

    modeling = build_modeling_data(top_stations=requested_stations, engine=db)
    features = engineer_features(modeling.frame)
    split = time_split(
        features,
        validation_days=int(cfg.get("validation_days", 4)),
        test_days=int(cfg.get("test_days", 5)),
    )

    print(
        "Modeling rows after 168h history requirement: "
        f"{len(features):,}; train={len(split.train):,}; "
        f"validation={len(split.validation):,}; test={len(split.test):,}"
    )
    print(
        f"Coverage: weather={modeling.coverage['weather_percent']:.2f}% "
        f"traffic={modeling.coverage['traffic_percent']:.2f}%"
    )

    trained_at = datetime.now(UTC)
    model_version = trained_at.strftime("%Y%m%dT%H%M%SZ")

    # Seasonal naive: same station and same hour one week earlier.
    baseline_prediction = np.clip(
        split.test["lag_168"].to_numpy(dtype=float),
        0.0,
        None,
    )
    baseline_metrics = evaluate(
        split.test["rides_started"].to_numpy(dtype=float),
        baseline_prediction,
    )

    ablation: dict[str, dict[str, Any]] = {}
    trained_models: dict[str, Any] = {}

    for feature_name, feature_columns in FEATURE_SETS.items():
        print(f"\n==> CatBoost ablation: {feature_name} ({len(feature_columns)} features)")
        model, metrics, best_iteration = _fit_ablation(
            split,
            feature_name=feature_name,
            features=feature_columns,
            params=cat_cfg,
            iterations=requested_iterations,
        )
        trained_models[feature_name] = model
        ablation[feature_name] = {
            **metrics,
            "best_iteration": best_iteration,
            "feature_count": len(feature_columns),
        }
        print(
            f"{feature_name}: MAE={metrics['mae']:.4f} "
            f"RMSE={metrics['rmse']:.4f} WAPE={metrics['wape']:.2f}% "
            f"best_iteration={best_iteration}"
        )

    selected_feature_set = min(
        ablation,
        key=lambda name: (
            float(ablation[name]["wape"])
            if np.isfinite(ablation[name]["wape"])
            else float("inf"),
            float(ablation[name]["rmse"]),
        ),
    )
    selected_features = FEATURE_SETS[selected_feature_set]
    selected_iterations = int(ablation[selected_feature_set]["best_iteration"])

    print(
        f"\nSelected feature set: {selected_feature_set}; "
        f"refit iterations={selected_iterations}"
    )

    train_validation = pd.concat([split.train, split.validation], ignore_index=True)
    final_model = _catboost_regressor(
        iterations=selected_iterations,
        depth=int(cat_cfg["depth"]),
        learning_rate=float(cat_cfg["learning_rate"]),
        l2_leaf_reg=float(cat_cfg["l2_leaf_reg"]),
        random_seed=int(cat_cfg["random_seed"]),
        thread_count=int(cat_cfg["thread_count"]),
        verbose=int(cat_cfg.get("verbose", 50)),
    )
    final_model.fit(
        train_validation[selected_features],
        train_validation["rides_started"].to_numpy(dtype=float),
        cat_features=["station_id"],
    )

    final_prediction = np.clip(
        final_model.predict(split.test[selected_features]),
        0.0,
        None,
    )
    final_metrics = evaluate(
        split.test["rides_started"].to_numpy(dtype=float),
        final_prediction,
    )

    importance = sorted(
        [
            {"feature": name, "importance": float(value)}
            for name, value in zip(
                selected_features,
                final_model.get_feature_importance(),
                strict=True,
            )
        ],
        key=lambda item: item["importance"],
        reverse=True,
    )

    summary: dict[str, Any] = {
        "model_version": model_version,
        "top_stations": requested_stations,
        "raw_grid_rows": int(len(modeling.frame)),
        "modeling_rows": int(len(features)),
        "train_rows": int(len(split.train)),
        "validation_rows": int(len(split.validation)),
        "test_rows": int(len(split.test)),
        "data_from": modeling.min_hour.isoformat(),
        "data_to": modeling.max_hour.isoformat(),
        "validation_from": split.validation_start.isoformat(),
        "test_from": split.test_start.isoformat(),
        "coverage": modeling.coverage,
        "baseline_test": baseline_metrics,
        "ablation_validation": ablation,
        "selected_feature_set": selected_feature_set,
        "selected_iterations": selected_iterations,
        "catboost_test": final_metrics,
        "feature_importance": importance,
        "persisted": bool(persist),
    }

    if persist:
        model_dir, metrics_dir = _artifact_directories(config)
        model_path = model_dir / f"catboost_global_{model_version}.cbm"
        metrics_path = metrics_dir / f"forecast_experiment_{model_version}.json"
        importance_path = metrics_dir / f"feature_importance_{model_version}.csv"

        final_model.save_model(str(model_path))
        pd.DataFrame(importance).to_csv(importance_path, index=False)

        evaluation_from = pd.Timestamp(split.test["observed_hour"].min())
        evaluation_to = pd.Timestamp(split.test["observed_hour"].max())
        validation_from = pd.Timestamp(split.validation["observed_hour"].min())
        validation_to = pd.Timestamp(split.validation["observed_hour"].max())

        persist_metric(
            model_name="seasonal_naive_168h",
            model_version=model_version,
            split_name="test",
            evaluation_from=evaluation_from,
            evaluation_to=evaluation_to,
            metrics=baseline_metrics,
            rows_evaluated=len(split.test),
            engine=db,
        )

        for feature_name, metrics in ablation.items():
            persist_metric(
                model_name=f"catboost_{feature_name}",
                model_version=model_version,
                split_name="validation",
                evaluation_from=validation_from,
                evaluation_to=validation_to,
                metrics=metrics,
                rows_evaluated=len(split.validation),
                engine=db,
            )

        persist_metric(
            model_name="catboost_global",
            model_version=model_version,
            split_name="test",
            evaluation_from=evaluation_from,
            evaluation_to=evaluation_to,
            metrics=final_metrics,
            rows_evaluated=len(split.test),
            engine=db,
        )

        baseline_frame = split.test[
            ["observed_hour", "station_sk", "rides_started"]
        ].copy()
        baseline_frame["prediction"] = baseline_prediction
        baseline_inserted = persist_forecasts(
            baseline_frame,
            model_name="seasonal_naive_168h",
            model_version=model_version,
            trained_at=trained_at,
            feature_set_version="seasonal_168h",
            engine=db,
        )

        final_frame = split.test[
            ["observed_hour", "station_sk", "rides_started"]
        ].copy()
        final_frame["prediction"] = final_prediction
        final_inserted = persist_forecasts(
            final_frame,
            model_name="catboost_global",
            model_version=model_version,
            trained_at=trained_at,
            feature_set_version=selected_feature_set,
            engine=db,
        )

        summary["forecast_rows_persisted"] = {
            "seasonal_naive_168h": int(baseline_inserted),
            "catboost_global": int(final_inserted),
        }
        summary["artifacts"] = {
            "model": str(model_path),
            "metrics": str(metrics_path),
            "feature_importance": str(importance_path),
        }

        metrics_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    print(
        "\nTEST RESULT\n"
        f"Seasonal Naive: MAE={baseline_metrics['mae']:.4f} "
        f"RMSE={baseline_metrics['rmse']:.4f} "
        f"WAPE={baseline_metrics['wape']:.2f}%\n"
        f"CatBoost ({selected_feature_set}): MAE={final_metrics['mae']:.4f} "
        f"RMSE={final_metrics['rmse']:.4f} "
        f"WAPE={final_metrics['wape']:.2f}%"
    )

    return summary
