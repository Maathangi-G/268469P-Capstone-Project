"""Verification helpers for comparing the baseline and the CP-SAT model fairly.

* ``rounding_audit`` lists every duration the CP-SAT model uses and whether
  converting it to integer seconds (rounding up) changes it.
* ``baseline_in_model`` fixes the baseline's exact assignments and visit
  orders as HARD constraints (not hints) in the optimizer's integer model and
  asks CP-SAT whether that schedule is feasible there, letting the timing
  variables take any valid values. It also evaluates the baseline on the
  optimizer's three objective measures in the same units.

Only if the baseline is feasible in the same model can a proven-optimal
optimizer result be said to be no worse on the stated objective.
"""

from __future__ import annotations

import pandas as pd

from agriflight.scheduling.contracts import Scenario
from agriflight.scheduling.optimizer import SCALE, OptimizerConfig, _Model, secs, window_days_outside
from agriflight.scheduling.rule_baseline import (
    ScheduleResult,
    bundle_unavailability,
    date_allowed,
    incompatibility,
    is_multi_day,
    service_minutes,
    setup_minutes,
)


def rounding_audit(scenario: Scenario) -> pd.DataFrame:
    rows = []

    def add(kind: str, item: str, minutes: float) -> None:
        exact = minutes * SCALE
        used = secs(minutes)
        rows.append({"kind": kind, "item": item, "minutes_exact": minutes, "seconds_exact": exact,
                     "seconds_used": used, "rounding_added_s": round(used - exact, 6)})

    for (a, b), leg in sorted(scenario.travel.items()):
        add("travel", f"{a}->{b}", leg.travel_minutes)
    for bundle in scenario.bundles:
        days = [d for d in scenario.horizon if not bundle_unavailability(scenario, bundle, d)]
        for job in scenario.jobs.values():
            if not any(date_allowed(job, d) for d in days) or incompatibility(scenario, job, bundle) is not None:
                continue
            service = service_minutes(job, bundle)
            if service is None or is_multi_day(scenario, job, bundle):
                continue
            add("setup", f"{job.job_id}@{bundle.bundle_id}", setup_minutes(job, bundle))
            add("service", f"{job.job_id}@{bundle.bundle_id}", service)
    add("break", "break_minutes", scenario.break_minutes)
    add("working_day", "break_after_minutes", scenario.break_after_minutes)
    add("working_day", "day_start", scenario.day_start_min)
    add("working_day", "day_end", scenario.day_end_min)
    return pd.DataFrame(rows)


def baseline_objectives(scenario: Scenario, result: ScheduleResult) -> dict:
    """The baseline evaluated on the optimizer's measures (scaled travel = solver units)."""
    legs = [leg for r in result.routes for leg in r.legs]
    return {
        "scheduled_jobs": len(result.assignments),
        "preferred_window_days_outside": sum(
            window_days_outside(r.day, scenario.jobs[s.job_id].preferred_window_start,
                                scenario.jobs[s.job_id].preferred_window_end) for r in result.routes for s in r.stops),
        "travel_seconds_solver_units": sum(secs(leg[2]) for leg in legs),
        "travel_minutes_exact": round(sum(leg[2] for leg in legs), 6),
    }


def baseline_in_model(scenario: Scenario, result: ScheduleResult, config: OptimizerConfig | None = None) -> dict:
    cfg = config or OptimizerConfig(time_limit_s=10.0)
    model = _Model(scenario)
    index = {(b.bundle_id, d): k for k, (b, d) in enumerate(model.teamdays)}
    used_k = set()
    for route in result.routes:
        k = index.get((route.bundle_id, route.day))
        if k is None:
            return {"feasible": False, "status": "NOT_REPRESENTABLE",
                    "reason": f"team-day {route.bundle_id} {route.day} absent from the model"}
        used_k.add(k)
        seq = [0]
        for stop in route.stops:
            if stop.job_id not in model.nodes[k]:
                return {"feasible": False, "status": "NOT_REPRESENTABLE",
                        "reason": f"{stop.job_id} not eligible for {route.bundle_id} {route.day} in the model"}
            seq.append(model.nodes[k].index(stop.job_id) + 1)
        seq.append(0)
        chosen = set(zip(seq, seq[1:]))
        for arc in chosen:
            if arc not in model.arcs[k]:
                return {"feasible": False, "status": "NOT_REPRESENTABLE", "reason": f"arc {arc} missing in model"}
        for arc, (x, _) in model.arcs[k].items():
            model.m.add(x == (1 if arc in chosen else 0))
        for j in model.nodes[k]:
            model.m.add(model.visit[(k, j)] == (1 if j in {s.job_id for s in route.stops} else 0))
    for k, used in model.used.items():
        model.m.add(used == (1 if k in used_k else 0))
    solver = model.cp.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.time_limit_s
    solver.parameters.num_workers = cfg.num_workers
    solver.parameters.random_seed = cfg.random_seed
    model.m.clear_objective()
    model.m.clear_hints()
    name = solver.status_name(solver.solve(model.m))
    return {"feasible": name in ("OPTIMAL", "FEASIBLE"), "status": name,
            "reason": "baseline assignments and visit orders fixed as hard constraints"}
