"""CP-SAT optimizer tests (fictional scenarios only). Skipped if OR-Tools is not installed."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("ortools")
from ortools.sat.python import cp_model  # noqa: E402

from agriflight.scheduling import load_scenario  # noqa: E402
from agriflight.scheduling import optimizer as opt  # noqa: E402
from agriflight.scheduling.costs import route_costs  # noqa: E402
from agriflight.scheduling.outputs import summarize_result  # noqa: E402
from scheduling_fixtures import DAY1, DAY2, build_scenario, job, set_available, set_travel  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "examples"
CMP = EX / "scheduling_comparison"
CFG = opt.OptimizerConfig(time_limit_s=20, random_seed=7, num_workers=1)


def _solve(folder, cfg=CFG):
    sc = load_scenario(folder)
    out = opt.optimize(sc, cfg)
    run = summarize_result(out.result) if out.result is not None else None
    if run is not None:
        assert run.checks_passed, run.frames["checks"].to_string()
    return sc, out, run


def _values(out):
    return [s["objective_value"] for s in out.stages]


def test_tiny_manual_optimum():
    _, out, run = _solve(CMP / "c1_tiny_manual")
    assert out.status_label == opt.LABEL_OPTIMAL
    assert _values(out) == [2, 0, 1800]  # 2 jobs, 0 days outside, 30 min = DEP->A->B->DEP
    route = run.result.routes[0]
    assert [s.job_id for s in route.stops] == ["JA", "JB"]  # unique optimum here


def test_route_continuation_without_direct_depot_edges():
    _, out, run = _solve(CMP / "c5_route_continuation")
    stops = [s.job_id for s in run.result.routes[0].stops]
    assert stops == ["A", "X"] and _values(out)[0] == 2


def test_missing_edges_never_become_zero_travel(tmp_path):
    def mutate(m, r):
        for other in ("D1", "D2", "S2", "S3", "S4"):
            set_travel(r, "S1", other, None)  # S1 has no outgoing edge at all
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert "J1" not in run.result.assignments
    assert run.frames["unassigned"].set_index("job_id").loc["J1", "reason_codes"] == "NO_TRAVEL_CONNECTION"


def test_shared_resource_is_not_double_booked(tmp_path):
    def mutate(m, r):
        m["horizon_end"] = DAY1
        r["bundles.csv"][1]["equipment_ids"] = "E1|E2"  # B2 shares B1's drone
        r["jobs.csv"] = [job("J1", "S1"), job("J3", "S3"), job("J2", "S2", equipment="ms_drone", skills="ms")]
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert len({rt.bundle_id for rt in run.result.routes}) <= 1  # E1 used by one bundle on the single day


def test_unavailable_resource_removes_team_day(tmp_path):
    def mutate(m, r):
        m["horizon_end"] = DAY1
        set_available(r, "P2", DAY1, "False")
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert "J2" not in run.result.assignments  # only B2 can do the ms job
    assert run.frames["unassigned"].set_index("job_id").loc["J2", "reason_codes"] == "RESOURCES_UNAVAILABLE"


def test_waiting_break_and_return_are_accounted(tmp_path):
    def mutate(m, r):
        m["horizon_end"] = DAY1
        r["jobs.csv"] = [job("JW", "S1", area="60", access_start="10:00", access_end="16:00"),
                         job("JL", "S2", area="180")]
        r["jobs.csv"][1].update(required_equipment_type="rgb_drone", required_skills="rgb")
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    stops = {s.job_id: s for s in run.result.routes[0].stops}
    assert set(stops) == {"JW", "JL"}
    assert sum(s.break_min for s in stops.values()) == 30  # day exceeds 240 min
    if stops["JW"].arrival_min < 600:
        assert stops["JW"].wait_min > 0 and stops["JW"].work_start_min == 600
    assert run.result.routes[0].return_min <= 16 * 60


def test_access_window_is_hard(tmp_path):
    def mutate(m, r):
        r["jobs.csv"] = [job("J9", "S1", access_start="08:00", access_end="08:45")]  # 30 travel + 70 work
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert run.result.assignments == {}
    assert out.status_label == opt.LABEL_OPTIMAL  # an empty schedule can be the proven optimum


def test_early_and_late_window_deviation_are_absolute(tmp_path):
    def mutate(m, r):
        m["horizon_end"] = DAY1
        r["jobs.csv"] = [job("JL", "S1", preferred_window_start="2031-01-01", preferred_window_end="2031-01-04"),
                         job("JE", "S3", preferred_window_start="2031-01-09", preferred_window_end="2031-01-12")]
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert set(run.result.assignments) == {"JL", "JE"}
    assert _values(out)[1] == 2 + 3  # late 2 days + early 3 days; they do not cancel
    a = run.frames["assignments"].set_index("job_id")["job_preferred_window_deviation_days"]
    assert a["JL"] == 2 and a["JE"] == -3  # signed values kept for explanation


def test_window_priority_beats_travel(tmp_path):
    def mutate(m, r):
        r["jobs.csv"] = [job("J1", "S1", preferred_window_start=DAY2, preferred_window_end=DAY2,
                             equipment="", skills="")]
        set_available(r, "P2", DAY1, "False")  # B2 (far) only on DAY2; B1 (near) only on DAY1
        set_available(r, "P1", DAY2, "False")
        set_travel(r, "D1", "S1", "10")
        set_travel(r, "S1", "D1", "10")
        set_travel(r, "D2", "S1", "60")
        set_travel(r, "S1", "D2", "60")
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert run.result.assignments["J1"] == ("B2", date.fromisoformat(DAY2))
    assert _values(out) == [1, 0, 120 * 60]  # in-window with longer travel beats out-of-window short travel


def test_job_count_priority_beats_travel(tmp_path):
    def mutate(m, r):
        m["horizon_end"] = DAY1
        r["jobs.csv"] = [job("J1", "S1"), job("J3", "S3")]
        set_travel(r, "S1", "S3", "100")
        set_travel(r, "S3", "D1", "100")
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert _values(out)[0] == 2  # both jobs although a one-job route travels less


def test_single_assignment_and_connected_routes():
    _, out, run = _solve(EX / "scheduling_demo")
    stops = [s.job_id for rt in run.result.routes for s in rt.stops]
    assert len(stops) == len(set(stops)) == len(run.result.assignments)
    checks = run.frames["checks"].set_index("check")["passed"]
    assert checks["route_continuity"] and checks["unique_job_assignment"]


def test_cost_parity_uses_shared_module():
    sc, out, run = _solve(EX / "scheduling_demo")
    recomputed = [row for rt in out.result.routes for row in route_costs(sc, rt)]
    assert len(recomputed) == len(run.frames["costs"])
    assert "allowance_person_day (rate_unknown)" in run.cost_summary["missing_components"]
    assert not run.cost_summary["coverage_complete"]  # missing allowance stays unknown


class _UnknownSolver:
    """Stands in for a solve that hit its limits without finding a solution."""
    wall_time = 0.0

    def status_name(self, status):
        return "UNKNOWN"


def test_unproven_stage_is_reported(monkeypatch):
    real = opt._Model.solve

    def fake(self, stage, maximize, limit, cfg, hint=None):
        if stage == opt.STAGES[2]:
            return _UnknownSolver(), cp_model.UNKNOWN
        return real(self, stage, maximize, limit, cfg, hint)
    monkeypatch.setattr(opt._Model, "solve", fake)
    _, out, run = _solve(CMP / "c1_tiny_manual")
    assert out.status_label == opt.LABEL_FEASIBLE and out.stages[2]["status"] == "UNKNOWN"
    assert run is not None and len(run.result.assignments) == 2  # stage-2 solution kept


def test_no_solution_is_not_called_infeasible_and_fallback_is_labelled(monkeypatch):
    monkeypatch.setattr(opt._Model, "solve", lambda *a, **k: (_UnknownSolver(), cp_model.UNKNOWN))
    sc = load_scenario(CMP / "c1_tiny_manual")
    out = opt.optimize(sc, CFG)
    assert out.status_label == opt.LABEL_NO_SOLUTION and out.result is None and out.method == "none"
    fb = opt.optimize(sc, opt.OptimizerConfig(fallback_to_baseline=True))
    assert fb.fallback_used and fb.method == "rule_baseline_fallback" and "FALLBACK" in fb.message


def test_status_labels():
    s = lambda *names: [{"status": n} for n in names]  # noqa: E731
    assert opt._status_label(s("MODEL_INVALID")) == opt.LABEL_INVALID
    assert opt._status_label(s("INFEASIBLE")) == opt.LABEL_INFEASIBLE
    assert opt._status_label(s("UNKNOWN")) == opt.LABEL_NO_SOLUTION
    assert opt._status_label(s("OPTIMAL", "FEASIBLE", "OPTIMAL")) == opt.LABEL_FEASIBLE


def test_invalid_itinerary_is_rejected(monkeypatch):
    def broken(*a, **k):
        raise opt.RouteInfeasible("TEST", "forced")
    monkeypatch.setattr(opt, "simulate_route", broken)
    out = opt.optimize(load_scenario(CMP / "c1_tiny_manual"), CFG)
    assert out.status_label == opt.LABEL_REJECTED and out.result is None


def test_empty_schedule_is_valid_not_a_failure(tmp_path):
    def mutate(m, r):
        r["jobs.csv"] = [job("JT", "S1", equipment="thermal_camera", skills="thermal")]
    _, out, run = _solve(build_scenario(tmp_path, mutate))
    assert out.status_label == opt.LABEL_OPTIMAL and run.result.routes == []
    assert run.cost_summary["estimated_known_total_lkr"] == 0.0
    assert run.frames["unassigned"].iloc[0]["reason_codes"] == "NO_COMPATIBLE_BUNDLE"


def test_reproducible_with_fixed_seed():
    a = _solve(EX / "scheduling_demo")[1]
    b = _solve(EX / "scheduling_demo")[1]
    assert _values(a) == _values(b)
