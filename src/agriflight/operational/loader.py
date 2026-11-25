"""Read-only loader for the integrated operational dataset package.

* The package location comes from the AGRIFLIGHT_DATA_DIR environment variable
  (the package root, not its data/ folder). Nothing is hardcoded.
* Files are only read. Nothing is written, copied or cached on disk.
* Each CSV is kept twice: ``raw`` (every value as the exact source text) and
  ``tables`` (typed copies). Dates are parsed strictly as YYYY-MM-DD, booleans
  only from the text "True"/"False" after trimming surrounding whitespace
  (raw text unchanged), numbers with pandas.to_numeric.
  Blank stays missing (NaT/<NA>), never zero or False.
* Problems found while loading are returned as findings, not repaired.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from agriflight.operational.contract import (
    DATE_FORMAT,
    ENV_VAR,
    FALSE_TEXT,
    KNOWN_TEMPLATES,
    REQUIRED_PACKAGE_ENTRIES,
    TABLES,
    TRUE_TEXT,
    TableSpec,
)


class PackageError(ValueError):
    """The configured location is not a usable dataset package."""


@dataclass
class OperationalDataset:
    root: Path
    schema: dict
    raw: dict[str, pd.DataFrame]
    tables: dict[str, pd.DataFrame]
    templates: pd.DataFrame
    manifest: list[dict] | None
    supplied_validation: dict | None
    findings: list[dict] = field(default_factory=list)

    def has(self, table: str) -> bool:
        return table in self.tables


def finding(severity: str, check: str, table: str = "", column: str = "",
            record_id: str = "", explanation: str = "") -> dict:
    return {"severity": severity, "check": check, "table": table, "column": column,
            "record_id": record_id, "explanation": explanation}


def resolve_package_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return the configured package root, or raise PackageError explaining why not."""
    env = os.environ if environ is None else environ
    value = (env.get(ENV_VAR) or "").strip().strip('"')
    if not value:
        raise PackageError(
            f"{ENV_VAR} is not set. Set it to the dataset package root folder "
            "(the folder containing README.md, FILE_MANIFEST.json, data/ and docs/)."
        )
    return check_package_dir(Path(value).expanduser())


def check_package_dir(root: Path) -> Path:
    if not root.exists():
        raise PackageError(f"The configured dataset folder does not exist: {root.name!r}.")
    if not root.is_dir():
        raise PackageError(f"The configured dataset path is not a folder: {root.name!r}.")
    missing = [entry for entry in REQUIRED_PACKAGE_ENTRIES if not (root / entry).exists()]
    if missing:
        hint = ""
        if (root.name == "data") or (root / "schema.json").exists():
            hint = f" {ENV_VAR} must point to the package root, not its data/ or docs/ folder."
        raise PackageError(
            f"The folder {root.name!r} is not a valid dataset package; missing: "
            + ", ".join(missing) + "." + hint
        )
    return root.resolve()


def _read_json(path: Path, label: str, findings: list[dict]) -> object | None:
    if not path.exists():
        findings.append(finding("warning", "package_file_missing", explanation=f"{label} not found."))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        findings.append(finding("error", "package_file_unreadable", explanation=f"{label} is not valid JSON: {exc}"))
        return None


