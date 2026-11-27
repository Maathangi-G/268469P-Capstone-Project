"""Streamlit view: rule-based scheduling baseline on the fictional demo scenario."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from agriflight.scheduling import DRAFT_NOTICE, ScenarioError, load_scenario, run_scenario

DEMO_DIR = Path(__file__).resolve().parents[1] / "examples" / "scheduling_demo"


def _table(frame, height=None) -> None:
    kwargs = {"hide_index": True, "width": "stretch"}
    if height:
        kwargs["height"] = height
    st.dataframe(frame, **kwargs)


def render() -> None:
    st.subheader("Scheduling baseline (rule-based, draft)")
    st.warning(
        "**Synthetic demonstration scenario.** Jobs, teams, travel times, work rates and cost rates in "
        "`examples/scheduling_demo` are entirely fictional. This is not a company plan and does not make any real "
        "division scheduler-ready.", icon="⚠️")
    st.info(DRAFT_NOTICE)
    try:
        run = run_scenario(load_scenario(DEMO_DIR))
    except ScenarioError as exc:
        st.error(f"Scenario inputs are missing or invalid: {exc}")
        return
    result, f = run.result, run.frames
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jobs scheduled by baseline", f"{len(result.assignments)} of {len(result.scenario.jobs)}")
    c2.metric("Bundle-day routes", len(result.routes))
    total = run.cost_summary["estimated_known_total_lkr"]
    c3.metric("Estimated known cost", "unknown" if total is None else f"LKR {total:,.0f}")
    c4.metric("Independent checks", "all passed" if run.checks_passed else "FAILED")
    if not run.cost_summary["coverage_complete"]:
        st.caption("Known estimated cost only - not a complete operating budget. Cost coverage incomplete "
                   "(missing rates are not treated as zero): " + ", ".join(run.cost_summary["missing_components"]))
    st.caption("Shared physical resources are reserved for the whole day by the first bundle (in bundle_id order) "
               "that uses them; within-day handovers are not supported in version 1.")
    st.caption("Rule: each day, each bundle (by ID) takes the eligible job with the earliest planning due date "
               "that still fits travel, setup, work, access window, break and return-to-depot; ties by travel time "
               "then job ID. Preferred windows are soft; hard dates, access, availability and working limits are not.")

    st.markdown("**Daily itineraries (local Asia/Colombo times)**")
    _table(f["itinerary"], height=320)
    st.markdown("**Job assignments and date-window deviations**")
    st.caption("Three separate soft windows: operational +/-5 days and proposal +/-3 days around the planning due date "
               "(deviation = days outside, max(0, |offset| - tolerance)), and each job's own supplied preferred "
               "window (signed: negative = early, positive = late). None of them excludes a job.")
    _table(f["assignments"])
    st.markdown("**Not scheduled by this baseline** (structured reasons; not a proof of infeasibility)")
    _table(f["unassigned"])
    st.markdown("**Estimated costs per bundle-day** (estimates from fictional rates; not actual expenditure)")
    _table(f["costs"], height=260)
    with st.expander("Bundle-day status and resource conflicts"):
        _table(f["bundle_days"])
    with st.expander("Independent result checks"):
        _table(f["checks"])
    with st.expander("Assumptions and scenario provenance"):
        _table(f["assumptions"])
    st.code("python scripts/run_schedule.py", language="powershell")
    _comparison()


SCENARIOS = {"scheduling_demo (11 jobs)": DEMO_DIR} | {
    p.name: p for p in sorted((DEMO_DIR.parent / "scheduling_comparison").glob("c*")) if p.is_dir()}
CMP_KEY = "_scheduler_comparison"


def _comparison() -> None:
    from agriflight.scheduling.comparison import OBJECTIVE_PRIORITIES, assess, compare_folder, scenario_hash
    from agriflight.scheduling.optimizer import OptimizerConfig, solver_version

    st.divider()
    st.subheader("Baseline vs CP-SAT optimizer (fictional scenarios)")
    st.caption("Both methods use the same rules, inputs, cost module and independent checker. The optimizer may "
               "choose different eligible teams, days and visit orders. Objective (lexicographic): "
               + " | ".join(OBJECTIVE_PRIORITIES))
    if "not installed" in solver_version():
        st.warning("OR-Tools is not installed in this environment; the comparison is unavailable. "
                   "Install with: python -m pip install \"ortools>=9.15,<9.16\"")
        return
    c1, c2 = st.columns([2, 1])
    name = c1.selectbox("Fictional scenario", list(SCENARIOS), key="cmp_scenario")
    limit = c2.number_input("Solver time budget (s)", min_value=1.0, max_value=120.0, value=20.0, step=1.0,
                            key="cmp_limit")
    folder = SCENARIOS[name]
    cfg = OptimizerConfig(time_limit_s=float(limit), random_seed=42, num_workers=1)
    key = (str(folder), scenario_hash(folder), cfg)
    if st.button("Run optimizer comparison", key="cmp_run"):
        st.session_state[CMP_KEY] = (key, compare_folder(folder, cfg))
    stored = st.session_state.get(CMP_KEY)
    if not stored or stored[0] != key:
        st.info("Press **Run optimizer comparison** to solve this scenario (results are not computed automatically "
                "and are discarded when the scenario or settings change).")
        return
    comp = stored[1]
    st.warning("Fictional scenario; draft plans only - not dispatch authorisation, not company-level evidence.",
               icon="⚠️")
    st.markdown(f"**Verdict on the stated objective:** {assess(comp)} | optimizer status "
                f"`{comp.optimizer.status_label}` | {comp.optimizer.solver_version} | runtime "
                f"{comp.optimizer.runtime_s} s | seed {cfg.random_seed}, workers {cfg.num_workers}")
    for note in comp.notes:
        st.warning(note)
    if comp.optimizer.message:
        st.caption(comp.optimizer.message)
    _table(comp.table, height=420)
    st.markdown("**Solver stages** (later stages fix earlier objectives; not proven optimal unless every stage is OPTIMAL)")
    _table(pd.DataFrame(comp.optimizer.stages))
    left, right = st.columns(2)
    with left:
        st.markdown("**Baseline itinerary**")
        _table(comp.baseline.frames["itinerary"], height=260)
        st.markdown("**Baseline: not scheduled**")
        _table(comp.baseline.frames["unassigned"])
    with right:
        st.markdown("**Optimizer itinerary**")
        if comp.optimizer_run is None:
            st.error("No valid optimizer schedule (see status above).")
        else:
            _table(comp.optimizer_run.frames["itinerary"], height=260)
            st.markdown("**Optimizer: not scheduled** (omission is not proof of individual infeasibility)")
            _table(comp.optimizer_run.frames["unassigned"])
    if not comp.baseline.cost_summary["coverage_complete"] or (
            comp.optimizer_run is not None and not comp.optimizer_run.cost_summary["coverage_complete"]):
        st.caption("Known estimated costs are incomplete (missing rates stay unknown); they are not budgets or savings.")
    st.code("python scripts/compare_schedulers.py", language="powershell")
