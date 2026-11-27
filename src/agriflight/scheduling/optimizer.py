"""OR-Tools CP-SAT scheduling optimizer (same operating rules as the rule baseline).

MODEL (see docs/scheduling_optimizer.md for the plain-English description)
* A "team-day" k is one bundle on one horizon day whose every resource is
  available. Team-days with no eligible job are omitted.
* For each team-day, a directed graph has node 0 = the bundle's depot and one
  node per eligible job. Arcs exist only where the directed travel matrix has
  an entry (missing edges are never created). A CP-SAT circuit constraint over
  these arcs forms ONE connected tour depot -> jobs -> depot, or skips the
  team-day entirely (depot self-loop). A job node's self-loop = not visited.
  Intermediate jobs need no direct depot edge; only the actual last job must
  have an edge back to the depot.
* Timing (integer seconds, durations rounded UP from minutes): arrival =
  previous departure + travel; work starts at max(arrival, access start) -
  no voluntary idling, as in the baseline; work end = start + setup + service
  and must respect the access end; the same break rule as the baseline (one
  break after the first job ending at or past the threshold, otherwise after
  the last job when the return passes the threshold); the return to the depot
  must be by the working-day end.
* Each job is visited by at most one team-day. A physical resource can belong
  to at most one USED team-day per day (whole-day reservation, no handovers).
* Eligibility uses the baseline's shared rules (hard dates, blocked dates,
  compatibility, known duration, one-day jobs).

OBJECTIVE (lexicographic, solved as three sequential CP-SAT solves)
  1. maximise the number of scheduled jobs;
  2. then minimise the total ABSOLUTE days outside each job's own preferred window;
  3. then minimise total travel time (seconds, including depot legs).
Each later stage fixes the earlier objective at its found value. If an earlier
stage was not proven optimal, the hierarchy is not proven optimal either.

Every returned itinerary is rebuilt with the shared exact timeline function
and validated by the independent checker; invalid outputs are rejected.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from agriflight.scheduling.contracts import Bundle, Scenario
from agriflight.scheduling.rule_baseline import (
    NOT_SCHEDULED,
    RouteInfeasible,
    ScheduleResult,
    build_schedule,
    bundle_unavailability,
    date_allowed,
    incompatibility,
    is_multi_day,
    service_minutes,
    setup_minutes,
    simulate_route,
)

SCALE = 60  # CP-SAT time unit: seconds
STAGES = ("max_scheduled_jobs", "min_preferred_window_days_outside", "min_travel_seconds")

LABEL_OPTIMAL = "optimal_for_stated_model"
LABEL_FEASIBLE = "feasible_optimality_not_established"
LABEL_NO_SOLUTION = "no_solution_within_limits"
LABEL_INVALID = "model_invalid"
LABEL_INFEASIBLE = "model_infeasible"
LABEL_REJECTED = "invalid_result_rejected"


@dataclass(frozen=True)
class OptimizerConfig:
    time_limit_s: float = 20.0  # total budget across the three stages
    random_seed: int = 42
    num_workers: int = 1
    fallback_to_baseline: bool = False


@dataclass
class OptimizerOutcome:
    method: str  # "cp_sat_optimizer" or "rule_baseline_fallback" or "none"
    result: ScheduleResult | None
    status_label: str
    stages: list[dict] = field(default_factory=list)
    solver_version: str = ""
    config: dict = field(default_factory=dict)
    runtime_s: float = 0.0
    fallback_used: bool = False
    model_size: dict = field(default_factory=dict)
    message: str = ""


def solver_version() -> str:
    try:
        import ortools
        return f"ortools {ortools.__version__}"
    except ImportError:
        return "ortools not installed"


def secs(minutes: float) -> int:
    return int(math.ceil(minutes * SCALE - 1e-9))


def window_days_outside(day: date, start: date, end: date) -> int:
    if day < start:
        return (start - day).days
    if day > end:
        return (day - end).days
    return 0


def _eligible(scenario: Scenario, job_id: str, bundle: Bundle, day: date) -> bool:
    job = scenario.jobs[job_id]
    return (date_allowed(job, day) and incompatibility(scenario, job, bundle) is None
            and service_minutes(job, bundle) is not None and not is_multi_day(scenario, job, bundle))


class _Model:
    """Builds the CP-SAT model once; objectives are swapped between stages."""

    def __init__(self, scenario: Scenario):
        from ortools.sat.python import cp_model
        self.cp = cp_model
        self.sc = scenario
        m = self.m = cp_model.CpModel()
        S, E = scenario.day_start_min * SCALE, scenario.day_end_min * SCALE
        A, B = S + scenario.break_after_minutes * SCALE, scenario.break_minutes * SCALE
        self.teamdays: list[tuple[Bundle, date]] = []
        self.used, self.visit, self.arcs, self.nodes = {}, {}, {}, {}
        self.travel_terms, self.dev_terms = [], []
        for day in scenario.horizon:
            for bundle in scenario.bundles:
                if bundle_unavailability(scenario, bundle, day):
                    continue
                jobs = sorted(j for j in scenario.jobs if _eligible(scenario, j, bundle, day))
                if not jobs:
                    continue
                k = len(self.teamdays)
                self.teamdays.append((bundle, day))
                self._team_day(k, bundle, day, jobs, S, E, A, B)
        # each job at most once
        self.assigned = {}
        for j in scenario.jobs:
            lits = [v for (k, jj), v in self.visit.items() if jj == j]
            a = m.new_bool_var(f"assigned_{j}")
            m.add(sum(lits) == a) if lits else m.add(a == 0)
            self.assigned[j] = a
        # whole-day exclusivity of shared physical resources
        for day in scenario.horizon:
            users: dict[tuple[str, str], list] = {}
            for k, (bundle, d) in enumerate(self.teamdays):
                if d == day:
                    for r in bundle.resources:
                        users.setdefault(r, []).append(self.used[k])
            for lits in users.values():
                if len(lits) > 1:
                    m.add(sum(lits) <= 1)
        self.obj = {
            STAGES[0]: sum(self.assigned.values()),
            STAGES[1]: sum(self.dev_terms) if self.dev_terms else 0,
            STAGES[2]: sum(self.travel_terms) if self.travel_terms else 0,
        }

    def _team_day(self, k, bundle, day, jobs, S, E, A, B):
        m, sc = self.m, self.sc
        used = m.new_bool_var(f"used_{k}")
        self.used[k] = used
        nodes = [bundle.depot_location_id] + [sc.jobs[j].location_id for j in jobs]
        self.nodes[k] = jobs
        arcs = [(0, 0, used.Not())]
        lit = {}
        for a in range(len(nodes)):
            for b in range(len(nodes)):
                if a == b:
                    continue
                leg = sc.leg(nodes[a], nodes[b])
                if leg is None:
                    continue  # missing directed edge: no arc, never zero travel
                x = m.new_bool_var(f"x_{k}_{a}_{b}")
                lit[(a, b)] = (x, secs(leg.travel_minutes))
                arcs.append((a, b, x))
                self.travel_terms.append(secs(leg.travel_minutes) * x)
        self.arcs[k] = lit
        info = {}
        for idx, j in enumerate(jobs, 1):
            job = sc.jobs[j]
            v = m.new_bool_var(f"v_{k}_{j}")
            self.visit[(k, j)] = v
            arcs.append((idx, idx, v.Not()))
            m.add_implication(v, used)
            dev = window_days_outside(day, job.preferred_window_start, job.preferred_window_end)
            if dev:
                self.dev_terms.append(dev * v)
            arr, start, end, dep = (m.new_int_var(S, E, f"{n}_{k}_{j}") for n in ("arr", "start", "end", "dep"))
            late, bprev, bmain, btk, blast = (m.new_bool_var(f"{n}_{k}_{j}") for n in
                                               ("late", "bprev", "bmain", "btk", "blast"))
            duration = secs(setup_minutes(job, bundle)) + secs(service_minutes(job, bundle))
            m.add(start >= arr).only_enforce_if(v)
            if job.access_start_min is not None:
                acc = job.access_start_min * SCALE
                wait = m.new_bool_var(f"wait_{k}_{j}")
                m.add(start >= acc).only_enforce_if(v)
                m.add(start == acc).only_enforce_if([v, wait])
                m.add(start == arr).only_enforce_if([v, wait.Not()])
            else:
                m.add(start == arr).only_enforce_if(v)
            m.add(end == start + duration).only_enforce_if(v)
            if job.access_end_min is not None:
                m.add(end <= job.access_end_min * SCALE).only_enforce_if(v)
            # break semantics identical to the baseline
            m.add(end >= A).only_enforce_if([v, late])
            m.add(end <= A - 1).only_enforce_if([v, late.Not()])
            for b in (late, bmain, btk, blast, bprev):
                m.add_implication(b, v)
            m.add_implication(bmain, late)
            m.add_implication(bmain, bprev.Not())
            m.add_bool_or([v.Not(), late.Not(), bprev, bmain])
            m.add_bool_or([btk.Not(), bprev, bmain])
            m.add_implication(bprev, btk)
            m.add_implication(bmain, btk)
            info[idx] = dict(v=v, arr=arr, end=end, dep=dep, bprev=bprev, btk=btk, bmain=bmain, blast=blast)
            ret = lit.get((idx, 0))
            if ret is None:
                m.add(blast == 0)
            else:
                x_ret, t_ret = ret
                retlong = m.new_bool_var(f"retlong_{k}_{j}")
                m.add(end + t_ret >= A + 1).only_enforce_if([v, retlong])
                m.add(end + t_ret <= A).only_enforce_if([v, retlong.Not()])
                m.add_implication(blast, x_ret)
                m.add_implication(blast, btk.Not())
                m.add_implication(blast, retlong)
                m.add_bool_or([x_ret.Not(), btk, retlong.Not(), blast])
                m.add(dep + t_ret <= E).only_enforce_if(x_ret)
            m.add(dep == end + B * bmain + B * blast).only_enforce_if(v)
        for (a, b), (x, t) in lit.items():
            if b == 0:
                continue
            tgt = info[b]
            if a == 0:
                m.add(tgt["arr"] == S + t).only_enforce_if(x)
                m.add(tgt["bprev"] == 0).only_enforce_if(x)
            else:
                m.add(tgt["arr"] == info[a]["dep"] + t).only_enforce_if(x)
                m.add(tgt["bprev"] == info[a]["btk"]).only_enforce_if(x)
        if any(b != 0 for (_, b) in lit):
            m.add(sum(info[i]["v"] for i in info) >= 1).only_enforce_if(used)
        m.add_circuit(arcs)

    def solve(self, stage: str, maximize: bool, time_limit: float, cfg: OptimizerConfig, hint=None):
        solver = self.cp.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.01, time_limit)
        solver.parameters.num_workers = cfg.num_workers
        solver.parameters.random_seed = cfg.random_seed
        self.m.clear_objective()
        (self.m.maximize if maximize else self.m.minimize)(self.obj[stage])
        self.m.clear_hints()
        if hint:
            for var, value in hint.items():
                self.m.add_hint(var, value)
        status = solver.solve(self.m)
        return solver, status

    def all_bools(self):
        out = list(self.used.values()) + list(self.visit.values())
        for lit in self.arcs.values():
            out += [x for x, _ in lit.values()]
        return out


def _extract(model: _Model, solver) -> list[tuple[Bundle, date, list[str]]]:
    plans = []
    for k, (bundle, day) in enumerate(model.teamdays):
        if not solver.value(model.used[k]):
            continue
        succ = {a: b for (a, b), (x, _) in model.arcs[k].items() if solver.value(x)}
        order, node, guard = [], succ.get(0), 0
        while node not in (None, 0) and guard <= len(model.nodes[k]):
            order.append(model.nodes[k][node - 1])
            node, guard = succ.get(node), guard + 1
        plans.append((bundle, day, order))
    return plans


def _status_label(stages: list[dict]) -> str:
    first = stages[0]["status"]
    if first == "MODEL_INVALID":
        return LABEL_INVALID
    if first == "INFEASIBLE":
        return LABEL_INFEASIBLE
    if first not in ("OPTIMAL", "FEASIBLE"):
        return LABEL_NO_SOLUTION
    return LABEL_OPTIMAL if all(s["status"] == "OPTIMAL" for s in stages) else LABEL_FEASIBLE


def optimize(scenario: Scenario, config: OptimizerConfig | None = None) -> OptimizerOutcome:
    cfg = config or OptimizerConfig()
    t0 = time.perf_counter()
    outcome = OptimizerOutcome("none", None, LABEL_NO_SOLUTION, solver_version=solver_version(), config=asdict(cfg))
    try:
        model = _Model(scenario)
    except ImportError:
        outcome.message = "OR-Tools is not installed in this environment."
        return _maybe_fallback(scenario, outcome, cfg, t0)
    outcome.model_size = {"team_days": len(model.teamdays), "job_visit_vars": len(model.visit),
                          "arc_vars": sum(len(a) for a in model.arcs.values())}
    best_solver, hint = None, None
    for i, stage in enumerate(STAGES):
        remaining = cfg.time_limit_s - (time.perf_counter() - t0)
        if remaining <= 0.01 and best_solver is not None:
            outcome.stages.append({"stage": stage, "status": "NOT_RUN_TIME_BUDGET", "objective_value": None,
                                   "best_bound": None, "wall_time_s": 0.0})
            continue
        solver, status = model.solve(stage, i == 0, remaining / (len(STAGES) - i), cfg, hint)
        name = solver.status_name(status)
        has = name in ("OPTIMAL", "FEASIBLE")
        outcome.stages.append({"stage": stage, "status": name,
                               "objective_value": solver.objective_value if has else None,
                               "best_bound": solver.best_objective_bound if has else None,
                               "wall_time_s": round(solver.wall_time, 4)})
        if not has:
            if i == 0:
                break
            continue  # keep the previous stage's solution
        best_solver = solver
        value = int(round(solver.objective_value))
        expr = model.obj[stage]
        if not isinstance(expr, int):  # a constant objective needs no fixing constraint
            if name == "OPTIMAL":
                model.m.add(expr == value)
            elif i == 0:
                model.m.add(expr >= value)
            else:
                model.m.add(expr <= value)
        hint = {var: solver.value(var) for var in model.all_bools()}
    outcome.status_label = _status_label(outcome.stages)
    if best_solver is None:
        outcome.message = f"Stage 1 status {outcome.stages[0]['status']}; no optimizer schedule."
        return _maybe_fallback(scenario, outcome, cfg, t0)
    try:
        result = _to_result(scenario, model, _extract(model, best_solver))
    except RouteInfeasible as exc:
        outcome.status_label = LABEL_REJECTED
        outcome.message = f"Solver itinerary failed the exact timeline rebuild: {exc}"
        return _maybe_fallback(scenario, outcome, cfg, t0)
    outcome.method, outcome.result = "cp_sat_optimizer", result
    outcome.runtime_s = round(time.perf_counter() - t0, 4)
    return outcome


def _maybe_fallback(scenario, outcome, cfg, t0):
    if cfg.fallback_to_baseline:
        outcome.method, outcome.result, outcome.fallback_used = "rule_baseline_fallback", build_schedule(scenario), True
        outcome.message += " Returned the rule-based baseline as an explicitly labelled FALLBACK (not optimized)."
    outcome.runtime_s = round(time.perf_counter() - t0, 4)
    return outcome


def _to_result(scenario: Scenario, model: _Model, plans) -> ScheduleResult:
    routes, assignments = [], {}
    for bundle, day, order in plans:
        route = simulate_route(scenario, bundle, day, order)  # shared exact timeline; raises if invalid
        routes.append(route)
        for j in order:
            assignments[j] = (bundle.bundle_id, day)
    used = {(b.bundle_id, d) for b, d, _ in plans}
    status = []
    for day in scenario.horizon:
        taken = {r for b, d, _ in plans if d == day for r in b.resources}
        for bundle in scenario.bundles:
            missing = bundle_unavailability(scenario, bundle, day)
            if (bundle.bundle_id, day) in used:
                entry = ("SCHEDULED", f"{len(next(o for b, d, o in plans if b.bundle_id == bundle.bundle_id and d == day))} job(s)")
            elif missing:
                entry = ("RESOURCE_UNAVAILABLE", ", ".join(missing))
            elif any(r in taken for r in bundle.resources):
                entry = ("RESOURCE_ALREADY_ASSIGNED", "shares a resource with a bundle used that day")
            else:
                entry = ("NOT_USED_BY_OPTIMIZER", "available; not used in the chosen solution")
            status.append({"day": day, "bundle_id": bundle.bundle_id, "operates": entry[0] == "SCHEDULED",
                           "reason": entry[0], "detail": entry[1]})
    unassigned = [_explain(scenario, model, j) for j in sorted(scenario.jobs) if j not in assignments]
    multi = sorted(u["job_id"] for u in unassigned if "MULTI_DAY_UNSUPPORTED" in u["reason_codes"])
    return ScheduleResult(scenario, routes, assignments, unassigned, status, multi)


def _explain(scenario: Scenario, model: _Model, job_id: str) -> dict:
    """Explain an omitted job only as strongly as the evidence permits."""
    job = scenario.jobs[job_id]
    compatible = [b for b in scenario.bundles if incompatibility(scenario, job, b) is None]
    timed = [b for b in compatible if service_minutes(job, b) is not None]
    one_day = [b for b in timed if not is_multi_day(scenario, job, b)]
    if not compatible:
        code, detail = "NO_COMPATIBLE_BUNDLE", "no bundle meets the vehicle/equipment/skill requirements"
    elif not timed:
        code, detail = "NO_SERVICE_DURATION", "no explicit duration and no area/work-rate combination"
    elif not one_day:
        code, detail = "MULTI_DAY_UNSUPPORTED", ("setup + service exceeds one working day; multi-day planning is not "
                                               "supported by version 1 (not a statement about company capability)")
    elif not any(date_allowed(job, d) for d in scenario.horizon):
        code, detail = "OUTSIDE_HARD_DATES", "no horizon day inside hard booking dates / outside blocked dates"
    elif not any(job_id in model.nodes[k] for k in model.nodes):
        code, detail = "RESOURCES_UNAVAILABLE", "no compatible bundle is available on an allowed day"
    elif not any(_connected(model, k, job_id) for k in model.nodes if job_id in model.nodes[k]):
        code, detail = "NO_TRAVEL_CONNECTION", "no incoming or no outgoing travel edge in any eligible team-day graph"
    else:
        solo = False
        for k, (bundle, day) in enumerate(model.teamdays):
            if job_id in model.nodes.get(k, []):
                try:
                    simulate_route(scenario, bundle, day, [job_id])
                    solo = True
                    break
                except RouteInfeasible:
                    pass
        if solo:
            code, detail = ("NOT_SELECTED_BY_OPTIMIZER",
                            "fits a team-day on its own, but is not in the chosen solution under the stated objective")
        else:
            code, detail = ("NOT_SELECTED_BY_OPTIMIZER",
                            "not in the chosen solution; individual feasibility not established (no direct "
                            "depot round trip fits; a multi-stop route was not proven impossible)")
    return {"job_id": job_id, "division_id": job.division_id, "status": NOT_SCHEDULED.replace("baseline", "optimizer"),
            "reason_codes": code, "detail": detail}


def _connected(model: _Model, k: int, job_id: str) -> bool:
    idx = model.nodes[k].index(job_id) + 1
    arcs = model.arcs[k]
    return any(b == idx for (_, b) in arcs) and any(a == idx for (a, _) in arcs)
