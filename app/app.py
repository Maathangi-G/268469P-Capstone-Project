"""AgriFlight AI - Data Readiness Dashboard (Streamlit).

The UI only renders results. All loading, validation and summarising lives in
the ``agriflight`` package so it can be tested without Streamlit.

Privacy: uploaded files are processed in memory only. Nothing is written to
disk, and no export is created by loading or refreshing this page.

Run from the repository root:
    streamlit run app/app.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from agriflight import __version__
from agriflight.data.loader import DataLoadError, load_operations_csv
from agriflight.data.schema import ALLOWED_RECORD_TYPES, EXPECTED_COLUMNS, SYNTHETIC_ORIGIN
from agriflight.data.validation import ISSUE_CODES, ValidationReport, validate_operations
from agriflight.services import project_status as status
from agriflight.services.data_summary import missing_value_summary, summarize_dataset

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = REPO_ROOT / "data" / "sample" / "demo_operations.csv"
DEMO_LABEL = "Bundled synthetic demo"
UPLOAD_LABEL = "Upload a CSV (demonstration schema)"
BLANK = "(blank)"

st.set_page_config(page_title="AgriFlight AI - Data Readiness", layout="wide")


@st.cache_data(show_spinner=False)
def _load_demo(path: str) -> pd.DataFrame:
    return load_operations_csv(path)


def _load_selected() -> tuple[pd.DataFrame | None, str, str | None]:
    """Return (frame, source description, load error message)."""
    st.sidebar.header("Data source")
    choice = st.sidebar.radio("Choose input", [DEMO_LABEL, UPLOAD_LABEL], label_visibility="collapsed")
    if choice == DEMO_LABEL:
        try:
            return _load_demo(str(DEMO_PATH)), "Bundled file data/sample/demo_operations.csv", None
        except DataLoadError as exc:
            return None, "Bundled demo", str(exc)

    st.sidebar.caption(
        "Only CSV files in the documented demonstration schema are supported. "
        "Raw company workbooks need a separate, reviewed adapter and are not accepted here. "
        "The upload is read in memory and never saved."
    )
    uploaded = st.sidebar.file_uploader("CSV file", type=["csv"])
    if uploaded is None:
        return None, "No file uploaded", None
    try:
        return load_operations_csv(uploaded.getvalue()), f"Uploaded file: {uploaded.name}", None
    except DataLoadError as exc:
        return None, f"Uploaded file: {uploaded.name}", str(exc)


def _data_notice(frame: pd.DataFrame | None, source: str) -> None:
    if source.startswith("Bundled"):
        st.warning(
            "**Synthetic demonstration data.** Every row is fictional (`data_origin = synthetic_demo`) "
            "and includes intentional quality issues. No real farm, client or company record is shown.",
            icon="⚠️",
        )
    else:
        st.info(f"{source}. Held in memory for this session only; not written to disk.")
        if frame is not None and "data_origin" in frame.columns:
            origins = set(frame["data_origin"].astype(str).str.strip()) - {"", SYNTHETIC_ORIGIN}
            if origins:
                st.warning(
                    "This file contains rows whose `data_origin` is not `synthetic_demo`. "
                    "Do not commit, publish or screenshot non-synthetic data.",
                    icon="🔒",
                )


def _overview(frame: pd.DataFrame | None, source: str) -> None:
    st.subheader("Overview")
    st.markdown(
        "AgriFlight AI is a capstone decision-support prototype for agricultural drone-operation "
        "planning. This milestone establishes **data readiness**: a documented schema, loading, "
        "validation and inspection. It does **not** yet predict coverage, schedule visits or "
        "assess cadence compliance."
    )
    st.caption(f"Milestone: {status.MILESTONE}")
    if frame is None:
        st.info("No data loaded. Choose the bundled demo or upload a CSV in the sidebar.")
        return

    summary = summarize_dataset(frame)
    c1, c2, c3 = st.columns(3)
    c1.metric("Source records (rows)", summary.source_record_count)
    c2.metric("Distinct operating units", summary.distinct_operating_units)
    c3.metric("Distinct clients", summary.distinct_clients)
    st.caption(
        "Counts are rows in the source file. A row is not a completed flight or a completed service; "
        "planned visits, capture observations and trial visits are counted separately and never added together."
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Source records by record type**")
        st.dataframe(summary.record_type_counts, hide_index=True, width="stretch")
    with right:
        st.markdown("**Observed valid date range** (invalid or blank dates excluded)")
        st.dataframe(summary.date_ranges, hide_index=True, width="stretch")


def _explorer(frame: pd.DataFrame | None) -> None:
    st.subheader("Data Explorer")
    st.caption(
        "Expected columns: " + ", ".join(f"`{c}`" for c in EXPECTED_COLUMNS)
        + ". Raw company workbooks require a separate adapter (planned) and cannot be uploaded here."
    )
    if frame is None:
        st.info("No data loaded.")
        return

    view = frame.copy()
    c1, c2 = st.columns(2)
    if "operating_unit_id" in view.columns:
        units_col = view["operating_unit_id"].astype(str).str.strip().replace("", BLANK)
        units = sorted(units_col.unique())
        chosen_units = c1.multiselect("Operating unit", units, placeholder="All units")
        if chosen_units:
            view = view[units_col.loc[view.index].isin(chosen_units)]
    if "record_type" in view.columns:
        types_col = view["record_type"].astype(str).str.strip().replace("", BLANK)
        present = list(dict.fromkeys(list(ALLOWED_RECORD_TYPES) + sorted(types_col.unique())))
        chosen_types = c2.multiselect("Record type", present, placeholder="All record types")
        if chosen_types:
            view = view[types_col.loc[view.index].isin(chosen_types)]

    st.caption(f"Showing {len(view)} of {len(frame)} source rows. `source_row` is the spreadsheet row number.")
    st.dataframe(view, hide_index=True, width="stretch")


def _quality(frame: pd.DataFrame | None, report: ValidationReport | None, load_error: str | None) -> None:
    st.subheader("Data Quality")
    if load_error:
        st.error(f"The file could not be loaded, so it was not validated.\n\n{load_error}")
        return
    if frame is None or report is None:
        st.info("No data loaded.")
        return

    if report.passed:
        st.success(
            f"No validation errors in {report.row_count} rows "
            f"({report.warning_count} warning(s)). This checks format and schema rules only; "
            "it does not confirm that records are complete or reconciled."
        )
    else:
        st.error(
            f"Validation failed: {report.error_count} error(s) across {report.rows_with_errors} row(s)"
            + (f"; missing column(s): {', '.join(report.missing_columns)}" if report.missing_columns else "")
            + f". {report.warning_count} warning(s). No rows were removed or altered."
        )

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("**Issue counts**")
        st.dataframe(report.counts_by_code(), hide_index=True, width="stretch")
    with c2:
        st.markdown("**Missing-value summary**")
        st.dataframe(missing_value_summary(frame), hide_index=True, width="stretch")

    st.markdown("**Issue details**")
    issues = report.issues
    severities = sorted(issues["severity"].unique()) if not issues.empty else []
    chosen = st.multiselect("Severity", severities, default=severities)
    st.dataframe(issues[issues["severity"].isin(chosen)], hide_index=True, width="stretch")

    with st.expander("Issue code reference"):
        st.dataframe(
            pd.DataFrame(list(ISSUE_CODES.items()), columns=["issue_code", "meaning"]),
            hide_index=True,
            width="stretch",
        )


def _status() -> None:
    st.subheader("Project Status")
    st.markdown(f"**{status.MILESTONE}**. This is a foundation milestone, not a model or a scheduler.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Implemented and covered by automated tests**")
        st.markdown("\n".join(f"- {item}" for item in status.IMPLEMENTED))
    with c2:
        st.markdown("**Pending (planned, not implemented)**")
        st.markdown("\n".join(f"- {item}" for item in status.PENDING))

    policy = status.CADENCE_POLICY
    st.markdown("**Recurring-service cadence policy**")
    st.info(
        f"Target: {policy['target_interval_days']} days, tolerance +/-{policy['tolerance_days']} days. "
        f"{policy['status']}\n\n{policy['note']}"
    )

    st.markdown("**Outstanding decisions**")
    st.dataframe(
        pd.DataFrame(status.OPEN_DECISIONS, columns=["topic", "decision needed"]),
        hide_index=True,
        width="stretch",
    )
    st.markdown("**Not claimed in this milestone**")
    st.markdown("\n".join(f"- {item}" for item in status.NOT_CLAIMED))


def main() -> None:
    st.title("AgriFlight AI - Data Readiness Dashboard")
    st.caption(f"Capstone prototype v{__version__} - local use only")

    frame, source, load_error = _load_selected()
    report = validate_operations(frame) if frame is not None else None
    _data_notice(frame, source)
    if load_error:
        st.error(f"Could not load data: {load_error}")

    tab_overview, tab_explorer, tab_quality, tab_status = st.tabs(
        ["Overview", "Data Explorer", "Data Quality", "Project Status"]
    )
    with tab_overview:
        _overview(frame, source)
    with tab_explorer:
        _explorer(frame)
    with tab_quality:
        _quality(frame, report, load_error)
    with tab_status:
        _status()


main()
