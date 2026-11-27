"""Rule-based scheduling baseline tests (fictional fixtures only)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agriflight.scheduling import run_folder
from agriflight.scheduling.outputs import due_date_window_deviation, window_deviation
from agriflight.scheduling.rule_baseline import NOT_SCHEDULED
from scheduling_fixtures import DAY1, DAY2, build_scenario, job, set_available, set_travel

DEMO = Path(__file__).resolve().parents[1] / "examples" / "scheduling_demo"
D1, D2 = date.fromisoformat(DAY1), date.fromisoformat(DAY2)


def _run(tmp_path, mutate=None):
    run = run_folder(build_scenario(tmp_path, mutate))
    assert run.checks_passed, run.frames["checks"].to_string()
    return run


def _reasons(run) -> dict[str, str]:
    return dict(zip(run.frames["unassigned"]["job_id"], run.frames["unassigned"]["reason_codes"]))


def test_base_case_schedules_both_jobs(tmp_path):
    run = _run(tmp_path)
    assert run.result.assignments == {"J1": ("B1", D1), "J2": ("B2", D1)}


def test_results_are_deterministic(tmp_path):
    a, b = _run(tmp_path / "a"), _run(tmp_path / "b")
    for name in ("itinerary", "assignments", "costs", "unassigned"):
        assert a.frames[name].equals(b.frames[name])
    demo1, demo2 = run_folder(DEMO), run_folder(DEMO)
    assert demo1.frames["itinerary"].equals(demo2.frames["itinerary"])


def test_resource_unavailable_moves_job_to_next_day(tmp_path):
    run = _run(tmp_path, lambda m, r: set_available(r, "P1", DAY1, "False"))
    assert run.result.assignments["J1"] == ("B1", D2)
    day1 = run.frames["bundle_days"].query("bundle_id == 'B1'").iloc[0]
    assert day1["reason"] == "RESOURCE_UNAVAILABLE" and "P1" in day1["detail"]


def test_missing_availability_row_means_not_available(tmp_path):
    run = _run(tmp_path, lambda m, r: set_available(r, "V1", DAY1, None))
    assert run.result.assignments["J1"] == ("B1", D2)


def test_shared_resource_cannot_be_double_booked(tmp_path):
    def mutate(m, r):
        r["bundles.csv"][1]["equipment_ids"] = "E1|E2"  # B2 also needs B1's drone
        r["jobs.csv"].append(job("J3", "S3"))
    run = _run(tmp_path, mutate)
    b2_day1 = run.frames["bundle_days"].query("bundle_id == 'B2'").iloc[0]
    assert b2_day1["reason"] == "RESOURCE_ALREADY_ASSIGNED" and "E1" in b2_day1["detail"]
    for day in (D1, D2):
        users = [rt.bundle_id for rt in run.result.routes if rt.day == day]
        assert len(users) <= 1  # E1 used by at most one bundle per day


def test_vehicle_and_skill_compatibility(tmp_path):
    def mutate(m, r):
        r["jobs.csv"] = [job("J4", "S3", required_vehicle_type="4wd", equipment="", skills=""),
                         job("J5", "S4", equipment="", skills="thermal")]
    run = _run(tmp_path, mutate)
    assert run.result.assignments["J4"][0] == "B2"  # only B2 has the 4wd
    assert _reasons(run)["J5"] == "NO_COMPATIBLE_BUNDLE"
    assert run.frames["unassigned"].iloc[0]["status"] == NOT_SCHEDULED


def test_travel_work_break_and_return_must_fit(tmp_path):
    # 30 travel + 10 setup + 360 work + 30 break + 30 return = 460 <= 480 -> fits
    run = _run(tmp_path, lambda m, r: r.update({"jobs.csv": [job("J6", "S1", area="360")]}))
    stop = run.frames["itinerary"].query("stop == 'J6'").iloc[0]
    assert stop["break_min"] == 30 and run.result.routes[0].return_min == 8 * 60 + 460
    # 400 work -> 500 > 480 -> not scheduled; travel/setup/work alone (440) would fit before the return leg
    run = _run(tmp_path / "x", lambda m, r: r.update({"jobs.csv": [job("J7", "S1", area="400")]}))
    assert _reasons(run)["J7"] == "DOES_NOT_FIT_WORKING_DAY"


def test_hard_dates_and_access_are_hard_preferred_window_is_soft(tmp_path):
    def mutate(m, r):
        r["jobs.csv"] = [
            job("J8", "S1", hard_earliest_date=DAY2, preferred_window_start="2031-01-01",
                preferred_window_end="2031-01-03", planning_due_date="2031-01-02"),
            job("J9", "S2", equipment="rgb_drone", access_start="08:00", access_end="08:45"),
            job("J10", "S3", blocked_dates=DAY1),
        ]
    run = _run(tmp_path, mutate)
    assert run.result.assignments["J8"][1] == D2  # hard earliest date respected
    row = run.frames["assignments"].set_index("job_id").loc["J8"]
    assert row["job_preferred_window_deviation_days"] == 4  # soft window violated, still scheduled and reported
    assert row["offset_from_due_date_days"] == 5
    assert row["operational_window_pm5_deviation_days"] == 0 and row["proposal_window_pm3_deviation_days"] == 2
    assert "ACCESS_WINDOW" in _reasons(run)["J9"]  # arrive 08:30 + 70 min > 08:45
    assert run.result.assignments["J10"][1] == D2


def test_missing_travel_is_not_zero(tmp_path):
    run = _run(tmp_path, lambda m, r: set_travel(r, "S1", "D1", None))
    assert _reasons(run)["J1"] == "MISSING_TRAVEL"


def test_asymmetric_travel_uses_each_direction(tmp_path):
    def mutate(m, r):
        set_travel(r, "D1", "S1", "30", "20")
        set_travel(r, "S1", "D1", "55", "31")
    run = _run(tmp_path, mutate)
    route = next(rt for rt in run.result.routes if rt.bundle_id == "B1")
    assert route.stops[0].travel_minutes == 30 and route.return_travel_minutes == 55
    km = run.frames["costs"].query("bundle_id == 'B1' and category == 'distance_km'")["quantity"].iloc[0]
    assert km == 51


def test_each_job_assigned_at_most_once(tmp_path):
    def mutate(m, r):
        r["jobs.csv"] = [job(f"J{i:02d}", f"S{1 + i % 4}", area="30") for i in range(12)]
    run = _run(tmp_path, mutate)
    stops = [s.job_id for rt in run.result.routes for s in rt.stops]
    assert len(stops) == len(set(stops)) == len(run.result.assignments)
    assert set(run.result.assignments) | set(_reasons(run)) == {f"J{i:02d}" for i in range(12)}


def test_oversized_job_flagged_multi_day_not_partially_scheduled(tmp_path):
    run = _run(tmp_path, lambda m, r: r.update({"jobs.csv": [job("J11", "S1", area="600")]}))
    assert _reasons(run)["J11"] == "MULTI_DAY_UNSUPPORTED"
    assert run.result.unsupported_multi_day == ["J11"] and not run.result.routes
    assert "not a statement about company capability" in run.frames["unassigned"]["detail"].iloc[0]


def test_capacity_used_reason_when_greedy_fills_days(tmp_path):
    def mutate(m, r):
        m["horizon_end"] = DAY1
        r["jobs.csv"] = [job("JA", "S1", area="300", due=DAY1), job("JB", "S3", area="300", due=DAY2)]
    run = _run(tmp_path, mutate)
    assert run.result.assignments["JA"] == ("B1", D1)
    assert _reasons(run)["JB"] == "CAPACITY_USED_BY_EARLIER_JOBS"


def test_no_job_fits_reports_bundle_day_status(tmp_path):
    run = _run(tmp_path, lambda m, r: r.update({"jobs.csv": [job("J1", "S1")]}))
    b1_day2 = run.frames["bundle_days"].query("bundle_id == 'B1'").iloc[1]
    assert b1_day2["reason"] == "NO_FEASIBLE_JOB"


def test_demo_scenario_expected_cases():
    run = run_folder(DEMO)
    assert run.checks_passed and run.result.scenario.is_synthetic
    reasons = dict(zip(run.frames["unassigned"]["job_id"], run.frames["unassigned"]["reason_codes"]))
    assert reasons == {"JOB_05": "MULTI_DAY_UNSUPPORTED", "JOB_06": "MISSING_TRAVEL",
                       "JOB_07": "DOES_NOT_FIT_WORKING_DAY", "JOB_08": "NO_COMPATIBLE_BUNDLE"}
    status = run.frames["bundle_days"].set_index(["bundle_id", "day"])["reason"]
    assert status[("TEAM_A", date(2030, 3, 5))] == "RESOURCE_UNAVAILABLE"
    assert status[("TEAM_C", date(2030, 3, 4))] == "RESOURCE_ALREADY_ASSIGNED"
    assert all(rt.bundle_id != "TEAM_C" or rt.day == date(2030, 3, 5) for rt in run.result.routes)
    # JOB_03 needs a 4wd: TEAM_C (car) never takes it even on the day it operates.
    assert run.result.assignments["JOB_03"][0] == "TEAM_A"


@pytest.mark.parametrize("offset, operational, proposal", [
    (-6, 1, 3), (-5, 0, 2), (-4, 0, 1), (-3, 0, 0), (0, 0, 0),
    (3, 0, 0), (4, 0, 1), (5, 0, 2), (6, 1, 3),
])
def test_due_date_window_boundaries_early_and_late(offset, operational, proposal):
    assert due_date_window_deviation(offset, 5) == operational
    assert due_date_window_deviation(offset, 3) == proposal


def test_custom_preferred_window_is_signed_and_not_replaced():
    start, end = date(2030, 2, 28), date(2030, 3, 4)
    assert window_deviation(date(2030, 2, 26), start, end) == -2
    assert window_deviation(date(2030, 3, 4), start, end) == 0
    assert window_deviation(date(2030, 3, 6), start, end) == 2


def test_demo_job_09_window_columns_are_distinct():
    row = run_folder(DEMO).frames["assignments"].set_index("job_id").loc["JOB_09"]
    assert (str(row["planning_due_date"]), str(row["scheduled_date"])) == ("2030-03-02", "2030-03-06")
    assert row["offset_from_due_date_days"] == 4
    assert row["operational_window_pm5"] == "2030-02-25 to 2030-03-07"
    assert row["operational_window_pm5_deviation_days"] == 0
    assert row["proposal_window_pm3"] == "2030-02-27 to 2030-03-05"
    assert row["proposal_window_pm3_deviation_days"] == 1
    assert row["job_preferred_window"] == "2030-02-28 to 2030-03-04"
    assert row["job_preferred_window_deviation_days"] == 2
