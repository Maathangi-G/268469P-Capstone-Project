"""Checks the application runs itself on the loaded operational dataset.

These are kept separate from the package's own supplied findings
(data_quality_issues.csv and docs/validation_results.json). Nothing here
modifies, drops or fills source rows; every problem becomes a finding.
Findings reference record IDs and counts only, never row contents.
"""

from __future__ import annotations

import pandas as pd

from agriflight.operational.contract import FOREIGN_KEYS, LIST_SEPARATOR, TABLES
from agriflight.operational.loader import OperationalDataset, finding, manifest_check

FINDING_COLUMNS = ["severity", "check", "table", "column", "record_id", "explanation"]
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
MAX_EXAMPLES = 5


def split_list(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [part.strip() for part in str(value).split(LIST_SEPARATOR) if part.strip()]


def _blank(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip() == ""


def _columns_and_keys(ds: OperationalDataset) -> list[dict]:
    out: list[dict] = []
    for name, spec in TABLES.items():
        raw = ds.raw.get(name)
        if raw is None:
            continue
        missing = [c for c in spec.required_columns if c not in raw.columns]
        for column in missing:
            out.append(finding("error", "required_column_missing", name, column,
                               explanation="Column required by the application contract is absent."))
        if raw.empty:
            out.append(finding("error", "table_empty", name,
                               explanation="Table has a header but no rows; it is not a template."))
        pk = spec.primary_key
        if pk not in raw.columns:
            continue
        keys = raw[pk].astype(str).str.strip()
        blanks = int((keys == "").sum())
        if blanks:
            out.append(finding("error", "primary_key_blank", name, pk,
                               explanation=f"{blanks} row(s) have a blank {pk}."))
        dupes = keys[(keys != "") & keys.duplicated(keep=False)]
        if not dupes.empty:
            examples = ", ".join(sorted(dupes.unique())[:MAX_EXAMPLES])
            out.append(finding("error", "primary_key_duplicate", name, pk, examples,
                               f"{dupes.nunique()} {pk} value(s) occur on more than one row; "
                               "one-to-one joins on this table would inflate counts."))
        for column, allowed in spec.allowed_values.items():
            if column not in raw.columns:
                continue
            values = raw[column].astype(str).str.strip()
            bad = raw.loc[(values != "") & ~values.isin(allowed), pk]
            if not bad.empty:
                out.append(finding("error", "unexpected_value", name, column,
                                   ", ".join(bad.astype(str).head(MAX_EXAMPLES)),
                                   f"{len(bad)} row(s) outside {list(allowed)}; the view's labels assume these values."))
    return out


def _foreign_keys(ds: OperationalDataset) -> list[dict]:
    out: list[dict] = []
    for fk in FOREIGN_KEYS:
        child, parent = ds.raw.get(fk.table), ds.raw.get(fk.ref_table)
        if child is None or parent is None or fk.column not in child.columns or fk.ref_column not in parent.columns:
            continue
        rows = child
        if fk.condition_column:
            if fk.condition_column not in child.columns:
                continue
            rows = child[child[fk.condition_column].astype(str).str.strip() == fk.condition_value]
        valid = set(parent[fk.ref_column].astype(str).str.strip()) - {""}
        pk = TABLES[fk.table].primary_key
        orphans: list[str] = []
        for _, row in rows.iterrows():
            values = split_list(row[fk.column]) if fk.is_list else [str(row[fk.column]).strip()]
            if any(v and v not in valid for v in values):
                orphans.append(str(row.get(pk, "")))
        if orphans:
            label = f"{fk.column} (where {fk.condition_column}={fk.condition_value})" if fk.condition_column else fk.column
            out.append(finding("error", "foreign_key_orphan", fk.table, label,
                               ", ".join(orphans[:MAX_EXAMPLES]),
                               f"{len(orphans)} row(s) reference a {fk.ref_table}.{fk.ref_column} that does not exist."))
    return out


def _hierarchy(ds: OperationalDataset) -> list[dict]:
    """division -> farm -> client must agree wherever the same keys are repeated."""
    out: list[dict] = []
    farms, divisions = ds.raw.get("farms"), ds.raw.get("divisions")
    if farms is None or divisions is None:
        return out
    farm_client = dict(zip(farms["farm_id"], farms["client_id"]))
    div_parent = {d: (f, c) for d, f, c in zip(divisions["division_id"], divisions["farm_id"], divisions["client_id"])}
    bad = [d for d, (f, c) in div_parent.items() if f in farm_client and farm_client[f] != c]
    if bad:
        out.append(finding("error", "hierarchy_mismatch", "divisions", "client_id", ", ".join(bad[:MAX_EXAMPLES]),
                           f"{len(bad)} division(s) name a client different from their farm's client."))
    sched = ds.raw.get("scheduler_division_inputs")
    if sched is not None and {"division_id", "farm_id", "client_id"} <= set(sched.columns):
        bad = [d for d, f, c in zip(sched["division_id"], sched["farm_id"], sched["client_id"])
               if d in div_parent and div_parent[d] != (f, c)]
        if bad:
            out.append(finding("error", "hierarchy_mismatch", "scheduler_division_inputs", "farm_id/client_id",
                               ", ".join(bad[:MAX_EXAMPLES]),
                               f"{len(bad)} row(s) disagree with divisions.csv on farm or client."))
    return out


def _snapshot(ds: OperationalDataset) -> list[dict]:
    """Reconcile loaded row counts and headers with schema.json (reference only)."""
    out: list[dict] = []
    schema_tables = ds.schema.get("tables", {})
    for name, raw in ds.raw.items():
        spec = schema_tables.get(name)
        if spec is None:
            out.append(finding("warning", "snapshot_table_not_in_schema", name,
                               explanation="Table is not described in docs/schema.json."))
            continue
        if spec.get("rows") != len(raw):
            out.append(finding("warning", "snapshot_row_count_differs", name,
                               explanation=f"File has {len(raw)} rows; schema.json lists {spec.get('rows')}."))
        if spec.get("columns") and list(raw.columns) != spec["columns"]:
            out.append(finding("warning", "snapshot_header_differs", name,
                               explanation="Header differs from schema.json column list."))
    if ds.manifest:
        check = manifest_check(ds)
        changed = check[check["manifest_sha256"] != "matches"]
        if not changed.empty:
            out.append(finding("warning", "manifest_mismatch", column="sha256",
                               record_id=", ".join(changed["file"].head(MAX_EXAMPLES)),
                               explanation=f"{len(changed)} file(s) are missing or differ from FILE_MANIFEST.json."))
    return out


def validate_operational(ds: OperationalDataset) -> pd.DataFrame:
    """All application findings (load + structure + relationships + snapshot)."""
    rows = (list(ds.findings) + _columns_and_keys(ds) + _foreign_keys(ds)
            + _hierarchy(ds) + _snapshot(ds))
    frame = pd.DataFrame(rows, columns=FINDING_COLUMNS)
    if frame.empty:
        return frame
    frame["_order"] = frame["severity"].map(SEVERITY_ORDER).fillna(9)
    return frame.sort_values(["_order", "table", "check"], kind="stable").drop(columns="_order").reset_index(drop=True)


def snapshot_table(ds: OperationalDataset) -> pd.DataFrame:
    """Loaded rows per integrated table vs the schema.json snapshot (reference only)."""
    schema_tables = ds.schema.get("tables", {})
    rows = []
    for name in TABLES:
        loaded = len(ds.raw[name]) if name in ds.raw else None
        expected = schema_tables.get(name, {}).get("rows")
        rows.append((name, TABLES[name].role, loaded, expected,
                     None if loaded is None or expected is None else loaded == expected))
    return pd.DataFrame(rows, columns=["table", "role", "rows_loaded", "schema_snapshot_rows", "matches_snapshot"])


def finding_counts(findings: pd.DataFrame) -> dict[str, int]:
    return {sev: int((findings["severity"] == sev).sum()) for sev in ("error", "warning", "info")}
