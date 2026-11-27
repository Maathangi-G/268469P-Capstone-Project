"""Reproducible comparison of the rule baseline and the CP-SAT optimizer.

Both methods run on the same loaded scenario and are summarised by the SAME
cost module, independent checker and metric function. Metrics state their
denominators; an unscheduled job never counts as window-compliant. When the
methods schedule different jobs, travel and cost differences are flagged as
not like-for-like (less work can cost less without being better).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from agriflight.scheduling.contracts import Scenario, load_scenario
from agriflight.scheduling.optimizer import OptimizerConfig, OptimizerOutcome, optimize, window_days_outside
from agriflight.scheduling.outputs import ScheduleRun, summarize_result
from agriflight.scheduling.rule_baseline import build_schedule, service_minutes

OBJECTIVE_PRIORITIES = (
    "1. maximise the number of scheduled jobs",
    "2. minimise total absolute days outside each job's supplied preferred window",
    "3. minimise total travel time (including depot legs)",
    "Cost is reported, not optimised.",
)


def scenario_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix in (".csv", ".json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def pct_change(a: float | None, b: float | None) -> str:
    """Percentage change from a to b, safe for zero/unknown denominators."""
    if a is None or b is None:
        return "n/a (unknown)"
    if a == 0:
        return "n/a (baseline is 0)" if b != 0 else "0%"
    return f"{100 * (b - a) / a:+.1f}%"


def metrics(run: ScheduleRun | None, scenario: Scenario, runtime_s: float, status: str) -> dict:
    total = len(scenario.jobs)
    if run is None:
        return {"status": status, "runtime_s": runtime_s, "jobs_total": total, "scheduled_count": None}
    res = run.result
    scheduled = sorted(res.assignments)
    op, prop = scenario.cadence["operational_tolerance_days"], scenario.cadence["proposal_tolerance_days"]
    area, missing_area, service, setup = 0.0, 0, 0.0, 0.0
    outside_total, early, late, op_ok, prop_ok = 0, 0, 0, 0, 0
    for route in res.routes:
        for stop in route.stops:
            job = scenario.jobs[stop.job_id]
            service += stop.service_min
            setup += stop.setup_min
            if job.required_area_ha is None:
                missing_area += 1
            else:
                area += job.required_area_ha
            out = window_days_outside(route.day, job.preferred_window_start, job.preferred_window_end)
            outside_total += out
            early += route.day < job.preferred_window_start
            late += route.day > job.preferred_window_end
            offset = abs((route.day - job.planning_due_date).days)
            op_ok += offset <= op
            prop_ok += offset <= prop
    legs = [leg for r in res.routes for leg in r.legs]
    km = None if any(leg[3] is None for leg in legs) else round(sum(leg[3] for leg in legs), 1)
    return {
        "status": status, "runtime_s": round(runtime_s, 4), "jobs_total": total,
        "scheduled_count": len(scheduled), "unscheduled_count": total - len(scheduled),
        "scheduled_ids": ", ".join(scheduled),
        "unscheduled_ids": ", ".join(sorted(set(scenario.jobs) - set(scheduled))),
        "scheduled_area_ha_known": round(area, 2), "scheduled_jobs_missing_area": missing_area,
        "scheduled_service_min": round(service, 1), "scheduled_setup_min": round(setup, 1),
        "preferred_window_days_outside_total": outside_total,
        "preferred_window_jobs_early": int(early), "preferred_window_jobs_late": int(late),
        f"operational_pm{op}_compliant": f"{op_ok} of {total} jobs ({op_ok} of {len(scheduled)} scheduled)",
        f"proposal_pm{prop}_compliant": f"{prop_ok} of {total} jobs ({prop_ok} of {len(scheduled)} scheduled)",
        "travel_min": round(sum(leg[2] for leg in legs), 1), "travel_km": km,
        "team_days_used": len(res.routes),
        "known_estimated_cost_lkr": run.cost_summary["estimated_known_total_lkr"],
        "cost_coverage_complete": run.cost_summary["coverage_complete"],
        "missing_cost_components": "; ".join(run.cost_summary["missing_components"]),
        "independent_checks_passed": run.checks_passed,
    }


@dataclass
class Comparison:
    scenario: Scenario
    input_hash: str
    baseline: ScheduleRun
    baseline_runtime_s: float
    optimizer: OptimizerOutcome
    optimizer_run: ScheduleRun | None
    table: pd.DataFrame
    same_job_set: bool | None
    notes: list[str]


def compare_folder(folder: Path, config: OptimizerConfig | None = None) -> Comparison:
    scenario = load_scenario(folder)
    t0 = time.perf_counter()
    baseline_result = build_schedule(scenario)
    base_rt = time.perf_counter() - t0
    base_run = summarize_result(baseline_result)
    outcome = optimize(scenario, config)
    opt_run = summarize_result(outcome.result) if outcome.result is not None else None
    if opt_run is not None and not opt_run.checks_passed and not outcome.fallback_used:
        outcome.message += " Optimizer itinerary FAILED the independent checker and is rejected."
        outcome.status_label, opt_run = "invalid_result_rejected", None
    b = metrics(base_run, scenario, base_rt, "deterministic rule baseline")
    o = metrics(opt_run, scenario, outcome.runtime_s,
                f"{outcome.method}: {outcome.status_label}" + (" (FALLBACK, not optimized)" if outcome.fallback_used else ""))
    notes: list[str] = []
    same = None
    if opt_run is not None:
        same = set(base_run.result.assignments) == set(opt_run.result.assignments)
        if not same:
            only_b = sorted(set(base_run.result.assignments) - set(opt_run.result.assignments))
            only_o = sorted(set(opt_run.result.assignments) - set(base_run.result.assignments))
            notes.append(f"Different scheduled job sets: only baseline {only_b or '-'}; only optimizer {only_o or '-'}. "
                         "Travel, area, duration and cost differences are not like-for-like.")
    if outcome.status_label != "optimal_for_stated_model":
        notes.append(f"Optimizer status: {outcome.status_label}; hierarchical optimality NOT established.")
    rows = []
    for key in b:
        if key in ("status",):
            continue
        bv, ov = b.get(key), o.get(key)
        diff = ""
        if isinstance(bv, (int, float)) and isinstance(ov, (int, float)) and not isinstance(bv, bool):
            diff = f"{ov - bv:+g} ({pct_change(bv, ov)})"
        rows.append({"metric": key, "baseline": bv, "optimizer": ov, "difference (optimizer - baseline)": diff})
    rows.insert(0, {"metric": "method / status", "baseline": b["status"], "optimizer": o["status"],
                    "difference (optimizer - baseline)": ""})
    table = pd.DataFrame(rows).astype({"baseline": "string", "optimizer": "string"})
    return Comparison(scenario, scenario_hash(folder), base_run, base_rt, outcome, opt_run, table, same, notes)


def assess(comp: Comparison) -> str:
    """Plain verdict on the stated objective hierarchy only (not cost, not company performance)."""
    if comp.optimizer_run is None:
        return "no optimizer result"
    b, o = comp.baseline.result, comp.optimizer_run.result
    keys = []
    for res in (b, o):
        outside = sum(window_days_outside(r.day, comp.scenario.jobs[s.job_id].preferred_window_start,
                                          comp.scenario.jobs[s.job_id].preferred_window_end)
                      for r in res.routes for s in r.stops)
        travel = sum(leg[2] for r in res.routes for leg in r.legs)
        keys.append((-len(res.assignments), outside, round(travel, 6)))
    if keys[1] < keys[0]:
        return "optimizer better on the stated objective"
    if keys[1] > keys[0]:
        return "optimizer worse on the stated objective"
    return "tied on the stated objective"


def unused_service_minutes(scenario: Scenario, run: ScheduleRun) -> float | None:
    """Service minutes of unscheduled jobs where known (context for job-count objective bias)."""
    total = 0.0
    for job_id in set(scenario.jobs) - set(run.result.assignments):
        values = [service_minutes(scenario.jobs[job_id], b) for b in scenario.bundles]
        values = [v for v in values if v is not None]
        if values:
            total += min(values)
    return round(total, 1)
