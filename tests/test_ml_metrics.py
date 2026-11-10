import math

from citibike_pipeline.ml.metrics import evaluate, mae, rmse, wape


def test_metrics_known_values() -> None:
    actual = [0, 2, 4]
    predicted = [1, 2, 2]

    assert mae(actual, predicted) == 1.0
    assert math.isclose(rmse(actual, predicted), math.sqrt(5 / 3), rel_tol=1e-12)
    assert math.isclose(wape(actual, predicted), 50.0, rel_tol=1e-12)
    result = evaluate(actual, predicted)
    assert set(result) == {"mae", "rmse", "wape"}


def test_wape_zero_denominator_is_nan() -> None:
    assert math.isnan(wape([0, 0], [0, 1]))
