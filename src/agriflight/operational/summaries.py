"""Descriptive, read-only summaries of the operational dataset.

Counting safeguards (see docs/operational_dataset.md):
* Child counts are computed by group-by and then *mapped* onto the parent
  table, never by merging a one-to-many table into it, so parent rows and
  their amounts are never duplicated.
* A fuel trip is counted once per fuel_trip_id. Filtering by farm selects
  the trips whose route links to that farm; it never copies or apportions
  the trip's cost to the farm.
* Money is summed only within one table and one record_type. Summary
  expense lines are never added to fuel or accommodation detail.
* Sums use min_count=1 and report how many values were missing, so an
  unknown amount is never treated as zero.
* Observation counts are "source observations", not completed flights.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from agriflight.operational.contract import OBSERVATION_LAYERS
from agriflight.operational.loader import OperationalDataset
from agriflight.operational.validation import split_list

DISCREPANCY_THRESHOLD_LKR = 1.0  # same tolerance the package uses ("agrees within LKR 1")
SHARED_TRIP_LABEL = "shared trip estimate - not allocated to this farm"


# ---------------------------------------------------------------- helpers
def _labels(ds: OperationalDataset, table: str, key: str, label: str) -> dict[str, str]:
    frame = ds.tables.get(table)
    if frame is None or key not in frame.columns or label not in frame.columns:
        return {}
    return dict(zip(frame[key].astype(str), frame[label].astype(str)))


def label_maps(ds: OperationalDataset) -> dict[str, dict[str, str]]:
    """Anonymous display labels supplied by the package (e.g. 'Farm 001')."""
    return {
        "client": _labels(ds, "clients", "client_id", "client_name"),
        "farm": _labels(ds, "farms", "farm_id", "farm_name"),
        "division": _labels(ds, "divisions", "division_id", "division_name"),
        "vehicle_model": _labels(ds, "vehicle_models", "vehicle_model_id", "vehicle_model"),
        "route": _labels(ds, "route_index", "route_id", "route_name"),
        "operation_unit": _labels(ds, "operation_units", "operation_unit_id", "operation_name"),
    }


def _map(series: pd.Series, mapping: dict[str, str]) -> pd.Series:
    return series.astype("string").map(lambda v: mapping.get(v, pd.NA) if pd.notna(v) and v != "" else pd.NA)


def safe_sum(series: pd.Series) -> tuple[float | None, int]:
    """(sum of known values or None if none known, number of missing values)."""
    numeric = pd.to_numeric(series, errors="coerce")
    missing = int(numeric.isna().sum())
    total = numeric.sum(min_count=1)
    return (None if pd.isna(total) else float(total)), missing


def blank_summary(frame: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    cols = [c for c in (columns or frame.columns) if c in frame.columns]
    total = len(frame)
    rows = []
    for c in cols:
        missing = int((frame[c].isna() | (frame[c].astype("string").str.strip() == "")).sum())
        rows.append((c, missing, round(100 * missing / total, 1) if total else 0.0))
    return pd.DataFrame(rows, columns=["field", "missing_values", "missing_percent"])


# ------------------------------------------------- A. divisions/readiness
def division_table(ds: OperationalDataset, client_ids: Iterable[str] = (), farm_ids: Iterable[str] = (),
                   division_ids: Iterable[str] = ()) -> pd.DataFrame:
    sched = ds.tables.get("scheduler_division_inputs")
    if sched is None:
        return pd.DataFrame()
    labels = label_maps(ds)
    view = sched.copy()
    for column, chosen in (("client_id", client_ids), ("farm_id", farm_ids), ("division_id", division_ids)):
        chosen = list(chosen)
        if chosen:
            view = view[view[column].isin(chosen)]

    out = pd.DataFrame({
        "client": _map(view["client_id"], labels["client"]),
        "client_id": view["client_id"],
        "farm": view["farm_name"],
        "farm_id": view["farm_id"],
        "division": view["division_name"],
        "division_id": view["division_id"],
        "tracker_imaging_area_ha": view["tracker_imaging_area_ha"],
        "area_approval_status": view["area_approval_status"],
        "linked_operation_units": view["operation_unit_ids"].map(lambda v: len(split_list(v))),
        "first_recorded_capture_date": view["first_recorded_capture_date"],
        "last_recorded_capture_date": view["last_recorded_capture_date"],
    })

    obs = ds.tables.get("flight_observations")
    for layer in OBSERVATION_LAYERS:
        col = f"source_obs_{layer}"
        if obs is None:
            out[col] = pd.NA
            continue
        counts = obs[obs["source_layer"] == layer].groupby("division_id").size()
        out[col] = view["division_id"].map(counts).fillna(0).astype("Int64")

    fve = ds.tables.get("farm_vehicle_evidence")
    if fve is not None:
        div_counts = fve[fve["target_level"] == "division"].groupby("target_id").size()
        farm_counts = fve[fve["target_level"] == "farm"].groupby("target_id").size()
        out["vehicle_evidence_division_level"] = view["division_id"].map(div_counts).fillna(0).astype("Int64")
        out["vehicle_evidence_farm_level"] = view["farm_id"].map(farm_counts).fillna(0).astype("Int64")
    out["vehicle_models_in_evidence"] = view["vehicle_model_evidence_ids"].map(
        lambda v: ", ".join(labels["vehicle_model"].get(i, i) for i in split_list(v)))
    out["scheduler_ready"] = view["scheduler_ready"]
    out["readiness_blocker_count"] = view["readiness_blockers"].map(lambda v: len(split_list(v)))
    out["readiness_blockers"] = view["readiness_blockers"].map(lambda v: ", ".join(split_list(v)))
    return out.reset_index(drop=True)


def blocker_counts(ds: OperationalDataset, division_ids: Iterable[str] | None = None) -> pd.DataFrame:
    sched = ds.tables.get("scheduler_division_inputs")
    if sched is None:
        return pd.DataFrame(columns=["readiness_blocker", "divisions"])
    if division_ids is not None:
        sched = sched[sched["division_id"].isin(list(division_ids))]
    exploded = sched["readiness_blockers"].map(split_list).explode().dropna()
    counts = exploded.value_counts()
    return counts.rename_axis("readiness_blocker").reset_index(name="divisions")


def division_vehicle_evidence(ds: OperationalDataset, farm_id: str, division_id: str | None = None) -> pd.DataFrame:
    fve = ds.tables.get("farm_vehicle_evidence")
    if fve is None:
        return pd.DataFrame()
    mask = (fve["target_level"] == "farm") & (fve["target_id"] == farm_id)
    if division_id:
        mask |= (fve["target_level"] == "division") & (fve["target_id"] == division_id)
    return farm_vehicle_view(ds, fve[mask])


# ------------------------------------------------ B. operational records
def layer_summary(ds: OperationalDataset) -> pd.DataFrame:
    obs = ds.tables.get("flight_observations")
    if obs is None:
        return pd.DataFrame()
    rows = []
    for layer in OBSERVATION_LAYERS:
        part = obs[obs["source_layer"] == layer]
        rows.append({
            "source_layer": layer,
            "source_observations": len(part),
            "with_recorded_actual_date": int(part["recorded_actual_date"].notna().sum()),
            "without_recorded_actual_date": int(part["recorded_actual_date"].isna().sum()),
            "with_planned_date": int(part["planned_date"].notna().sum()),
            "linked_to_division": int(part["division_id"].fillna("").ne("").sum()),
            "identity_unresolved": int((part["identity_link_method"] == "unresolved").sum()),
        })
    return pd.DataFrame(rows)


def observations_by_month(ds: OperationalDataset, layer: str, date_field: str) -> tuple[pd.DataFrame, int]:
    """Monthly count of source observations in one layer, plus undated rows.

    The month range is continuous; a month with 0 means no source record in
    that layer, not a missed or cancelled visit.
    """
    obs = ds.tables.get("flight_observations")
    if obs is None:
        return pd.DataFrame(columns=["month", "source_observations"]), 0
    part = obs[obs["source_layer"] == layer]
    dates = part[date_field]
    undated = int(dates.isna().sum())
    dated = dates.dropna()
    if dated.empty:
        return pd.DataFrame(columns=["month", "source_observations"]), undated
    months = dated.dt.to_period("M")
    counts = months.value_counts().sort_index()
    full = pd.period_range(counts.index.min(), counts.index.max(), freq="M")
    counts = counts.reindex(full, fill_value=0)
    frame = pd.DataFrame({"month": counts.index.astype(str), "source_observations": counts.values})
    return frame, undated


def observation_records(ds: OperationalDataset, layer: str) -> pd.DataFrame:
    obs = ds.tables.get("flight_observations")
    if obs is None:
        return pd.DataFrame()
    labels = label_maps(ds)
    part = obs[obs["source_layer"] == layer].copy()
    part.insert(2, "division", _map(part["division_id"], labels["division"]))
    part.insert(3, "operation_unit", _map(part["operation_unit_id"], labels["operation_unit"]))
    hidden = ["person_ids"]  # opaque person tokens are not needed for this view
    return part.drop(columns=[c for c in hidden if c in part.columns]).reset_index(drop=True)


# ------------------------------------------- C. budget/vehicle evidence
def route_link_counts(ds: OperationalDataset) -> pd.DataFrame:
    links = ds.tables.get("route_entity_links")
    if links is None:
        return pd.DataFrame(columns=["route_id", "linked_entities", "linked_farms"])
    grouped = links.groupby("route_id")
    return pd.DataFrame({
        "linked_entities": grouped.size(),
        "linked_farms": grouped["farm_id"].agg(lambda s: s.dropna()[s.dropna() != ""].nunique()),
    }).reset_index()


def routes_linked_to_farm(ds: OperationalDataset, farm_id: str) -> set[str]:
    links = ds.tables.get("route_entity_links")
    if links is None:
        return set()
    mask = (links["farm_id"] == farm_id) | ((links["target_level"] == "farm") & (links["target_id"] == farm_id))
    return set(links.loc[mask.fillna(False), "route_id"].astype(str))


def farms_with_linked_routes(ds: OperationalDataset) -> list[str]:
    links = ds.tables.get("route_entity_links")
    if links is None:
        return []
    farms = links["farm_id"].dropna()
    return sorted(farms[farms != ""].unique())


def fuel_trips_view(ds: OperationalDataset, farm_id: str | None = None,
                    purposes: Iterable[str] = (), scopes: Iterable[str] = ()) -> pd.DataFrame:
    """One row per fuel_trip_id. A farm filter keeps linked shared trips without
    duplicating or allocating their cost."""
    trips = ds.tables.get("budget_fuel_trips")
    if trips is None:
        return pd.DataFrame()
    view = trips.copy()
    purposes, scopes = list(purposes), list(scopes)
    if purposes:
        view = view[view["purpose_category"].isin(purposes)]
    if scopes:
        view = view[view["department_scope"].isin(scopes)]
    if farm_id:
        view = view[view["route_id"].isin(routes_linked_to_farm(ds, farm_id))]
    labels = label_maps(ds)
    counts = route_link_counts(ds).set_index("route_id")
    view.insert(1, "itinerary", _map(view["route_id"], labels["route"]))
    view.insert(2, "vehicle_model", _map(view["vehicle_model_id"], labels["vehicle_model"]))
    view["route_linked_entities"] = view["route_id"].map(counts["linked_entities"]).astype("Int64")
    view["route_linked_farms"] = view["route_id"].map(counts["linked_farms"]).astype("Int64")
    view["cost_basis"] = SHARED_TRIP_LABEL if farm_id else "whole trip estimate (unallocated)"
    view = view.drop(columns=[c for c in ("person_id",) if c in view.columns])
    assert view["fuel_trip_id"].is_unique, "fuel trip rows must not be duplicated"
    return view.reset_index(drop=True)


def fuel_trip_totals(trips: pd.DataFrame) -> dict[str, object]:
    distance, distance_missing = safe_sum(trips.get("estimated_distance_km", pd.Series(dtype="Float64")))
    reported, reported_missing = safe_sum(trips.get("reported_estimated_fuel_cost_lkr", pd.Series(dtype="Float64")))
    recomputed, recomputed_missing = safe_sum(trips.get("recomputed_fuel_cost_lkr", pd.Series(dtype="Float64")))
    diff = pd.to_numeric(trips.get("reported_minus_recomputed_lkr", pd.Series(dtype="Float64")), errors="coerce")
    return {
        "trip_rows": len(trips),
        "distinct_fuel_trip_ids": int(trips["fuel_trip_id"].nunique()) if "fuel_trip_id" in trips else 0,
        "estimated_distance_km": distance, "distance_missing": distance_missing,
        "reported_estimated_fuel_cost_lkr": reported, "reported_missing": reported_missing,
        "recomputed_fuel_cost_lkr": recomputed, "recomputed_missing": recomputed_missing,
        "rows_with_discrepancy_over_1_lkr": int((diff.abs() >= DISCREPANCY_THRESHOLD_LKR).sum()),
        "rows_outside_filename_period": int((trips.get("date_check", pd.Series(dtype="string")) == "outside_filename_period").sum()),
    }


def fuel_trips_by_period(trips: pd.DataFrame) -> pd.DataFrame:
    if trips.empty:
        return pd.DataFrame()
    grouped = trips.groupby(["period_start", "period_end"], dropna=False)
    out = grouped.agg(
        trip_rows=("fuel_trip_id", "size"),
        estimated_distance_km=("estimated_distance_km", lambda s: s.sum(min_count=1)),
        reported_estimated_fuel_cost_lkr=("reported_estimated_fuel_cost_lkr", lambda s: s.sum(min_count=1)),
        recomputed_fuel_cost_lkr=("recomputed_fuel_cost_lkr", lambda s: s.sum(min_count=1)),
        missing_reported_cost=("reported_estimated_fuel_cost_lkr", lambda s: int(s.isna().sum())),
    ).reset_index()
    for c in ("period_start", "period_end"):
        out[c] = out[c].dt.date
    return out


def accommodation_view(ds: OperationalDataset) -> pd.DataFrame:
    acc = ds.tables.get("accommodation_estimates")
    if acc is None:
        return pd.DataFrame()
    return acc.drop(columns=[c for c in ("person_ids",) if c in acc.columns]).reset_index(drop=True)


def vehicle_rates_view(ds: OperationalDataset) -> pd.DataFrame:
    rates = ds.tables.get("vehicle_rate_evidence")
    if rates is None:
        return pd.DataFrame()
    view = rates.copy()
    view.insert(1, "vehicle_model", _map(view["vehicle_model_id"], label_maps(ds)["vehicle_model"]))
    return view.reset_index(drop=True)


def vehicle_rate_summary(rates: pd.DataFrame) -> pd.DataFrame:
    if rates.empty:
        return pd.DataFrame()
    out = rates.groupby(["vehicle_model", "fuel_type"], dropna=False).agg(
        rate_snapshots=("rate_id", "size"),
        earliest_source_period=("source_period_start", "min"),
        latest_source_period=("source_period_end", "max"),
        min_fuel_price_lkr_per_l=("fuel_price_lkr_per_l", "min"),
        max_fuel_price_lkr_per_l=("fuel_price_lkr_per_l", "max"),
        min_efficiency_km_per_l=("assumed_efficiency_km_per_l", "min"),
        max_efficiency_km_per_l=("assumed_efficiency_km_per_l", "max"),
    ).reset_index()
    for c in ("earliest_source_period", "latest_source_period"):
        out[c] = out[c].dt.date
    return out


def expense_lines_split(ds: OperationalDataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(estimate summary lines, actual_recorded lines) - never combined."""
    lines = ds.tables.get("budget_expense_lines")
    if lines is None:
        return pd.DataFrame(), pd.DataFrame()
    return (lines[lines["record_type"] == "estimate"].reset_index(drop=True),
            lines[lines["record_type"] == "actual_recorded"].reset_index(drop=True))


