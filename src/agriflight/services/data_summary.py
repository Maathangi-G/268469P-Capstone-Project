"""Descriptive summaries of a loaded operations table.

Counts here are counts of *source records* (rows). They are never labelled or
combined as completed flights or completed services: planned visits, capture
observations and trial visits are always summarised separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from agriflight.data.loader import is_blank, parse_typed_columns
from agriflight.data.schema import (
    ALLOWED_RECORD_TYPES,
    DATE_COLUMNS,
    FIELDS,
    SOURCE_ROW_COLUMN,
)

_POLICY = {spec.name: spec.value_policy for spec in FIELDS}


@dataclass(frozen=True)
class DatasetSummary:
    source_record_count: int
    distinct_operating_units: int
    distinct_clients: int
    record_type_counts: pd.DataFrame
    date_ranges: pd.DataFrame


def record_type_counts(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows per record_type. Documented types are always listed (even at 0);
    undocumented values and blanks are listed separately, never merged."""
    columns = ["record_type", "source_records", "documented_type"]
    if "record_type" not in frame.columns:
        return pd.DataFrame(columns=columns)
    values = frame["record_type"].astype(str).str.strip().replace("", "(blank)")
    counts = values.value_counts()
    rows = [(t, int(counts.get(t, 0)), True) for t in ALLOWED_RECORD_TYPES]
    rows += [(t, int(n), False) for t, n in counts.items() if t not in ALLOWED_RECORD_TYPES]
    return pd.DataFrame(rows, columns=columns)


def date_ranges_by_record_type(frame: pd.DataFrame) -> pd.DataFrame:
    """Earliest/latest *valid* date per record type and date field.

    Invalid and blank dates are excluded and counted, not guessed.
    """
    columns = ["record_type", "date_field", "valid_dates", "earliest", "latest"]
    if "record_type" not in frame.columns:
        return pd.DataFrame(columns=columns)
    typed = parse_typed_columns(frame)
    rtype = frame["record_type"].astype(str).str.strip()
    rows = []
    for record_type in ALLOWED_RECORD_TYPES:
        mask = rtype == record_type
        for column in DATE_COLUMNS:
            if column not in frame.columns:
                continue
            dates = typed.loc[mask, f"{column}_parsed"].dropna()
            rows.append(
                (
                    record_type,
                    column,
                    int(len(dates)),
                    dates.min().date() if len(dates) else None,
                    dates.max().date() if len(dates) else None,
                )
            )
    return pd.DataFrame(rows, columns=columns)


def missing_value_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Blank-cell counts per column, with the contract's policy for blanks.

    A blank is only a problem where the policy says the value is required;
    the validator decides that, this table just describes completeness.
    """
    rows = []
    total = len(frame)
    for column in frame.columns:
        if column == SOURCE_ROW_COLUMN:
            continue
        blanks = int(is_blank(frame[column]).sum())
        rows.append(
            (
                column,
                blanks,
                round(100 * blanks / total, 1) if total else 0.0,
                _POLICY.get(column, "not in demonstration schema"),
            )
        )
    return pd.DataFrame(rows, columns=["field", "blank_cells", "blank_percent", "blank_policy"])


def summarize_dataset(frame: pd.DataFrame) -> DatasetSummary:
    """Headline descriptive figures for the Overview page."""

    def distinct(column: str) -> int:
        if column not in frame.columns:
            return 0
        values = frame[column].astype(str).str.strip()
        return int(values[values != ""].nunique())

    return DatasetSummary(
        source_record_count=len(frame),
        distinct_operating_units=distinct("operating_unit_id"),
        distinct_clients=distinct("client_id"),
        record_type_counts=record_type_counts(frame),
        date_ranges=date_ranges_by_record_type(frame),
    )
