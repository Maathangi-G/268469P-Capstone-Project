"""Coverage-target feasibility for the daily-coverage prediction requirement.

Each candidate hectare column in the package is assessed from the files at
run time (nothing is hardcoded). Four meanings are kept distinct:

* observed completed workload - work recorded as done (a small job does not
  reveal maximum daily capacity);
* estimated achievable capacity - no such source is supplied;
* planned work - what a plan intended, not what happened;
* static farm area - a snapshot of area, not daily output.

A record is *eligible* as a model target only if it is observed workload,
has a finite non-negative numeric value, an explicit verification flag set to
True, any supplied eligibility flag set to True, and a valid date. A verified
zero is eligible; a missing value is never treated as zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from agriflight.operational.loader import OperationalDataset

OBSERVED = "observed completed workload"
CAPACITY = "estimated achievable capacity"
PLANNED = "planned work"
STATIC = "static farm area"

BLOCKED_MESSAGE = ("Coverage-model training blocked: no verified daily-hectare targets "
                   "in the inspected integrated package.")
BASELINE_REAL_DATA_STATUS = "Implemented and tested; not fitted or evaluated on operational targets."


@dataclass(frozen=True)
class TargetSource:
    table: str
    column: str
    category: str
    grain: str
    date_column: str | None
    verified_column: str | None = None
    eligible_column: str | None = None
    supplied_reason_column: str | None = None


TARGET_SOURCES: tuple[TargetSource, ...] = (
    TargetSource("flight_observations", "actual_daily_covered_ha", OBSERVED,
                 "source observation row (operation unit, recorded date, source layer)", "recorded_actual_date"),
    TargetSource("daily_work_evidence", "actual_covered_ha", OBSERVED,
                 "operation unit x recorded date (main tracker evidence)", "recorded_date",
                 verified_column="target_measured", eligible_column="training_eligible",
                 supplied_reason_column="blocking_reason"),
    TargetSource("daily_coverage_template", "measured_covered_ha", OBSERVED,
                 "division x work date x team (input contract)", "work_date",
                 verified_column="independent_label_verified"),
    TargetSource("trial_observations", "recorded_extent_ha", OBSERVED,
                 "trial record (non-recurring; extent of a trial job)", "trial_date"),
    TargetSource("planned_team_days", "planned_coverage_ha", PLANNED, "team x planned date", "planned_date"),
    TargetSource("operation_units", "imaging_area_ha", STATIC, "tracker operation unit (undated snapshot)", None),
    TargetSource("scheduler_division_inputs", "tracker_imaging_area_ha", STATIC, "division (undated snapshot)", None),
    TargetSource("area_evidence", "boundary_area_ha", STATIC, "mixed record_grain (field/division/farm/summary)", "effective_date"),
    TargetSource("area_evidence", "farm_total_area_ha", STATIC, "mixed record_grain (field/division/farm/summary)", "effective_date"),
    TargetSource("area_evidence", "contract_area_ha", STATIC, "mixed record_grain (field/division/farm/summary)", "effective_date"),
)


def _eligibility_masks(ds: OperationalDataset, src: TargetSource) -> dict[str, pd.Series] | None:
    typed, raw = ds.tables.get(src.table), ds.raw.get(src.table)
    if typed is None or raw is None or src.column not in typed.columns:
        return None
    text = raw[src.column].astype(str).str.strip()
    value = pd.to_numeric(typed[src.column], errors="coerce").astype("Float64")
    blank = text == ""
    nonnumeric = ~blank & value.isna()
    as_float = value.to_numpy(dtype=float, na_value=np.nan)
    finite = pd.Series(np.isfinite(as_float), index=value.index)  # missing -> NaN -> not finite
    nonfinite = value.notna() & ~finite
    negative = finite & pd.Series(as_float < 0, index=value.index)
    numeric_ok = finite & ~negative
    if src.verified_column and src.verified_column in typed.columns:
        verified = typed[src.verified_column].fillna(False).astype(bool)
    else:
        verified = pd.Series(False, index=typed.index)
    if src.eligible_column and src.eligible_column in typed.columns:
        flagged = typed[src.eligible_column].fillna(False).astype(bool)
    else:
        flagged = pd.Series(True, index=typed.index)
    if src.date_column and src.date_column in typed.columns:
        dated = typed[src.date_column].notna()
    else:
        dated = pd.Series(False, index=typed.index)
    observed = pd.Series(src.category == OBSERVED, index=typed.index)
    eligible = observed & numeric_ok & verified & flagged & dated
    return {"blank": blank, "nonnumeric": nonnumeric, "nonfinite": nonfinite, "negative": negative,
            "numeric_ok": numeric_ok, "verified": verified, "flagged": flagged, "dated": dated,
            "observed": observed, "eligible": eligible}


def _reasons(ds: OperationalDataset, src: TargetSource, m: dict[str, pd.Series]) -> list[tuple[str, int]]:
    excluded = ~m["eligible"]
    reasons = [
        (f"category is '{src.category}', not observed workload", ~m["observed"]),
        ("target value missing (not treated as zero)", m["blank"]),
        ("target value not numeric", m["nonnumeric"]),
        ("target value not finite", m["nonfinite"]),
        ("target value negative", m["negative"]),
    ]
    if not src.verified_column:
        reasons.append(("no verification field in this table", pd.Series(True, index=excluded.index)))
    else:
        reasons.append((f"{src.verified_column} not True", ~m["verified"]))
    if src.eligible_column:
        reasons.append((f"{src.eligible_column} not True", ~m["flagged"]))
    reasons.append(("no valid date" if src.date_column else "no date column (snapshot)", ~m["dated"]))
    out = [(text, int((mask & excluded).sum())) for text, mask in reasons]
    if src.supplied_reason_column:
        supplied = ds.tables[src.table].loc[excluded, src.supplied_reason_column].dropna()
        for reason, count in supplied.value_counts().items():
            out.append((f"supplied blocking_reason: {reason}", int(count)))
    return [(text, n) for text, n in out if n > 0]


def feasibility_report(ds: OperationalDataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(one row per target source, long table of exclusion reasons)."""
    rows, reason_rows = [], []
    for src in TARGET_SOURCES:
        base = {"table": src.table, "target_column": src.column, "category": src.category,
                "intended_grain": src.grain}
        masks = _eligibility_masks(ds, src)
        if masks is None:
            rows.append({**base, "records": None, "status": "table/column not available"})
            continue
        eligible = masks["eligible"]
        dates = ds.tables[src.table].loc[eligible, src.date_column] if src.date_column else pd.Series(dtype="datetime64[ns]")
        rows.append({
            **base,
            "records": len(eligible),
            "nonmissing_numeric_ha": int(masks["numeric_ok"].sum() + masks["negative"].sum()),
            "verified_measured": int((masks["verified"] & masks["numeric_ok"]).sum()),
            "eligible_for_modelling": int(eligible.sum()),
            "eligible_first_date": dates.min().date() if len(dates) else None,
            "eligible_last_date": dates.max().date() if len(dates) else None,
            "eligible_distinct_dates": int(dates.nunique()) if len(dates) else 0,
            "status": "eligible records present" if eligible.any() else "no eligible records",
        })
        for text, count in _reasons(ds, src, masks):
            reason_rows.append({"table": src.table, "target_column": src.column, "exclusion_reason": text,
                                "records": count})
    return pd.DataFrame(rows), pd.DataFrame(reason_rows, columns=["table", "target_column", "exclusion_reason", "records"])


