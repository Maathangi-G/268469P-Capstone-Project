"""Historical-mean baseline tests. All values are fictional; no result here is
a company-model performance figure."""

from __future__ import annotations

import pandas as pd
import pytest

from agriflight.baselines.baseline import BaselineInputError, HistoricalMeanBaseline, chronological_split

GRAIN = "team x work date"


def _frame(values, verified=True, grain=GRAIN, dates=None):
    n = len(values)
    return pd.DataFrame({
        "target_grain": [grain] * n,
        "target_ha": values,
        "target_verified": [verified] * n if not isinstance(verified, list) else verified,
        "target_date": dates or pd.date_range("2030-01-01", periods=n, freq="D"),
    })


def test_mean_of_training_records():
    model = HistoricalMeanBaseline(GRAIN).fit(_frame([100.0, 200.0, 300.0]))
    assert model.mean_ha == 200.0 and model.n_train == 3
    assert model.predict(_frame([1.0, 1.0])).tolist() == [200.0, 200.0]


def test_verified_zero_is_a_valid_target():
    assert HistoricalMeanBaseline(GRAIN).fit(_frame([0.0, 10.0])).mean_ha == 5.0


@pytest.mark.parametrize("frame, message", [
    (_frame([]), "empty"),
    (_frame([1.0, None]), "missing"),
    (_frame([1.0, "abc"]), "not numeric"),
    (_frame([1.0, float("inf")]), "not finite"),
    (_frame([1.0, float("nan")]), "missing"),
    (_frame([1.0, -5.0]), "negative"),
    (_frame([1.0, 2.0], verified=[True, False]), "not explicitly verified"),
    (_frame([1.0, 2.0], verified=["True", "True"]), "not explicitly verified"),
    (_frame([1.0, 2.0], verified=[True, None]), "not explicitly verified"),
])
def test_invalid_training_input_rejected(frame, message):
    with pytest.raises(BaselineInputError, match=message):
        HistoricalMeanBaseline(GRAIN).fit(frame)


def test_missing_column_rejected():
    with pytest.raises(BaselineInputError, match="target_verified"):
        HistoricalMeanBaseline(GRAIN).fit(_frame([1.0]).drop(columns="target_verified"))


def test_mixed_grains_rejected():
    mixed = pd.concat([_frame([1.0]), _frame([2.0], grain="pilot x work date")], ignore_index=True)
    with pytest.raises(BaselineInputError, match="only target grain"):
        HistoricalMeanBaseline(GRAIN).fit(mixed)


def test_test_period_outcomes_do_not_affect_fit():
    frame = _frame([10.0, 20.0, 1000.0, 2000.0])
    train, test = chronological_split(frame, "target_date", "2030-01-03")
    assert train["target_ha"].tolist() == [10.0, 20.0]
    model = HistoricalMeanBaseline(GRAIN).fit(train)
    metrics = model.evaluate(test)
    assert model.mean_ha == 15.0  # unchanged by evaluation
    assert metrics["n_test"] == 2
    assert metrics["mae_ha"] == pytest.approx((985 + 1985) / 2)
    assert metrics["rmse_ha"] == pytest.approx(((985 ** 2 + 1985 ** 2) / 2) ** 0.5)


def test_undated_records_cannot_be_split():
    frame = _frame([1.0, 2.0])
    frame.loc[1, "target_date"] = None
    with pytest.raises(BaselineInputError, match="no valid target_date"):
        chronological_split(frame, "target_date", "2030-01-02")


def test_unfitted_model_cannot_predict_or_evaluate():
    with pytest.raises(BaselineInputError, match="not fitted"):
        HistoricalMeanBaseline(GRAIN).predict(_frame([1.0]))
    with pytest.raises(BaselineInputError, match="not fitted"):
        HistoricalMeanBaseline(GRAIN).evaluate(_frame([1.0]))
