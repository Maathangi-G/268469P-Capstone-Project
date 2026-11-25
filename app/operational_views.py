"""Streamlit views for the private operational dataset (presentation only).

All loading, validation and counting is done by ``agriflight.operational``.
This module only renders results and labels them honestly.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import streamlit as st

from agriflight.operational import summaries as s
from agriflight.operational.contract import (
    DEFAULT_OBSERVATION_LAYER,
    ENV_VAR,
    OBSERVATION_DATE_FIELDS,
    OBSERVATION_LAYERS,
)
from agriflight.operational.loader import PackageError, resolve_package_dir
from agriflight.operational.session import LoadedOperational, get_or_load
from agriflight.operational.validation import finding_counts, snapshot_table

PRIVATE_NOTICE = (
    "**Private operational dataset - pseudonymised REAL data.** Labels such as 'Farm 001' are anonymous, "
    "but dates, areas, costs and associations are real and confidential. Do not screenshot, export, share "
    "or commit this view. Nothing is written to disk."
)


def _table(frame: pd.DataFrame, height: int | None = None) -> None:
    kwargs = {"hide_index": True, "width": "stretch"}
    if height:
        kwargs["height"] = height
    st.dataframe(frame, **kwargs)


def _lkr(value: float | None) -> str:
    return "unknown" if value is None else f"LKR {value:,.2f}"


def load_for_session() -> tuple[LoadedOperational | None, str | None]:
    """Resolve AGRIFLIGHT_DATA_DIR and load (cached per session, in memory)."""
    try:
        root = resolve_package_dir()
        return get_or_load(st.session_state, root), None
    except PackageError as exc:
        return None, str(exc)


def render_load_error(message: str) -> None:
    st.error(
        f"**Private operational dataset not loaded.** {message}\n\n"
        "No synthetic or substitute data is shown in this mode. "
        f"Set `{ENV_VAR}` to the package root and restart the app, or switch back to synthetic mode."
    )
    st.code(f'$env:{ENV_VAR} = (Resolve-Path "<path to>\\AgriFlight_Integrated_v0_2").Path\n'
            "streamlit run app/app.py", language="powershell")


# ------------------------------------------------------------- A
def _divisions(loaded: LoadedOperational) -> None:
    ds = loaded.dataset
    st.subheader("Divisions and data readiness")
    st.caption(
        "One row per anonymous division (division_id). Farm and client come from the supplied foreign keys; "
        "IDs are never split. A farm key is a business parent, not a verified physical site or route stop."
    )
    base = s.division_table(ds)
    if base.empty:
        st.warning("scheduler_division_inputs.csv is not available.")
        return
    c1, c2, c3 = st.columns(3)
    clients = sorted(base["client"].dropna().unique())
    chosen_clients = c1.multiselect("Client", clients, placeholder="All clients")
    pool = base[base["client"].isin(chosen_clients)] if chosen_clients else base
    chosen_farms = c2.multiselect("Farm", sorted(pool["farm"].unique()), placeholder="All farms")
    pool = pool[pool["farm"].isin(chosen_farms)] if chosen_farms else pool
    chosen_divs = c3.multiselect("Division", sorted(pool["division"].unique()), placeholder="All divisions")
    view = pool[pool["division"].isin(chosen_divs)] if chosen_divs else pool

    ready, total = s.scheduler_ready_count(ds)
    m1, m2, m3 = st.columns(3)
    m1.metric("Divisions shown", len(view))
    m2.metric("With tracker imaging area", int(view["tracker_imaging_area_ha"].notna().sum()))
    m3.metric("scheduler_ready = True (all divisions)", f"{ready} of {total}")
    st.caption(
        "Area is the tracker snapshot (not contract-approved). Capture dates are the first/last *recorded* source "
        "dates - descriptive only, not confirmed completion or onboarding dates. Observation counts are source "
        "observations per layer, not completed flights. Vehicle evidence is historical budget evidence, "
        "not a mandatory access rule."
    )
    _table(view, height=380)

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Readiness blockers (divisions affected, current filter)**")
        _table(s.blocker_counts(ds, view["division_id"]))
    with right:
        if len(view) == 1:
            row = view.iloc[0]
            st.markdown(f"**Vehicle evidence for {row['division']} / {row['farm']}**")
            _table(s.division_vehicle_evidence(ds, row["farm_id"], row["division_id"]))
        else:
            st.info("Select a single division to see its farm- and division-level vehicle evidence.")


# ------------------------------------------------------------- B
def _observations(loaded: LoadedOperational) -> None:
    ds = loaded.dataset
    st.subheader("Operational records (source observations)")
    st.caption(
        "Three overlapping source layers are kept separate and never added together. Counts are source "
        "observations, not completed flights or completed services."
    )
    _table(s.layer_summary(ds))
    c1, c2 = st.columns(2)
    layer = c1.selectbox("Source layer", OBSERVATION_LAYERS, index=OBSERVATION_LAYERS.index(DEFAULT_OBSERVATION_LAYER))
    date_field = c2.selectbox("Date field for the time series", OBSERVATION_DATE_FIELDS)
    monthly, undated = s.observations_by_month(ds, layer, date_field)
    st.markdown(f"**Source observations per month - layer `{layer}`, by `{date_field}`**")
    st.caption(
        f"{undated} row(s) in this layer have no `{date_field}` and are counted separately, not plotted. "
        "A month with 0 means no source record in this layer; it is not a missed or cancelled visit. "
        "`last_recorded_capture_date` is not treated as a confirmed completion date."
    )
    if monthly.empty:
        st.info("No dated rows for this layer and date field.")
    else:
        st.bar_chart(monthly, x="month", y="source_observations")
    records = s.observation_records(ds, layer)
    st.markdown("**Missing-value summary for this layer**")
    _table(s.blank_summary(records))
    with st.expander(f"Source observation rows ({len(records)})"):
        _table(records, height=360)


# ------------------------------------------------------------- C
def _budget(loaded: LoadedOperational) -> None:
    ds = loaded.dataset
    labels = s.label_maps(ds)
    st.subheader("Budget and vehicle evidence")
    st.caption(
        "Historical budget documents (estimates unless explicitly recorded as actual). Tables below are "
        "separate layers and must not be added together. Rates are historical budget assumptions, not current prices."
    )
    trips_all = ds.tables.get("budget_fuel_trips")
    if trips_all is None:
        st.warning("budget_fuel_trips.csv is not available.")
        return

    st.markdown("### Fuel-trip estimates (one row per fuel_trip_id)")
    c1, c2, c3 = st.columns(3)
    purposes = c1.multiselect("Purpose category", sorted(trips_all["purpose_category"].dropna().unique()),
                              placeholder="All purposes (incl. mixed/unresolved)")
    scopes = c2.multiselect("Department scope", sorted(trips_all["department_scope"].dropna().unique()),
                            placeholder="All scopes (incl. mixed_or_unspecified)")
    farm_options = {labels["farm"].get(f, f): f for f in s.farms_with_linked_routes(ds)}
    farm_label = c3.selectbox("Linked farm (optional)", ["(no farm filter)"] + sorted(farm_options))
    farm_id = farm_options.get(farm_label)
    trips = s.fuel_trips_view(ds, farm_id=farm_id, purposes=purposes, scopes=scopes)
    totals = s.fuel_trip_totals(trips)
    if farm_id:
        st.warning(
            f"Showing trips whose itinerary is linked to {farm_label}. These are **shared trip estimates**: "
            "each trip's full estimate is shown once and is NOT this farm's allocated expenditure."
        )
    m = st.columns(4)
    m[0].metric("Fuel-trip rows (estimates)", totals["trip_rows"])
    m[1].metric("Estimated distance (km)", "unknown" if totals["estimated_distance_km"] is None
                else f"{totals['estimated_distance_km']:,.1f}")
    m[2].metric("Reported estimated fuel cost", _lkr(totals["reported_estimated_fuel_cost_lkr"]))
    m[3].metric("Recomputed fuel cost", _lkr(totals["recomputed_fuel_cost_lkr"]))
    st.caption(
        f"Sums over the selected estimate rows only - not actual spend, not a deduplicated annual budget and not a "
        f"forecast. Missing values excluded and counted: distance {totals['distance_missing']}, reported cost "
        f"{totals['reported_missing']}, recomputed cost {totals['recomputed_missing']}. "
        f"Per-record arithmetic: rows where |reported - recomputed| >= LKR 1: "
        f"{totals['rows_with_discrepancy_over_1_lkr']}. Smaller differences are within the LKR 1 reporting "
        "tolerance, not exact matches; the full reported value, recomputed value and difference are shown "
        "in the rows table. "
        f"Planned date outside the filename-derived period: {totals['rows_outside_filename_period']}. "
        "Recomputed fuel = distance / assumed km per litre x recorded LKR per litre."
    )
    st.markdown("**By budget period (filename-derived, not confirmed trip dates)**")
    _table(s.fuel_trips_by_period(trips))
    with st.expander(f"Fuel-trip rows ({len(trips)})"):
        _table(trips, height=360)

    st.markdown("### Accommodation and food estimates")
    acc = s.accommodation_view(ds)
    if not acc.empty:
        reported, rep_missing = s.safe_sum(acc["reported_estimated_cost_lkr"])
        recomputed, rec_missing = s.safe_sum(acc["recomputed_cost_lkr"])
        st.caption(
            f"{len(acc)} estimate line(s). Reported {_lkr(reported)} vs recomputed {_lkr(recomputed)} "
            f"(missing: {rep_missing} / {rec_missing}). Recomputed = unit rate x quantity x days or nights x team "
            "multiplier. Estimates do not prove an actual overnight stay; allocated to team/trip, not division."
        )
        _table(acc, height=280)

    st.markdown("### Historical vehicle-rate evidence")
    rates = s.vehicle_rates_view(ds)
    if not rates.empty:
        st.caption("Fuel price (LKR per litre) and efficiency (km per litre) as assumed in each source period. "
                   "Historical budget assumptions, not current quotes; validity dates are unconfirmed.")
        _table(s.vehicle_rate_summary(rates))
        with st.expander(f"Rate snapshots ({len(rates)})"):
            _table(rates, height=300)

    st.markdown("### Source-recorded expense summaries (rollups)")
    estimates, actuals = s.expense_lines_split(ds)
    st.caption(
        "Summary/rollup lines that OVERLAP the fuel and accommodation detail above "
        "(`is_additive_to_detail_tables = False`). Never add them to the detail tables."
    )
    st.markdown("**Estimate summary lines by category**")
    _table(s.expense_category_summary(estimates))
    st.markdown("**Lines explicitly recorded as actual (source-reported, unaudited, incomplete)**")
    st.caption("Kept separate from estimates. These are not a complete actual-expense history.")
    _table(actuals)

    st.markdown("### Subtotal reconciliation (supplied by the package)")
    st.caption(
        "Separate from the per-record arithmetic above: each source sheet's reported subtotal compared with the "
        "sum of its detail lines, with the check status as supplied by the package. Not all subtotals agree - "
        "mismatched and not-checkable subtotals are listed below and preserved as source issues. "
        "'agrees_within_LKR_1' means within tolerance, not an exact match."
    )
    counts, flagged = s.reconciliation_status(ds)
    _table(counts)
    if not flagged.empty:
        st.caption("Subtotal checks that do not agree within LKR 1 or cannot be checked. "
                   "Source values are retained, not repaired.")
        _table(flagged)

    st.markdown("### Farm/division vehicle evidence")
    st.caption("Historical budget/itinerary evidence of vehicle models. Not a confirmed mandatory-access rule "
               "and not current fleet availability.")
    _table(s.farm_vehicle_view(ds), height=280)


# ------------------------------------------------------------- D
def _quality(loaded: LoadedOperational) -> None:
    ds, findings = loaded.dataset, loaded.findings
    st.subheader("Data quality and readiness")

    st.markdown("### 1. Checks run by this application now")
    counts = finding_counts(findings) if not findings.empty else {"error": 0, "warning": 0, "info": 0}
    if counts["error"]:
        st.error(f"{counts['error']} error(s) and {counts['warning']} warning(s) found by the application checks.")
    else:
        st.info(
            f"No structural errors from the application checks ({counts['warning']} warning(s)). "
            "This covers columns, keys, foreign keys, hierarchy, parsing and snapshot reconciliation only. "
            "It does not resolve the source issues below or confirm business readiness."
        )
    if not findings.empty:
        _table(findings)
    with st.expander("Snapshot reconciliation against docs/schema.json (reference counts, not results)"):
        _table(snapshot_table(ds))

    st.markdown("### 2. Findings supplied with the dataset package")
    issues = ds.tables.get("data_quality_issues")
    if issues is not None:
        open_count = int((issues["resolution_status"] == "open").sum())
        st.caption(f"data_quality_issues.csv: {len(issues)} record-level issue(s), {open_count} open. "
                   "Source date and subtotal conflicts are preserved as reported.")
        _table(issues.groupby(["severity", "issue_code", "resolution_status"]).size().reset_index(name="issues"))
        with st.expander("Issue rows"):
            _table(issues, height=300)
    report = ds.supplied_validation
    if report:
        st.caption(
            f"docs/validation_results.json (supplied, not re-run by this app): "
            f"{report.get('checks_passed')} of {report.get('checks_total')} package checks passed."
        )

    st.markdown("### 3. Unresolved requirements")
    st.caption("Derived from what the dataset contains. Nothing here is marked resolved by loading successfully.")
    _table(s.readiness_requirements(ds))
    st.markdown("**Input-contract templates**")
    _table(ds.templates)
    rules = ds.tables.get("rules_and_assumptions")
    if rules is not None:
        st.markdown("**Rules and assumptions (as supplied)**")
        _table(rules)


def render(loaded: LoadedOperational, status_renderer: Callable[[], None]) -> None:
    st.warning(PRIVATE_NOTICE, icon="🔒")
    st.caption(f"Package folder: {loaded.dataset.root.name} (from {ENV_VAR}); {len(loaded.dataset.tables)} tables loaded.")
    tabs = st.tabs(["Divisions & readiness", "Operational records", "Budget & vehicle evidence",
                    "Data quality", "Project Status"])
    with tabs[0]:
        _divisions(loaded)
    with tabs[1]:
        _observations(loaded)
    with tabs[2]:
        _budget(loaded)
    with tabs[3]:
        _quality(loaded)
    with tabs[4]:
        status_renderer()
