"""Load demonstration operations CSV files without altering their values.

Design rules:
* Every cell is read as text, so identifiers such as ``007`` keep their
  leading zeros and blanks stay blank (never NaN, never zero).
* The source file is only read, never written.
* A ``source_row`` column records the spreadsheet-style row number
  (header = row 1, first data row = row 2) so issues can be traced back.
* Missing columns are *not* fatal here; the validator reports them, so the
  dashboard can still explain what is wrong with a malformed file.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import IO, Union

import pandas as pd

from agriflight.data.schema import (
    DATE_COLUMNS,
    DATE_FORMAT,
    NUMERIC_COLUMNS,
    REQUIRED_COLUMNS,
    SOURCE_ROW_COLUMN,
)

CsvSource = Union[str, Path, IO[bytes], IO[str], bytes]


class DataLoadError(ValueError):
    """Raised when a CSV cannot be read as a table at all."""


def _to_buffer(source: CsvSource) -> Union[str, Path, IO[bytes], IO[str]]:
    if isinstance(source, bytes):
        return io.BytesIO(source)
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise DataLoadError(f"File not found: {path}")
        if path.is_dir():
            raise DataLoadError(f"Expected a CSV file but got a directory: {path}")
        if path.stat().st_size == 0:
            raise DataLoadError(f"The file is empty (0 bytes): {path.name}")
        return path
    if hasattr(source, "seek"):
        source.seek(0)
    return source


def load_operations_csv(source: CsvSource) -> pd.DataFrame:
    """Read a demonstration-schema CSV as text and add ``source_row``.

    Args:
        source: A file path, raw bytes, or an open binary/text file object
            (for example a Streamlit ``UploadedFile``).

    Returns:
        A DataFrame whose data columns are all strings with blanks as ``""``,
        plus an integer ``source_row`` column.

    Raises:
        DataLoadError: If the input is missing, empty, not decodable as UTF-8,
            or not parseable as a CSV table.
    """
    buffer = _to_buffer(source)
    try:
        frame = pd.read_csv(
            buffer,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8-sig",
            skip_blank_lines=True,
        )
    except pd.errors.EmptyDataError as exc:
        raise DataLoadError(
            "The file contains no data and no header row. "
            "Expected a CSV with a header row such as: " + ", ".join(REQUIRED_COLUMNS)
        ) from exc
    except pd.errors.ParserError as exc:
        raise DataLoadError(
            f"The file could not be parsed as CSV (check delimiters and quoting): {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise DataLoadError(
            "The file is not UTF-8 encoded text. Save it as 'CSV UTF-8' and retry. "
            "Excel workbooks (.xlsx) are not supported by this loader."
        ) from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    if SOURCE_ROW_COLUMN in frame.columns:
        raise DataLoadError(
            f"The input already has a '{SOURCE_ROW_COLUMN}' column, which is reserved."
        )
    # Header is row 1; the first data row is row 2. Assumes no embedded newlines.
    frame.insert(0, SOURCE_ROW_COLUMN, range(2, len(frame) + 2))
    return frame.reset_index(drop=True)


def missing_columns(frame: pd.DataFrame) -> list[str]:
    """Return required schema columns absent from ``frame`` (in schema order)."""
    return [column for column in REQUIRED_COLUMNS if column not in frame.columns]


def is_blank(series: pd.Series) -> pd.Series:
    """True where a text cell is empty or whitespace-only."""
    return series.astype(str).str.strip() == ""


def parse_typed_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with parsed ``*_parsed`` columns added beside the raw text.

    Raw columns are left untouched. Blank or invalid values become NaT/NaN in
    the parsed columns only; validation decides whether that is an error.
    """
    typed = frame.copy()
    for column in DATE_COLUMNS:
        if column in typed.columns:
            typed[f"{column}_parsed"] = pd.to_datetime(
                typed[column].astype(str).str.strip(),
                format=DATE_FORMAT,
                errors="coerce",
            )
    for column in NUMERIC_COLUMNS:
        if column in typed.columns:
            typed[f"{column}_parsed"] = pd.to_numeric(
                typed[column].astype(str).str.strip(), errors="coerce"
            )
    return typed