def training_status(report: pd.DataFrame) -> tuple[bool, str]:
    """(blocked?, message). Scope is the inspected package only, not all company sources."""
    observed = report[report["category"] == OBSERVED]
    eligible = int(pd.to_numeric(observed.get("eligible_for_modelling"), errors="coerce").fillna(0).sum())
    if eligible == 0:
        return True, BLOCKED_MESSAGE
    return False, (f"{eligible} eligible observed-workload record(s) found. Model fitting is not performed in "
                   "this milestone; grains must be kept separate before any fitting.")


def eligible_training_frame(ds: OperationalDataset, table: str, column: str) -> pd.DataFrame:
    """Eligible records from ONE source in the baseline's input shape (single grain)."""
    src = next(s for s in TARGET_SOURCES if s.table == table and s.column == column)
    masks = _eligibility_masks(ds, src)
    columns = ["target_grain", "target_ha", "target_verified", "target_date"]
    if masks is None or not masks["eligible"].any():
        return pd.DataFrame(columns=columns)
    rows = ds.tables[table][masks["eligible"]]
    return pd.DataFrame({
        "target_grain": src.grain,
        "target_ha": pd.to_numeric(rows[column]).astype(float),
        "target_verified": True,
        "target_date": rows[src.date_column],
    }).reset_index(drop=True)


# Feature availability at scheduling time. This classification is an
# AI-proposed, provisional review of the package's columns; it is not validated.
FEATURE_AVAILABILITY: tuple[tuple[str, str, str], ...] = (
    ("known when preparing a schedule", "planned_team_days.planned_date / team_reference / vehicle_model_id",
     "Entered as part of a plan; plan revisions and the exact preparation date are not recorded."),
    ("known when preparing a schedule", "divisions / farms / clients identity and hierarchy",
     "Registry structure; valid as of registry, not versioned by date."),
    ("known when preparing a schedule", "vehicle_rate_evidence fuel price / efficiency (source period)",
     "Historical budget assumptions for their own period only; never backfill later prices."),
    ("known only after work happens", "flight_observations.recorded_actual_date, person_ids, equipment_reference",
     "Realised execution details; using them at planning time would leak outcomes."),
    ("known only after work happens", "flight_observations.actual_daily_covered_ha / daily_work_evidence.actual_covered_ha",
     "Realised outcomes (targets), currently unpopulated."),
    ("known only after work happens", "observation_status, source_review_flags_present, completed_service_id",
     "Assigned after or about execution."),
    ("known only after work happens", "actual weather on the work date (not in package)",
     "Future actual weather must not be used as if forecast at scheduling time."),
    ("uncertain timing / provenance", "operation_units.imaging_area_ha / scheduler_division_inputs.tracker_imaging_area_ha",
     "Undated snapshot; may reflect later revisions."),
    ("uncertain timing / provenance", "area_evidence boundary / farm total / contract area",
     "No effective dates supplied; mixed grains."),
    ("uncertain timing / provenance", "operation_units.current_status_snapshot",
     "Snapshot without an effective date; cannot be backdated."),
    ("uncertain timing / provenance", "scheduler_division_inputs.last_recorded_capture_date",
     "Computed over the whole history; at a past planning date only earlier records were known."),
    ("uncertain timing / provenance", "farm_vehicle_evidence / route_vehicle_references",
     "Aggregated across budget periods; reconstruct per planning date before use."),
    ("uncertain timing / provenance", "budget_fuel_trips planned_date / period",
     "Periods inferred from filenames; some planned dates fall outside them."),
    ("uncertain timing / provenance", "planned_team_days (all fields)",
     "No source row provenance supplied in this release; revision history unknown."),
    ("uncertain timing / provenance", "weather forecasts (not in package)",
     "Usable only as an archived forecast issued before the planning date."),
)


def feature_availability() -> pd.DataFrame:
    return pd.DataFrame(FEATURE_AVAILABILITY, columns=["availability", "feature_or_source", "rationale"])
