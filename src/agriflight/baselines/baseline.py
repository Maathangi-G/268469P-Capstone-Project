"""Guarded historical-mean baseline for daily coverage (hectares).

The baseline predicts the mean of verified, measured training targets of ONE
target grain. It is deliberately simple: it is the reference any later model
must beat on the same approved observations.

Guards (each raises BaselineInputError with an explanation):
* empty training input;
* missing required columns;
* mixed or unexpected target grains (per-pilot, per-team and per-division
  outcomes do not mean the same thing);
* any record not explicitly verified (target_verified must be True);
* missing targets (missing is not zero - resolve or exclude them upstream);
* non-numeric, non-finite or negative targets.
A verified zero is a valid observation and is kept.

Only the frame passed to ``fit`` affects the mean. Use
``chronological_split`` to keep evaluation-period outcomes out of fitting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

REQUIRED = ("target_grain", "target_ha", "target_verified")


def _is_true(value: object) -> bool:
    return isinstance(value, (bool, np.bool_)) and bool(value)


class BaselineInputError(ValueError):
    """Training or evaluation input violates the baseline's guards."""


def _validate(frame: pd.DataFrame, grain: str, purpose: str) -> pd.Series:
    if frame is None or len(frame) == 0:
        raise BaselineInputError(f"No {purpose} records: the baseline cannot be fitted or evaluated on empty input.")
    missing_cols = [c for c in REQUIRED if c not in frame.columns]
    if missing_cols:
        raise BaselineInputError(f"{purpose} input is missing required column(s): {', '.join(missing_cols)}.")
    grains = set(frame["target_grain"].astype(str))
    if grains != {grain}:
        raise BaselineInputError(
            f"{purpose} input must contain only target grain {grain!r}; found {sorted(grains)}. "
            "Different grains (e.g. per pilot, per team, per division) are not combined.")
    explicit_true = frame["target_verified"].map(_is_true, na_action="ignore").fillna(False).astype(bool)
    if not explicit_true.all():
        raise BaselineInputError(f"{int((~explicit_true).sum())} {purpose} record(s) are not explicitly verified "
                                 "(target_verified must be boolean True; text, 1 or missing are rejected).")
    raw = frame["target_ha"]
    if raw.isna().any():
        raise BaselineInputError(
            f"{int(raw.isna().sum())} {purpose} target(s) are missing. Missing targets are not zero; "
            "resolve or exclude them before fitting.")
    values = pd.to_numeric(raw, errors="coerce")
    if values.isna().any():
        raise BaselineInputError(f"{int(values.isna().sum())} {purpose} target(s) are not numeric.")
    values = values.astype(float)
    if not values.map(math.isfinite).all():
        raise BaselineInputError(f"{int((~values.map(math.isfinite)).sum())} {purpose} target(s) are not finite.")
    if (values < 0).any():
        raise BaselineInputError(f"{int((values < 0).sum())} {purpose} target(s) are negative hectares.")
    return values


@dataclass
class HistoricalMeanBaseline:
    """Mean of verified training targets for one explicitly named grain."""

    target_grain: str
    mean_ha: float | None = field(default=None, init=False)
    n_train: int = field(default=0, init=False)

    def fit(self, train: pd.DataFrame) -> "HistoricalMeanBaseline":
        values = _validate(train, self.target_grain, "training")
        self.mean_ha = float(values.mean())
        self.n_train = len(values)
        return self

    @property
    def is_fitted(self) -> bool:
        return self.mean_ha is not None

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        if not self.is_fitted:
            raise BaselineInputError("Baseline is not fitted.")
        return pd.Series(self.mean_ha, index=frame.index, name="predicted_ha", dtype=float)

    def evaluate(self, test: pd.DataFrame) -> dict[str, float]:
        """MAE/RMSE on held-out verified targets. Test targets never change the fitted mean."""
        if not self.is_fitted:
            raise BaselineInputError("Baseline is not fitted.")
        actual = _validate(test, self.target_grain, "evaluation")
        error = actual - self.mean_ha
        return {"n_test": len(actual), "mae_ha": float(error.abs().mean()),
                "rmse_ha": float(math.sqrt((error ** 2).mean()))}


def chronological_split(frame: pd.DataFrame, date_column: str, cutoff: str | pd.Timestamp
                        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train = dates strictly before ``cutoff``; test = on/after. Undated rows are rejected."""
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    if dates.isna().any():
        raise BaselineInputError(f"{int(dates.isna().sum())} record(s) have no valid {date_column}; "
                                 "they cannot be placed chronologically.")
    cutoff = pd.Timestamp(cutoff)
    return frame[dates < cutoff].reset_index(drop=True), frame[dates >= cutoff].reset_index(drop=True)
