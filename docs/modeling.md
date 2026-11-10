# Demand forecasting

## Target and grain

The target is `rides_started`: the number of rides starting at a station during
one hour.

The GOLD analytical mart is preserved for all stations. The default modeling
experiment uses the 250 busiest stations so the full experiment is reproducible
on a normal student laptop.

A complete `station × hour` grid is created before training. Missing demand
rows become explicit zero-demand observations. This avoids selection bias that
would occur if the model learned only from hours in which at least one trip
existed.

## Leakage control

Historical features are calculated separately per station:

- `lag_1`;
- `lag_24`;
- `lag_168`;
- shifted rolling mean over 3 hours;
- shifted rolling mean over 24 hours;
- shifted rolling mean over 168 hours.

Every rolling statistic is shifted by one hour first. Therefore the target of
the current row never participates in its own feature vector.

The first 168 hours are removed so Seasonal Naive and CatBoost are evaluated on
exactly the same rows.

## Time split

No random shuffle is used.

Default split for a one-month dataset:

- training — oldest observations;
- validation — 4 days immediately before the test set;
- test — final 5 days.

This is a rolling one-hour-ahead evaluation: when forecasting hour `t`, actual
demand through `t-1` is assumed to be available.

## Models

### Seasonal Naive

`prediction(t) = rides_started(t - 168h)`.

This is the mandatory interpretable baseline for weekly seasonality.

### CatBoost

A global CatBoost regressor is trained across multiple stations. `station_id`
is handled as a categorical feature.

Ablation is run in four stages:

1. `history` — station ID, lags and rolling averages;
2. `calendar` — history + calendar/cyclical features;
3. `weather` — calendar + weather;
4. `traffic` — weather + road-traffic conditions.

The feature set with the lowest validation WAPE (RMSE as tie-breaker) is selected.
It is then refit on `train + validation` and evaluated exactly once on the test
period.

## Metrics

The project persists:

- MAE;
- RMSE;
- WAPE.

Metrics are written to `gold.model_metrics`.

Test predictions for Seasonal Naive and the selected CatBoost model are written
to `gold.forecast_results`, enabling direct actual-vs-forecast comparison in
Apache Superset.

## Commands

Install ML dependencies:

```powershell
pip install -e ".[dev,transform,ml]"
```

Fast environment/model smoke test:

```powershell
citibike-pipeline train --smoke
```

Full reproducible experiment:

```powershell
citibike-pipeline train
```

Show persisted metrics:

```powershell
citibike-pipeline model-metrics
```

The final CatBoost binary, experiment JSON and feature-importance CSV are saved
under `artifacts/` and intentionally ignored by Git.