def expense_category_summary(lines: pd.DataFrame) -> pd.DataFrame:
    if lines.empty:
        return pd.DataFrame(columns=["record_type", "cost_category", "summary_lines", "amount_lkr", "missing_amounts"])
    return lines.groupby(["record_type", "cost_category"], dropna=False).agg(
        summary_lines=("expense_line_id", "size"),
        amount_lkr=("amount_lkr", lambda s: s.sum(min_count=1)),
        missing_amounts=("amount_lkr", lambda s: int(s.isna().sum())),
    ).reset_index().sort_values(["record_type", "cost_category"])


def reconciliation_status(ds: OperationalDataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    rec = ds.tables.get("budget_reconciliation")
    if rec is None:
        return pd.DataFrame(), pd.DataFrame()
    counts = rec.groupby(["detail_table", "check_status"]).size().reset_index(name="subtotal_checks")
    flagged = rec[rec["check_status"] != "agrees_within_LKR_1"].reset_index(drop=True)
    return counts, flagged


def farm_vehicle_view(ds: OperationalDataset, frame: pd.DataFrame | None = None) -> pd.DataFrame:
    fve = ds.tables.get("farm_vehicle_evidence") if frame is None else frame
    if fve is None:
        return pd.DataFrame()
    labels = label_maps(ds)
    view = fve.copy()
    target_label = view.apply(
        lambda r: labels["division"].get(r["target_id"]) if r["target_level"] == "division"
        else labels["farm"].get(r["target_id"]), axis=1) if not view.empty else pd.Series(dtype="string")
    view.insert(1, "target", target_label)
    view.insert(2, "farm", _map(view["farm_id"], labels["farm"]))
    view.insert(3, "vehicle_model", _map(view["vehicle_model_id"], labels["vehicle_model"]))
    return view.reset_index(drop=True)


# ----------------------------------------------- D. readiness evidence
def readiness_requirements(ds: OperationalDataset) -> pd.DataFrame:
    """What the dataset itself supplies for each unresolved requirement.

    Status is never 'resolved'; at most 'records present - needs review'.
    """
    def nonblank(table: str, column: str) -> int | None:
        frame = ds.tables.get(table)
        if frame is None or column not in frame.columns:
            return None
        return int((frame[column].notna() & (frame[column].astype("string").str.strip() != "")).sum())

    def template_rows(name: str) -> int | None:
        match = ds.templates[ds.templates["template"] == name]
        return None if match.empty else int(match["rows"].iloc[0])

    def blocker(code: str) -> int | None:
        sched = ds.tables.get("scheduler_division_inputs")
        if sched is None:
            return None
        return int(sched["readiness_blockers"].map(lambda v: code in split_list(v)).sum())

    items = [
        ("Verified service completion", "flight_observations.completed_service_id (non-blank)", nonblank("flight_observations", "completed_service_id")),
        ("Verified service completion", "service_completion_template rows", template_rows("service_completion_template")),
        ("Confirmed completion date", "scheduler_division_inputs.last_confirmed_service_completion_date (non-blank)", nonblank("scheduler_division_inputs", "last_confirmed_service_completion_date")),
        ("Due date", "scheduler_division_inputs.next_due_date (non-blank)", nonblank("scheduler_division_inputs", "next_due_date")),
        ("Measured daily hectares", "flight_observations.actual_daily_covered_ha (non-blank)", nonblank("flight_observations", "actual_daily_covered_ha")),
        ("Measured daily hectares", "daily_coverage_template rows", template_rows("daily_coverage_template")),
        ("Pilot availability", "pilot_availability_template rows", template_rows("pilot_availability_template")),
        ("Physical vehicle availability", "physical_vehicle_template rows", template_rows("physical_vehicle_template")),
        ("Base/depot location", "divisions blocked by base_location_missing", blocker("base_location_missing")),
        ("Verified access point", "divisions blocked by access_point_unconfirmed", blocker("access_point_unconfirmed")),
    ]
    rows = []
    for requirement, evidence, value in items:
        if value is None:
            status = "not checkable (table/column missing)"
        elif evidence.startswith("divisions blocked"):
            status = "unresolved" if value > 0 else "no blocker recorded - needs review"
        else:
            status = "unresolved (no records)" if value == 0 else "records present - needs review"
        rows.append((requirement, evidence, value, status))
    return pd.DataFrame(rows, columns=["requirement", "evidence_checked", "count", "status"])


def scheduler_ready_count(ds: OperationalDataset) -> tuple[int, int]:
    sched = ds.tables.get("scheduler_division_inputs")
    if sched is None:
        return 0, 0
    return int(sched["scheduler_ready"].fillna(False).astype(bool).sum()), len(sched)
