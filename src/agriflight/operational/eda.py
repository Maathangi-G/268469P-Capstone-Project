"""Reproducible exploratory analysis of the operational dataset (read-only).

Conventions used by every function here:
* Unit of counting is a *source observation row* unless stated otherwise.
  Rows are never equated with unique flights, services or pilot-days.
* Source layers (main_monthly, older_archive, annual_cycles) are analysed
  separately; main_monthly is the default layer.
* The date basis is ``recorded_actual_date`` unless stated otherwise.
* Missing history is not interpreted as onboarding, inactivity or a missed
  visit. Gaps are "gaps between recorded capture dates", never verified
  monitoring-cycle intervals and never late/on-time labels.
* Area grains and area types are kept apart and never summed together.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from agriflight.operational.contract import DEFAULT_OBSERVATION_LAYER, OBSERVATION_LAYERS
from agriflight.operational.loader import OperationalDataset
from agriflight.operational.summaries import label_maps
from agriflight.operational.validation import split_list

DATE_BASIS = "recorded_actual_date"
GAP_LABEL = "gaps between recorded capture dates"
GAP_BINS = (0, 7, 14, 21, 28, 35, 42, 60, 90, 180, 10_000)
AREA_TYPES = ("boundary_area_ha", "farm_total_area_ha", "contract_area_ha")
# Only an explicit resolution value counts as a confirmed duplicate; anything
# else (including the package's "not_deduplicated_..." value) is a candidate.
CONFIRMED_DUPLICATE_RESOLUTIONS = frozenset({"confirmed_duplicate"})


def _nonblank(series: pd.Series) -> pd.Series:
    return series.notna() & (series.astype("string").str.strip() != "")


def _observations(ds: OperationalDataset, layer: str | None) -> pd.DataFrame:
    obs = ds.tables.get("flight_observations")
    if obs is None:
        return pd.DataFrame()
    return obs if layer is None else obs[obs["source_layer"] == layer]


# ------------------------------------------------- A. completeness/history
OBSERVATION_FIELDS: dict[str, tuple[str, str | None]] = {
    # column: (category, reference table for unknown-ID checks)
    "observation_id": ("identifier", None),
    "operation_unit_id": ("identifier", "operation_units"),
    "division_id": ("identifier", "divisions"),
    "planned_date": ("date", None),
    "recorded_actual_date": ("date", None),
    "person_ids": ("assignment", None),
    "equipment_reference": ("assignment", None),
    "actual_daily_covered_ha": ("target", None),
    "completed_service_id": ("target", None),
}


def completeness(ds: OperationalDataset, layers: Iterable[str] = OBSERVATION_LAYERS) -> pd.DataFrame:
    """Missing and unknown-reference counts for important observation fields, per layer."""
    ref_keys = {"operation_units": "operation_unit_id", "divisions": "division_id"}
    rows = []
    for layer in layers:
        part = _observations(ds, layer)
        for column, (category, ref) in OBSERVATION_FIELDS.items():
            if column not in part.columns:
                rows.append((layer, column, category, len(part), None, None, None))
                continue
            present = _nonblank(part[column])
            unknown = None
            if ref and ref in ds.tables:
                known = set(ds.tables[ref][ref_keys[ref]].astype(str))
                unknown = int((present & ~part[column].astype("string").isin(known)).sum())
            missing = int((~present).sum())
            rows.append((layer, column, category, len(part), missing,
                         round(100 * missing / len(part), 1) if len(part) else None, unknown))
    return pd.DataFrame(rows, columns=["source_layer", "field", "category", "source_rows",
                                       "missing", "missing_percent", "unknown_reference"])


def undated_unmapped(ds: OperationalDataset) -> pd.DataFrame:
    """Per layer: rows without a recorded date and rows without unit/division links."""
    rows = []
    for layer in OBSERVATION_LAYERS:
        part = _observations(ds, layer)
        if part.empty:
            rows.append((layer, 0, 0, 0, 0, 0))
            continue
        undated = part[DATE_BASIS].isna()
        no_unit = ~_nonblank(part["operation_unit_id"])
        no_div = ~_nonblank(part["division_id"])
        rows.append((layer, len(part), int(undated.sum()), int(no_unit.sum()), int(no_div.sum()),
                     int((no_unit & no_div).sum())))
    return pd.DataFrame(rows, columns=["source_layer", "source_rows", f"undated_{DATE_BASIS}",
                                       "no_operation_unit_id", "no_division_id", "no_unit_and_no_division"])


def unit_history(ds: OperationalDataset, layer: str = DEFAULT_OBSERVATION_LAYER) -> pd.DataFrame:
    """Recorded-date coverage per operation_unit_id within ONE layer.

    Rows without an operation_unit_id are excluded here (see undated_unmapped).
    """
    part = _observations(ds, layer)
    columns = ["source_layer", "operation_unit_id", "operation_unit", "source_rows", "dated_observations",
               "distinct_recorded_dates", "same_date_repeat_rows", "first_recorded_date",
               "last_recorded_date", "months_with_records"]
    if part.empty:
        return pd.DataFrame(columns=columns)
    part = part[_nonblank(part["operation_unit_id"])]
    labels = label_maps(ds)["operation_unit"]
    rows = []
    for unit, group in part.groupby("operation_unit_id"):
        dates = group[DATE_BASIS].dropna()
        distinct = dates.drop_duplicates()
        rows.append((layer, unit, labels.get(unit), len(group), len(dates), len(distinct),
                     len(dates) - len(distinct),
                     dates.min().date() if len(dates) else None,
                     dates.max().date() if len(dates) else None,
                     int(dates.dt.to_period("M").nunique()) if len(dates) else 0))
    return pd.DataFrame(rows, columns=columns).sort_values("operation_unit_id").reset_index(drop=True)


def history_overview(history: pd.DataFrame) -> dict[str, object]:
    if history.empty:
        return {"operation_units": 0}
    return {
        "operation_units": len(history),
        "units_with_no_dated_rows": int((history["dated_observations"] == 0).sum()),
        "units_with_one_distinct_date": int((history["distinct_recorded_dates"] == 1).sum()),
        "units_with_two_or_more_distinct_dates": int((history["distinct_recorded_dates"] >= 2).sum()),
        "same_date_repeat_rows_total": int(history["same_date_repeat_rows"].sum()),
        "median_distinct_dates_per_unit": float(history["distinct_recorded_dates"].median()),
        "median_months_with_records_per_unit": float(history["months_with_records"].median()),
    }


# --------------------------------------------------------------- B. gaps
def recorded_date_gaps(ds: OperationalDataset, layer: str = DEFAULT_OBSERVATION_LAYER) -> pd.DataFrame:
    """Gaps between consecutive DISTINCT recorded dates per operation unit, one layer.

    Same-date repetitions (several rows for one unit on one date) collapse to
    one date for this calculation only; their observation IDs are listed in
    ``*_observation_ids`` so each gap stays traceable. Source rows are untouched.
    """
    part = _observations(ds, layer)
    columns = ["source_layer", "operation_unit_id", "operation_unit", "from_date", "to_date", "gap_days",
               "from_observation_ids", "to_observation_ids", "rows_on_to_date"]
    if part.empty:
        return pd.DataFrame(columns=columns)
    part = part[_nonblank(part["operation_unit_id"]) & part[DATE_BASIS].notna()]
    labels = label_maps(ds)["operation_unit"]
    rows = []
    for unit, group in part.groupby("operation_unit_id"):
        by_date = group.groupby(DATE_BASIS)["observation_id"].agg(lambda s: "|".join(sorted(s.astype(str))))
        dates = list(by_date.index)
        for prev, curr in zip(dates, dates[1:]):
            rows.append((layer, unit, labels.get(unit), prev.date(), curr.date(), int((curr - prev).days),
                         by_date[prev], by_date[curr], len(split_list(by_date[curr]))))
    return pd.DataFrame(rows, columns=columns)


def gap_distribution(gaps: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """Counts of gaps by length band (days) plus summary statistics. Neutral bands only."""
    if gaps.empty:
        return pd.DataFrame(columns=["gap_days_band", "gaps"]), {"gaps": 0}
    bands = pd.cut(gaps["gap_days"], bins=list(GAP_BINS), right=True, include_lowest=False)
    table = bands.value_counts(sort=False).rename_axis("gap_days_band").reset_index(name="gaps")
    table["gap_days_band"] = table["gap_days_band"].astype(str)
    stats = gaps["gap_days"].describe(percentiles=[0.25, 0.5, 0.75])
    summary = {"gaps": int(stats["count"]), "operation_units_with_gaps": int(gaps["operation_unit_id"].nunique()),
               "min_days": int(stats["min"]), "q1_days": float(stats["25%"]), "median_days": float(stats["50%"]),
               "q3_days": float(stats["75%"]), "max_days": int(stats["max"])}
    return table, summary


# --------------------------------------------------------------- C. area
def area_availability(ds: OperationalDataset) -> pd.DataFrame:
    """Per record_grain: rows, values present per area type, identity links."""
    area = ds.tables.get("area_evidence")
    if area is None:
        return pd.DataFrame()
    rows = []
    for grain, group in area.groupby("record_grain", dropna=False):
        row = {"record_grain": grain, "records": len(group)}
        for area_type in AREA_TYPES:
            row[f"with_{area_type}"] = int(group[area_type].notna().sum())
        row["linked_division"] = int(_nonblank(group["division_id"]).sum())
        row["linked_operation_unit"] = int(_nonblank(group["operation_unit_id"]).sum())
        row["identity_unresolved"] = int((group["identity_link_method"] == "unresolved").sum())
        row["with_effective_date"] = int(group["effective_date"].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows)


def _describe(values: pd.Series) -> dict[str, object]:
    v = pd.to_numeric(values, errors="coerce").dropna()
    if v.empty:
        return {"records_with_value": 0, "min_ha": None, "median_ha": None, "max_ha": None}
    return {"records_with_value": len(v), "min_ha": float(v.min()), "median_ha": float(v.median()),
            "max_ha": float(v.max())}


def area_distribution(ds: OperationalDataset) -> pd.DataFrame:
    """Distribution per area type and grain. Deliberately no sums across rows."""
    rows = []
    area = ds.tables.get("area_evidence")
    if area is not None:
        for grain, group in area.groupby("record_grain", dropna=False):
            for area_type in AREA_TYPES:
                rows.append({"area_type": area_type, "source": "area_evidence", "record_grain": grain,
                             **_describe(group[area_type])})
    units = ds.tables.get("operation_units")
    if units is not None:
        rows.append({"area_type": "tracker_imaging_area_ha", "source": "operation_units (snapshot)",
                     "record_grain": "tracker_operation_unit", **_describe(units["imaging_area_ha"])})
    return pd.DataFrame(rows)


def area_by_crop_maturity(ds: OperationalDataset) -> pd.DataFrame:
    area = ds.tables.get("area_evidence")
    if area is None:
        return pd.DataFrame()
    frame = area.assign(crop=area["crop"].fillna("").replace("", "(not recorded)"),
                        maturity=area["maturity"].fillna("").replace("", "(not recorded)"))
    rows = []
    for (grain, crop, maturity), group in frame.groupby(["record_grain", "crop", "maturity"], dropna=False):
        rows.append({"record_grain": grain, "crop": crop, "maturity": maturity, "records": len(group),
                     **{f"boundary_{k}": v for k, v in _describe(group["boundary_area_ha"]).items()}})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- D. overlap
def overlap_summary(ds: OperationalDataset) -> tuple[pd.DataFrame, dict[str, object]]:
    review = ds.tables.get("observation_overlap_review")
    if review is None:
        return pd.DataFrame(), {}
    table = review.groupby(["source_layers", "resolution"], dropna=False).agg(
        overlap_groups=("overlap_group_id", "size"),
        observations_referenced=("record_count", "sum"),
    ).reset_index()
    table["status"] = table["resolution"].map(
        lambda r: "confirmed duplicate (as supplied)" if r in CONFIRMED_DUPLICATE_RESOLUTIONS
        else "candidate overlap - not a confirmed duplicate")
    ids = review["observation_ids"].map(split_list).explode().dropna()
    summary = {
        "overlap_groups": len(review),
        "distinct_observations_referenced": int(ids.nunique()),
        "groups_marked_confirmed_duplicate": int(review["resolution"].isin(CONFIRMED_DUPLICATE_RESOLUTIONS).sum()),
        "within_single_layer_groups": int((~review["source_layers"].astype("string").str.contains(r"\|")).sum()),
        "date_basis": "recorded_date (as supplied)",
    }
    return table, summary
