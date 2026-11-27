"""Deterministic rule-based scheduling baseline (version 1).

RULE (see docs/scheduling_baseline.md for the full statement)
For each planning day in ascending order, and each resource bundle in
ascending bundle_id order:
  1. The bundle operates only if every pilot, vehicle and equipment item in it
     has an explicit available=True row for that day and none of them has
     already been assigned to another bundle that day.
  2. Starting at the bundle's depot at the working-day start, repeatedly pick,
     among unscheduled jobs that are *eligible* (inside hard booking dates,
     not blocked that day, compatible vehicle/equipment/skills, known service
     duration) and whose addition still yields a *feasible* day route, the job
     with the earliest planning_due_date; ties by travel minutes from the
     current location, then job_id.
  3. Stop when no further job fits. The route returns to the depot.
A day route is feasible when every leg exists in the directed travel matrix,
work fits each job's access window, the break rule is satisfied, and the
return to the depot is no later than the working-day end.

Preferred date windows are SOFT: they never exclude a job; deviation is
reported. Hard booking dates, access windows, resource availability/conflicts
and working limits are HARD.

Version-1 limits: return to depot daily, no overnight stays, no job splitting,
each job completed within one day. Jobs longer than one working day are
reported as "multi-day planning not supported by this baseline version".
Results are draft planning outputs, not dispatch authorisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from agriflight.scheduling.contracts import Bundle, Job, Scenario

NOT_SCHEDULED = "not scheduled by this baseline"


@dataclass(frozen=True)
class Stop:
    job_id: str
    location_id: str
    travel_from: str
    travel_minutes: float
    distance_km: float | None
    arrival_min: float
    wait_min: float
    work_start_min: float
    setup_min: float
    service_min: float
    work_end_min: float
    break_min: float
    departure_min: float


@dataclass(frozen=True)
class RouteDay:
    bundle_id: str
    day: date
    depot_location_id: str
    start_min: float
    stops: tuple[Stop, ...]
    return_travel_minutes: float
    return_distance_km: float | None
    return_min: float

    @property
    def legs(self) -> list[tuple[str, str, float, float | None]]:
        out = [(s.travel_from, s.location_id, s.travel_minutes, s.distance_km) for s in self.stops]
        if self.stops:
            out.append((self.stops[-1].location_id, self.depot_location_id, self.return_travel_minutes,
                        self.return_distance_km))
        return out


@dataclass
class ScheduleResult:
    scenario: Scenario
    routes: list[RouteDay]
    assignments: dict[str, tuple[str, date]]
    unassigned: list[dict]
    bundle_day_status: list[dict]
    unsupported_multi_day: list[str] = field(default_factory=list)


class RouteInfeasible(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


# --------------------------------------------------------------- helpers
def service_minutes(job: Job, bundle: Bundle) -> float | None:
    """Explicit job duration wins; else area / declared bundle work rate."""
    if job.service_duration_min is not None:
        return float(job.service_duration_min)
    if job.required_area_ha is not None and bundle.work_rate_ha_per_hour:
        return job.required_area_ha / bundle.work_rate_ha_per_hour * 60.0
    return None


def setup_minutes(job: Job, bundle: Bundle) -> float:
    return float(job.setup_min) if job.setup_min is not None else float(bundle.setup_min)


def incompatibility(scenario: Scenario, job: Job, bundle: Bundle) -> str | None:
    vtype, etypes, skills = scenario.bundle_capabilities(bundle)
    if job.required_vehicle_type and job.required_vehicle_type != vtype:
        return f"vehicle type {vtype!r} != required {job.required_vehicle_type!r}"
    if job.required_equipment_type and job.required_equipment_type not in etypes:
        return f"equipment {sorted(etypes)} lacks required {job.required_equipment_type!r}"
    missing = set(job.required_skills) - skills
    if missing:
        return f"pilot skills lack {sorted(missing)}"
    return None


def date_allowed(job: Job, day: date) -> bool:
    if job.hard_earliest_date and day < job.hard_earliest_date:
        return False
    if job.hard_latest_date and day > job.hard_latest_date:
        return False
    return day not in job.blocked_dates


def is_multi_day(scenario: Scenario, job: Job, bundle: Bundle) -> bool:
    service = service_minutes(job, bundle)
    if service is None:
        return False
    usable = scenario.day_end_min - scenario.day_start_min - scenario.break_minutes
    return setup_minutes(job, bundle) + service > usable


def bundle_unavailability(scenario: Scenario, bundle: Bundle, day: date) -> list[str]:
    return [f"{rtype} {rid}" for rtype, rid in bundle.resources if not scenario.available(rtype, rid, day)]


def simulate_route(scenario: Scenario, bundle: Bundle, day: date, job_ids: list[str]) -> RouteDay:
    """Timeline for visiting ``job_ids`` in order from/to the depot; raises RouteInfeasible."""
    t = float(scenario.day_start_min)
    loc = bundle.depot_location_id
    break_taken = False
    stops: list[Stop] = []
    for jid in job_ids:
        job = scenario.jobs[jid]
        leg = scenario.leg(loc, job.location_id)
        if leg is None:
            raise RouteInfeasible("MISSING_TRAVEL", f"no travel entry {loc} -> {job.location_id}")
        service = service_minutes(job, bundle)
        if service is None:
            raise RouteInfeasible("NO_SERVICE_DURATION", jid)
        arrival = t + leg.travel_minutes
        work_start = max(arrival, float(job.access_start_min) if job.access_start_min is not None else arrival)
        setup = setup_minutes(job, bundle)
        work_end = work_start + setup + service
        if job.access_end_min is not None and work_end > job.access_end_min:
            raise RouteInfeasible("ACCESS_WINDOW", f"{jid} work would end after its access window")
        brk = 0.0
        if not break_taken and work_end - scenario.day_start_min >= scenario.break_after_minutes:
            brk, break_taken = float(scenario.break_minutes), True
        stops.append(Stop(jid, job.location_id, loc, leg.travel_minutes, leg.distance_km, arrival,
                          work_start - arrival, work_start, setup, service, work_end, brk, work_end + brk))
        t, loc = work_end + brk, job.location_id
    if not stops:
        return RouteDay(bundle.bundle_id, day, bundle.depot_location_id, scenario.day_start_min, (), 0.0, 0.0,
                        float(scenario.day_start_min))
    back = scenario.leg(loc, bundle.depot_location_id)
    if back is None:
        raise RouteInfeasible("MISSING_TRAVEL", f"no travel entry {loc} -> {bundle.depot_location_id}")
    return_min = t + back.travel_minutes
    if not break_taken and return_min - scenario.day_start_min > scenario.break_after_minutes:
        last = stops[-1]
        stops[-1] = Stop(**{**last.__dict__, "break_min": float(scenario.break_minutes),
                            "departure_min": last.departure_min + scenario.break_minutes})
        return_min += scenario.break_minutes
    if return_min > scenario.day_end_min:
        raise RouteInfeasible("DOES_NOT_FIT_WORKING_DAY", "return to depot after the working-day end")
    return RouteDay(bundle.bundle_id, day, bundle.depot_location_id, scenario.day_start_min, tuple(stops),
                    back.travel_minutes, back.distance_km, return_min)


def _eligible(scenario: Scenario, job: Job, bundle: Bundle, day: date) -> bool:
    return (date_allowed(job, day) and incompatibility(scenario, job, bundle) is None
            and service_minutes(job, bundle) is not None and not is_multi_day(scenario, job, bundle))


# --------------------------------------------------------------- schedule
def build_schedule(scenario: Scenario) -> ScheduleResult:
    unscheduled = set(scenario.jobs)
    assignments: dict[str, tuple[str, date]] = {}
    routes: list[RouteDay] = []
    status: list[dict] = []
    for day in scenario.horizon:
        used: dict[tuple[str, str], str] = {}
        for bundle in scenario.bundles:
            missing = bundle_unavailability(scenario, bundle, day)
            if missing:
                status.append({"day": day, "bundle_id": bundle.bundle_id, "operates": False,
                               "reason": "RESOURCE_UNAVAILABLE", "detail": ", ".join(missing)})
                continue
            clash = [f"{r[0]} {r[1]} (with {used[r]})" for r in bundle.resources if r in used]
            if clash:
                status.append({"day": day, "bundle_id": bundle.bundle_id, "operates": False,
                               "reason": "RESOURCE_ALREADY_ASSIGNED", "detail": ", ".join(clash)})
                continue
            plan: list[str] = []
            route = simulate_route(scenario, bundle, day, plan)
            while True:
                here = route.stops[-1].location_id if route.stops else bundle.depot_location_id
                candidates = []
                for jid in unscheduled:
                    job = scenario.jobs[jid]
                    if not _eligible(scenario, job, bundle, day):
                        continue
                    leg = scenario.leg(here, job.location_id)
                    if leg is None:
                        continue
                    candidates.append((job.planning_due_date, leg.travel_minutes, jid))
                chosen = None
                for _, _, jid in sorted(candidates):
                    try:
                        trial = simulate_route(scenario, bundle, day, plan + [jid])
                    except RouteInfeasible:
                        continue
                    chosen, route = jid, trial
                    break
                if chosen is None:
                    break
                plan.append(chosen)
                unscheduled.discard(chosen)
                assignments[chosen] = (bundle.bundle_id, day)
            if plan:
                routes.append(route)
                for r in bundle.resources:
                    used[r] = bundle.bundle_id
            status.append({"day": day, "bundle_id": bundle.bundle_id, "operates": bool(plan),
                           "reason": "SCHEDULED" if plan else "NO_FEASIBLE_JOB",
                           "detail": f"{len(plan)} job(s)" if plan else "available but no eligible job fitted"})
    unassigned = [diagnose_unassigned(scenario, scenario.jobs[j], status) for j in sorted(unscheduled)]
    multi = sorted(u["job_id"] for u in unassigned if "MULTI_DAY_UNSUPPORTED" in u["reason_codes"].split("|"))
    return ScheduleResult(scenario, routes, assignments, unassigned, status, multi)


def diagnose_unassigned(scenario: Scenario, job: Job, status: list[dict]) -> dict:
    """Structured reasons why the baseline did not schedule ``job`` (not a proof of infeasibility)."""
    reasons: list[str] = []
    details: list[str] = []
    compatible = [b for b in scenario.bundles if incompatibility(scenario, job, b) is None]
    if not compatible:
        reasons.append("NO_COMPATIBLE_BUNDLE")
        details += [f"{b.bundle_id}: {incompatibility(scenario, job, b)}" for b in scenario.bundles]
    with_duration = [b for b in compatible if service_minutes(job, b) is not None]
    if compatible and not with_duration:
        reasons.append("NO_SERVICE_DURATION")
        details.append("no explicit duration and no area/work-rate combination")
    single_day = [b for b in with_duration if not is_multi_day(scenario, job, b)]
    if with_duration and not single_day:
        reasons.append("MULTI_DAY_UNSUPPORTED")
        details.append("setup + service exceeds one working day; multi-day planning is not supported by this "
                       "baseline version (not a statement about company capability)")
    allowed_days = [d for d in scenario.horizon if date_allowed(job, d)]
    if single_day and not allowed_days:
        reasons.append("OUTSIDE_HARD_DATES")
        details.append("no horizon day inside hard booking dates / outside blocked dates")
    travel_ok = [b for b in single_day if scenario.leg(b.depot_location_id, job.location_id)
                 and scenario.leg(job.location_id, b.depot_location_id)]
    if single_day and not travel_ok:
        reasons.append("MISSING_TRAVEL")
        details += [f"{b.bundle_id}: depot<->{job.location_id} travel entry missing" for b in single_day]
    if travel_ok and allowed_days:
        operating = {(s["bundle_id"], s["day"]) for s in status if s["reason"] not in
                     ("RESOURCE_UNAVAILABLE", "RESOURCE_ALREADY_ASSIGNED")}
        solo_codes, solo_fit = set(), False
        for b in travel_ok:
            for d in allowed_days:
                if (b.bundle_id, d) not in operating:
                    continue
                try:
                    simulate_route(scenario, b, d, [job.job_id])
                    solo_fit = True
                except RouteInfeasible as exc:
                    solo_codes.add(exc.code)
        if not any((b.bundle_id, d) in operating for b in travel_ok for d in allowed_days):
            reasons.append("RESOURCES_UNAVAILABLE")
            details.append("no compatible bundle was available on an allowed day")
        elif solo_fit:
            reasons.append("CAPACITY_USED_BY_EARLIER_JOBS")
            details.append("would fit alone, but the greedy rule filled the compatible bundle-days first")
        else:
            reasons += sorted(solo_codes)
            details.append("does not fit a single bundle-day even on its own")
    return {"job_id": job.job_id, "division_id": job.division_id, "status": NOT_SCHEDULED,
            "reason_codes": "|".join(reasons) or "UNDETERMINED", "detail": "; ".join(details)}
