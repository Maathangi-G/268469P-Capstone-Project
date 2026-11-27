"""Independent checks of a schedule result.

Deliberately re-derives times and costs from the scenario inputs rather than
calling the scheduler's own simulation, so an error in the scheduler is not
silently repeated by the checker.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from agriflight.scheduling.contracts import Scenario
from agriflight.scheduling.rule_baseline import ScheduleResult

TOL = 1e-6


def _ok(name: str, problems: list[str]) -> dict:
    return {"check": name, "passed": not problems, "problems": len(problems), "detail": "; ".join(problems[:5])}


def check_schedule(result: ScheduleResult, cost_rows: list[dict]) -> pd.DataFrame:
    sc: Scenario = result.scenario
    bundles = {b.bundle_id: b for b in sc.bundles}
    checks = []

    # 1. each job at most once, and assignments agree with the routes
    seen = Counter(s.job_id for r in result.routes for s in r.stops)
    problems = [f"{j} visited {n} times" for j, n in seen.items() if n > 1]
    problems += [f"{j} assignment/route mismatch" for j, (bid, day) in result.assignments.items()
                 if not any(r.bundle_id == bid and r.day == day and j in [s.job_id for s in r.stops] for r in result.routes)]
    problems += [f"{j} routed but not assigned" for j in seen if j not in result.assignments]
    problems += [f"{u['job_id']} both assigned and unassigned" for u in result.unassigned if u["job_id"] in result.assignments]
    checks.append(_ok("unique_job_assignment", problems))

    # 2. resources: available and not shared between bundles on the same day
    problems, per_day = [], {}
    for r in result.routes:
        for rtype, rid in bundles[r.bundle_id].resources:
            if not sc.available(rtype, rid, r.day):
                problems.append(f"{r.day} {r.bundle_id}: {rtype} {rid} not available")
            other = per_day.setdefault((r.day, rtype, rid), r.bundle_id)
            if other != r.bundle_id:
                problems.append(f"{r.day}: {rtype} {rid} used by {other} and {r.bundle_id}")
    keys = Counter((r.bundle_id, r.day) for r in result.routes)
    problems += [f"{k} has {n} routes" for k, n in keys.items() if n > 1]
    checks.append(_ok("resource_conflicts_and_availability", problems))

    # 3. route continuity and travel matrix agreement
    problems = []
    for r in result.routes:
        loc = r.depot_location_id
        if r.depot_location_id != bundles[r.bundle_id].depot_location_id:
            problems.append(f"{r.bundle_id} {r.day}: wrong depot")
        for s in r.stops:
            leg = sc.leg(loc, s.location_id)
            if s.travel_from != loc or leg is None or abs(leg.travel_minutes - s.travel_minutes) > TOL:
                problems.append(f"{r.bundle_id} {r.day}: leg {loc}->{s.location_id} inconsistent or missing")
            loc = s.location_id
        back = sc.leg(loc, r.depot_location_id)
        if r.stops and (back is None or abs(back.travel_minutes - r.return_travel_minutes) > TOL):
            problems.append(f"{r.bundle_id} {r.day}: return leg {loc}->{r.depot_location_id} inconsistent or missing")
    checks.append(_ok("route_continuity", problems))

    # 4. time accounting, working limits and the break rule
    problems = []
    for r in result.routes:
        tag = f"{r.bundle_id} {r.day}"
        t = r.start_min
        if abs(t - sc.day_start_min) > TOL:
            problems.append(f"{tag}: does not start at working-day start")
        components = 0.0
        for s in r.stops:
            if abs(s.arrival_min - (t + s.travel_minutes)) > TOL or s.wait_min < -TOL \
                    or abs(s.work_start_min - (s.arrival_min + s.wait_min)) > TOL \
                    or abs(s.work_end_min - (s.work_start_min + s.setup_min + s.service_min)) > TOL \
                    or abs(s.departure_min - (s.work_end_min + s.break_min)) > TOL:
                problems.append(f"{tag} {s.job_id}: timeline arithmetic inconsistent")
            components += s.travel_minutes + s.wait_min + s.setup_min + s.service_min + s.break_min
            t = s.departure_min
        components += r.return_travel_minutes
        if abs(r.return_min - (t + r.return_travel_minutes)) > TOL:
            problems.append(f"{tag}: return time inconsistent")
        if abs((r.return_min - r.start_min) - components) > TOL:
            problems.append(f"{tag}: time components do not sum to the route duration")
        if r.return_min > sc.day_end_min + TOL:
            problems.append(f"{tag}: returns after working-day end")
        breaks = [s for s in r.stops if s.break_min > 0]
        long_day = r.return_min - r.start_min > sc.break_after_minutes
        expected = next((s.job_id for s in r.stops if s.work_end_min - r.start_min >= sc.break_after_minutes),
                        r.stops[-1].job_id if r.stops else None)
        if long_day and (len(breaks) != 1 or breaks[0].job_id != expected
                         or abs(breaks[0].break_min - sc.break_minutes) > TOL):
            problems.append(f"{tag}: break rule not satisfied")
        if not long_day and breaks:
            problems.append(f"{tag}: break recorded on a day shorter than the break threshold")
    checks.append(_ok("time_accounting_and_working_limits", problems))

    # 5. hard constraints: booking dates, blocked dates, access windows, compatibility, one-day jobs
    problems = []
    for r in result.routes:
        vtype, etypes, skills = sc.bundle_capabilities(bundles[r.bundle_id])
        usable = sc.day_end_min - sc.day_start_min - sc.break_minutes
        for s in r.stops:
            j = sc.jobs[s.job_id]
            if (j.hard_earliest_date and r.day < j.hard_earliest_date) or \
                    (j.hard_latest_date and r.day > j.hard_latest_date) or r.day in j.blocked_dates:
                problems.append(f"{s.job_id}: scheduled outside hard dates")
            if (j.access_start_min is not None and s.work_start_min < j.access_start_min - TOL) or \
                    (j.access_end_min is not None and s.work_end_min > j.access_end_min + TOL):
                problems.append(f"{s.job_id}: outside access window")
            if (j.required_vehicle_type and j.required_vehicle_type != vtype) or \
                    (j.required_equipment_type and j.required_equipment_type not in etypes) or \
                    not set(j.required_skills) <= skills:
                problems.append(f"{s.job_id}: incompatible bundle {r.bundle_id}")
            if s.setup_min + s.service_min > usable + TOL:
                problems.append(f"{s.job_id}: exceeds one working day")
    checks.append(_ok("hard_constraints", problems))

    # 6. cost arithmetic: one cost set per bundle-day, amounts = quantity x rate
    problems = []
    sets = Counter((c["bundle_id"], c["day"], c["category"]) for c in cost_rows)
    problems += [f"{k} costed {n} times" for k, n in sets.items() if n > 1]
    routed = {(r.bundle_id, r.day) for r in result.routes}
    costed = {(c["bundle_id"], c["day"]) for c in cost_rows}
    if routed != costed:
        problems.append("cost rows do not match the set of bundle-day routes")
    for r in result.routes:
        legs_km = [km for *_, km in r.legs]
        km = None if any(k is None for k in legs_km) else sum(legs_km)
        persons = len(bundles[r.bundle_id].pilot_ids)
        expect_qty = {"trip": 1, "vehicle_day": 1, "distance_km": km, "fuel_km": km,
                      "personnel_person_day": persons, "allowance_person_day": persons}
        for c in (c for c in cost_rows if (c["bundle_id"], c["day"]) == (r.bundle_id, r.day)):
            if c["category"] in expect_qty:
                q = expect_qty[c["category"]]
                if (q is None) != (c["quantity"] is None) or (q is not None and abs(q - c["quantity"]) > TOL):
                    problems.append(f"{r.bundle_id} {r.day} {c['category']}: quantity mismatch")
            if c["amount_lkr"] is not None:
                if c["rate_lkr"] is None or abs(round(c["quantity"] * c["rate_lkr"], 2) - c["amount_lkr"]) > 0.005:
                    problems.append(f"{r.bundle_id} {r.day} {c['category']}: amount != quantity x rate")
    checks.append(_ok("cost_arithmetic", problems))
    return pd.DataFrame(checks)
