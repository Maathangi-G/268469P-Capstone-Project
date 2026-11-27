"""Tabular outputs of a schedule run (shared by the app view and the script)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from agriflight.scheduling.checker import check_schedule
from agriflight.scheduling.contracts import Scenario, format_hhmm, load_scenario
from agriflight.scheduling.costs import cost_summary, route_costs
from agriflight.scheduling.rule_baseline import ScheduleResult, build_schedule

DRAFT_NOTICE = ("Draft planning result from a rule-based baseline. Not dispatch authorisation; no weather, "
                "airspace or operational safety clearance is implied.")


@dataclass
class ScheduleRun:
    result: ScheduleResult
    frames: dict[str, pd.DataFrame]
    cost_summary: dict
    checks_passed: bool


def window_deviation(day, start, end) -> int:
    """Signed days outside an explicitly supplied window: negative = early, positive = late, 0 = inside."""
    if day < start:
        return -(start - day).days
    if day > end:
        return (day - end).days
    return 0


def due_date_window_deviation(offset_days: int, tolerance_days: int) -> int:
    """Days outside a symmetric +/-tolerance window around the planning due date: max(0, |offset| - tol)."""
    return max(0, abs(offset_days) - tolerance_days)


def summarize_result(result: ScheduleResult) -> ScheduleRun:
    """Costs, independent checks and tables for ANY schedule result (baseline or optimizer)."""
    costs = [row for r in result.routes for row in route_costs(result.scenario, r)]
    checks = check_schedule(result, costs)
    return ScheduleRun(result, _frames(result, costs, checks), cost_summary(costs), bool(checks["passed"].all()))


def run_scenario(scenario: Scenario) -> ScheduleRun:
    return summarize_result(build_schedule(scenario))


def run_folder(folder) -> ScheduleRun:
    return run_scenario(load_scenario(folder))


def _frames(result: ScheduleResult, costs: list[dict], checks: pd.DataFrame) -> dict[str, pd.DataFrame]:
    sc = result.scenario
    bundles = {b.bundle_id: b for b in sc.bundles}
    itinerary, assignments = [], []
    op_tol, prop_tol = sc.cadence["operational_tolerance_days"], sc.cadence["proposal_tolerance_days"]
    for r in sorted(result.routes, key=lambda x: (x.day, x.bundle_id)):
        b = bundles[r.bundle_id]
        base = {"day": r.day, "bundle_id": r.bundle_id, "pilots": "|".join(b.pilot_ids), "vehicle_id": b.vehicle_id,
                "equipment": "|".join(b.equipment_ids)}
        itinerary.append({**base, "seq": 0, "stop": "depart depot", "location_id": r.depot_location_id,
                          "departure": format_hhmm(r.start_min)})
        for i, s in enumerate(r.stops, 1):
            itinerary.append({**base, "seq": i, "stop": s.job_id, "location_id": s.location_id,
                              "travel_min": round(s.travel_minutes, 1), "distance_km": s.distance_km,
                              "arrival": format_hhmm(s.arrival_min), "wait_min": round(s.wait_min, 1),
                              "work_start": format_hhmm(s.work_start_min), "setup_min": round(s.setup_min, 1),
                              "service_min": round(s.service_min, 1), "work_end": format_hhmm(s.work_end_min),
                              "break_min": s.break_min, "departure": format_hhmm(s.departure_min)})
            job = sc.jobs[s.job_id]
            due = job.planning_due_date
            offset = (r.day - due).days
            assignments.append({
                "job_id": s.job_id, "division_id": job.division_id, "scheduled_date": r.day,
                "bundle_id": r.bundle_id, "planning_due_date": due,
                "offset_from_due_date_days": offset,  # signed: negative = before due date
                f"operational_window_pm{op_tol}": f"{due - timedelta(days=op_tol)} to {due + timedelta(days=op_tol)}",
                f"operational_window_pm{op_tol}_deviation_days": due_date_window_deviation(offset, op_tol),
                f"proposal_window_pm{prop_tol}": f"{due - timedelta(days=prop_tol)} to {due + timedelta(days=prop_tol)}",
                f"proposal_window_pm{prop_tol}_deviation_days": due_date_window_deviation(offset, prop_tol),
                "job_preferred_window": f"{job.preferred_window_start} to {job.preferred_window_end}",
                "job_preferred_window_deviation_days": window_deviation(r.day, job.preferred_window_start,
                                                                        job.preferred_window_end),
                "input_status": job.input_status})
        itinerary.append({**base, "seq": len(r.stops) + 1, "stop": "return depot", "location_id": r.depot_location_id,
                          "travel_min": round(r.return_travel_minutes, 1), "distance_km": r.return_distance_km,
                          "arrival": format_hhmm(r.return_min)})
    assumptions = [
        ("scenario_id", sc.scenario_id), ("data_origin", sc.data_origin), ("provenance", sc.provenance),
        ("timezone", "Asia/Colombo (local dates and times)"),
        ("horizon", f"{sc.horizon[0]} to {sc.horizon[-1]}" if sc.horizon else "empty"),
        ("working_day", f"{format_hhmm(sc.day_start_min)}-{format_hhmm(sc.day_end_min)}, break {sc.break_minutes} min "
                        f"once the day exceeds {sc.break_after_minutes} min"),
        ("capacity_mode", "declared_assumption (explicit work rates / durations; no ML prediction)"),
        ("cadence", f"target {sc.cadence['target_interval_days']} d; operational +/-{op_tol} d and proposal "
                    f"+/-{prop_tol} d windows around each planning due date reported separately "
                    "(deviation = max(0, |offset| - tolerance)); each job's own preferred window reported "
                    "separately (signed); all are soft"),
        ("resource_policy", "a physical resource used by a bundle is reserved for that whole day; bundles are "
                            "considered in bundle_id order; no within-day handover (conservative version-1 rule)"),
        ("constraints_included", ", ".join(sc.constraints_included)),
        ("constraints_excluded", ", ".join(sc.constraints_excluded)),
        ("cost_categories_included", ", ".join(sc.cost_categories_included)),
        ("route_model", "return to depot daily; no overnight stays; no job splitting; one-day jobs only"),
        ("notice", DRAFT_NOTICE),
    ]
    status = pd.DataFrame(result.bundle_day_status)
    return {
        "itinerary": pd.DataFrame(itinerary),
        "assignments": pd.DataFrame(assignments),
        "costs": pd.DataFrame(costs),
        "unassigned": pd.DataFrame(result.unassigned, columns=["job_id", "division_id", "status", "reason_codes", "detail"]),
        "bundle_days": status,
        "checks": checks,
        "assumptions": pd.DataFrame(assumptions, columns=["item", "value"]),
        "input_issues": pd.DataFrame(sc.issues, columns=["severity", "file", "record_id", "field", "message"]),
    }
