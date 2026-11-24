"""Data-quality validation for the demonstration operations schema.

The validator never modifies, drops or fills rows. It returns a structured
issue table that explains each problem with its source row and raw value.

Optional blanks (for example a planned visit with no ``actual_date``) are not
issues. Only rule violations documented in docs/data_contract.md are reported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from agriflight.data.loader import is_blank, missing_columns, parse_typed_columns
from agriflight.data.schema import (
    ALLOWED_RECORD_TYPES,
    CONDITIONALLY_REQUIRED_DATE,
    DATE_COLUMNS,
    EXPECTED_COLUMNS,
    REQUIRED_VALUE_COLUMNS,
    SOURCE_ROW_COLUMN,
    SYNTHETIC_ORIGIN,
)

ERROR = "error"
WARNING = "warning"
INFO = "info"

ISSUE_COLUMNS: tuple[str, ...] = (
    "source_row",
    "field",
    "issue_code",
    "severity",
    "raw_value",
    "explanation",
)

ISSUE_CODES: dict[str, str] = {
    "MISSING_REQUIRED_COLUMN": "A column required by the data contract is absent.",
    "UNEXPECTED_COLUMN": "A column not in the data contract is present (kept, not used).",
    "NO_DATA_ROWS": "The file has a header but no data rows.",
    "MISSING_REQUIRED_VALUE": "A required identifier or field is blank.",
    "MISSING_CONDITIONAL_DATE": "A date required for this record type is blank.",
    "DUPLICATE_OBSERVATION_ID": "The same observation_id appears on more than one row.",
    "INVALID_DATE": "A non-blank date is not a real YYYY-MM-DD calendar date.",
    "INVALID_NUMBER": "A non-blank numeric field is not a finite number.",
    "NEGATIVE_AREA": "area_ha is negative.",
    "UNEXPECTED_RECORD_TYPE": "record_type is not one of the documented values.",
    "NON_SYNTHETIC_ORIGIN": "data_origin is not synthetic_demo.",
}


@dataclass
class ValidationReport:
    """Result of validating one loaded table."""

    issues: pd.DataFrame
    row_count: int
    missing_columns: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return int((self.issues["severity"] == ERROR).sum())

    @property
    def warning_count(self) -> int:
        return int((self.issues["severity"] == WARNING).sum())

    @property
    def rows_with_errors(self) -> int:
        rows = self.issues.loc[self.issues["severity"] == ERROR, "source_row"]
        return int(rows.dropna().nunique())

    @property
    def passed(self) -> bool:
        """True only when there are no errors (warnings/info allowed)."""
        return self.error_count == 0

    def counts_by_code(self) -> pd.DataFrame:
        if self.issues.empty:
            return pd.DataFrame(columns=["issue_code", "severity", "count"])
        return (
            self.issues.groupby(["issue_code", "severity"], as_index=False)
            .size()
            .rename(columns={"size": "count"})
            .sort_values(["count", "issue_code"], ascending=[False, True])
            .reset_index(drop=True)
        )


def _issue(
    source_row: int | None, field_name: str, code: str, severity: str, raw: str, text: str
) -> dict[str, object]:
    return {
        "source_row": source_row,
        "field": field_name,
        "issue_code": code,
        "severity": severity,
        "raw_value": raw,
        "explanation": text,
    }


def validate_operations(frame: pd.DataFrame) -> ValidationReport:
    """Validate a frame produced by :func:`load_operations_csv`.

    Checks that cannot run because their column is missing are skipped; the
    missing column itself is reported as an error.
    """
    issues: list[dict[str, object]] = []
    absent = missing_columns(frame)
    present = set(frame.columns)

    for column in absent:
        issues.append(
            _issue(None, column, "MISSING_REQUIRED_COLUMN", ERROR, "",
                   f"Required column '{column}' is missing, so its checks were skipped.")
        )
    for column in frame.columns:
        if column != SOURCE_ROW_COLUMN and column not in EXPECTED_COLUMNS:
            issues.append(
                _issue(None, column, "UNEXPECTED_COLUMN", INFO, "",
                       f"Column '{column}' is not part of the demonstration schema; "
                       "it is shown but not validated or used.")
            )
    if len(frame) == 0:
        issues.append(
            _issue(None, "(file)", "NO_DATA_ROWS", WARNING, "",
                   "The file has a header row but no data rows.")
        )

    rows = frame[SOURCE_ROW_COLUMN] if SOURCE_ROW_COLUMN in present else pd.Series(
        range(2, len(frame) + 2), index=frame.index
    )

    # Required values (blank = missing). Only for present columns.
    for column in REQUIRED_VALUE_COLUMNS:
        if column not in present:
            continue
        for idx in frame.index[is_blank(frame[column])]:
            issues.append(
                _issue(int(rows[idx]), column, "MISSING_REQUIRED_VALUE", ERROR,
                       frame.at[idx, column], f"'{column}' is required but blank.")
            )

    # Duplicate observation IDs (blanks are already reported above).
    if "observation_id" in present:
        ids = frame["observation_id"].astype(str).str.strip()
        duplicated = ids.duplicated(keep=False) & (ids != "")
        for idx in frame.index[duplicated]:
            other_rows = [int(rows[i]) for i in frame.index[ids == ids[idx]] if i != idx]
            issues.append(
                _issue(int(rows[idx]), "observation_id", "DUPLICATE_OBSERVATION_ID", ERROR,
                       frame.at[idx, "observation_id"],
                       f"observation_id also appears on row(s) {other_rows}. "
                       "Neither row is dropped; the duplicate needs review.")
            )

    # Record types.
    if "record_type" in present:
        rtype = frame["record_type"].astype(str).str.strip()
        bad = (~rtype.isin(ALLOWED_RECORD_TYPES)) & (rtype != "")
        for idx in frame.index[bad]:
            issues.append(
                _issue(int(rows[idx]), "record_type", "UNEXPECTED_RECORD_TYPE", ERROR,
                       frame.at[idx, "record_type"],
                       "Allowed values are " + ", ".join(ALLOWED_RECORD_TYPES) + ". "
                       "The row is kept but excluded from record-type rules.")
            )
    else:
        rtype = pd.Series("", index=frame.index)

    typed = parse_typed_columns(frame)

    # Dates: a blank is not invalid; a non-blank unparseable value is.
    for column in DATE_COLUMNS:
        if column not in present:
            continue
        blank = is_blank(frame[column])
        invalid = typed[f"{column}_parsed"].isna() & ~blank
        for idx in frame.index[invalid]:
            issues.append(
                _issue(int(rows[idx]), column, "INVALID_DATE", ERROR, frame.at[idx, column],
                       "Not a valid calendar date in YYYY-MM-DD format. "
                       "The value is kept as text and not guessed.")
            )
        for record_type, required_date in CONDITIONALLY_REQUIRED_DATE.items():
            if required_date != column:
                continue
            missing = blank & (rtype == record_type)
            for idx in frame.index[missing]:
                issues.append(
                    _issue(int(rows[idx]), column, "MISSING_CONDITIONAL_DATE", ERROR, "",
                           f"A {record_type} row must have '{column}'. "
                           "No date is inferred.")
                )

    # Area: optional, but if present must be a finite, non-negative number.
    if "area_ha" in present:
        blank = is_blank(frame["area_ha"])
        parsed = typed["area_ha_parsed"]
        for idx in frame.index[~blank]:
            value = parsed[idx]
            raw = frame.at[idx, "area_ha"]
            if pd.isna(value) or not math.isfinite(float(value)):
                issues.append(
                    _issue(int(rows[idx]), "area_ha", "INVALID_NUMBER", ERROR, raw,
                           "area_ha must be a plain number of hectares (e.g. 12.5). "
                           "It is not converted to zero.")
                )
            elif value < 0:
                issues.append(
                    _issue(int(rows[idx]), "area_ha", "NEGATIVE_AREA", ERROR, raw,
                           "area_ha cannot be negative.")
                )

    # Provenance: this dashboard is intended for synthetic demonstration rows.
    if "data_origin" in present:
        origin = frame["data_origin"].astype(str).str.strip()
        non_demo = (origin != SYNTHETIC_ORIGIN) & (origin != "")
        for idx in frame.index[non_demo]:
            issues.append(
                _issue(int(rows[idx]), "data_origin", "NON_SYNTHETIC_ORIGIN", WARNING,
                       frame.at[idx, "data_origin"],
                       "This prototype is intended for synthetic demonstration data. "
                       "Do not publish or commit non-synthetic rows.")
            )

    issue_frame = pd.DataFrame(issues, columns=list(ISSUE_COLUMNS))
    issue_frame["source_row"] = issue_frame["source_row"].astype("Int64")
    issue_frame = issue_frame.sort_values(
        ["source_row", "field", "issue_code"], na_position="first", kind="stable"
    ).reset_index(drop=True)
    return ValidationReport(issues=issue_frame, row_count=len(frame), missing_columns=absent)