def _read_csv_text(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig")
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def parse_boolean(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Map exactly "True"->True and "False"->False; blank -> <NA>.

    Returns (parsed, invalid_mask). Any other text is <NA> and flagged invalid.
    Note: bool("False") is True in Python, so a generic cast must never be used.
    """
    text = series.astype(str).str.strip()
    parsed = pd.Series(pd.NA, index=series.index, dtype="boolean")
    parsed[text == TRUE_TEXT] = True
    parsed[text == FALSE_TEXT] = False
    invalid = (text != "") & ~text.isin([TRUE_TEXT, FALSE_TEXT])
    return parsed, invalid


def parse_date(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format=DATE_FORMAT, errors="coerce")
    invalid = parsed.isna() & (text != "")
    return parsed, invalid


def parse_number(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    text = series.astype(str).str.strip()
    parsed = pd.to_numeric(text.where(text != ""), errors="coerce").astype("Float64")
    invalid = parsed.isna() & (text != "")
    return parsed, invalid


def type_table(raw: pd.DataFrame, spec: TableSpec) -> tuple[pd.DataFrame, list[dict]]:
    """Return a typed copy of ``raw`` plus findings for unparseable values."""
    typed = raw.copy()
    findings: list[dict] = []
    keys = raw[spec.primary_key] if spec.primary_key in raw.columns else pd.Series("", index=raw.index)
    parsers = (
        [(c, parse_date, "invalid_date", "is not a YYYY-MM-DD date") for c in spec.date_columns]
        + [(c, parse_boolean, "invalid_boolean", "is not the text True or False") for c in spec.boolean_columns]
        + [(c, parse_number, "invalid_number", "is not a number") for c in spec.numeric_columns]
    )
    for column, parser, check, text in parsers:
        if column not in raw.columns:
            continue
        typed[column], invalid = parser(raw[column])
        for idx in raw.index[invalid]:
            findings.append(finding("error", check, spec.name, column, str(keys[idx]),
                                    f"Value {text}; kept as missing in calculations, original text retained."))
    for column in raw.columns:
        if column not in (spec.date_columns + spec.boolean_columns + spec.numeric_columns):
            typed[column] = raw[column].astype("string")
    return typed, findings


def _templates(root: Path, schema: dict, findings: list[dict]) -> pd.DataFrame:
    names = set(KNOWN_TEMPLATES) | {
        n for n, t in schema.get("tables", {}).items() if t.get("rows") == 0
    }
    rows = []
    for name in sorted(names):
        path = root / "data" / f"{name}.csv"
        expected_cols = schema.get("tables", {}).get(name, {}).get("columns")
        if not path.exists():
            rows.append((name, "missing", 0, None))
            findings.append(finding("warning", "template_missing", name,
                                    explanation="Input-contract template file is absent."))
            continue
        frame = _read_csv_text(path)
        status = "unfilled input contract (header only)" if frame.empty else f"contains {len(frame)} row(s)"
        header_ok = None if expected_cols is None else list(frame.columns) == expected_cols
        rows.append((name, status, len(frame), header_ok))
    return pd.DataFrame(rows, columns=["template", "status", "rows", "header_matches_schema"])


def load_package(root: Path) -> OperationalDataset:
    """Load the integrated tables read-only. Raises PackageError for an invalid package."""
    root = check_package_dir(Path(root))
    findings: list[dict] = []
    schema = _read_json(root / "docs" / "schema.json", "docs/schema.json", findings)
    if not isinstance(schema, dict) or "tables" not in schema:
        raise PackageError("docs/schema.json is missing, unreadable or has no 'tables' section.")
    manifest = _read_json(root / "FILE_MANIFEST.json", "FILE_MANIFEST.json", findings)
    supplied = _read_json(root / "docs" / "validation_results.json", "docs/validation_results.json", findings)

    raw: dict[str, pd.DataFrame] = {}
    tables: dict[str, pd.DataFrame] = {}
    for name, spec in TABLES.items():
        path = root / "data" / f"{name}.csv"
        if not path.exists():
            findings.append(finding("error" if spec.role == "main" else "warning", "table_file_missing",
                                    name, explanation=f"data/{name}.csv not found; dependent views are limited."))
            continue
        try:
            frame = _read_csv_text(path)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
            findings.append(finding("error", "table_unreadable", name, explanation=f"Could not parse CSV: {exc}"))
            continue
        raw[name] = frame
        typed, parse_findings = type_table(frame, spec)
        tables[name] = typed
        findings.extend(parse_findings)

    return OperationalDataset(
        root=root,
        schema=schema,
        raw=raw,
        tables=tables,
        templates=_templates(root, schema, findings),
        manifest=manifest if isinstance(manifest, list) else None,
        supplied_validation=supplied if isinstance(supplied, dict) else None,
        findings=findings,
    )


def manifest_check(ds: OperationalDataset) -> pd.DataFrame:
    """Compare files against FILE_MANIFEST.json SHA-256 values (read-only)."""
    rows = []
    for entry in ds.manifest or []:
        rel = str(entry.get("file", ""))
        path = ds.root / rel
        if not path.is_file():
            rows.append((rel, "missing"))
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append((rel, "matches" if digest == entry.get("sha256") else "differs"))
    return pd.DataFrame(rows, columns=["file", "manifest_sha256"])
