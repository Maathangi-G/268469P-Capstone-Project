"""Cost estimation, independent checker and input-contract tests (fictional fixtures)."""

from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from agriflight.scheduling import ScenarioError, load_scenario, run_folder
from agriflight.scheduling.checker import check_schedule
from agriflight.scheduling.costs import route_costs
from agriflight.scheduling.rule_baseline import build_schedule
from scheduling_fixtures import DAY1, build_scenario, set_travel

REPO = Path(__file__).resolve().parents[1]


def _costs(run, bundle):
    frame = run.frames["costs"].query("bundle_id == @bundle")
    return dict(zip(frame["category"], zip(frame["amount_lkr"], frame["status"])))


# -------------------------------------------------------------------- costs
def test_cost_arithmetic_and_all_inclusive_rate(tmp_path):
    run = run_folder(build_scenario(tmp_path))
    b1 = _costs(run, "B1")  # car: 2 legs x 20 km, all-inclusive km rate
    assert b1["trip"][0] == 100 and b1["vehicle_day"][0] == 1000
    assert b1["distance_km"][0] == 400 and b1["fuel_km"][1].startswith("included_in_rate")
    assert b1["personnel_person_day"][0] == 500 and b1["allowance_person_day"][0] == 50
    b2 = _costs(run, "B2")  # 4wd: fuel charged separately
    assert b2["distance_km"][0] == 200 and b2["fuel_km"][0] == 120
    assert b1["accommodation"][1] == "not_applicable_return_to_base"
    # B1: 100 + 1000 + 400 + 500 + 50 = 2050; B2: 100 + 2000 + 200 + 120 + 500 + 50 = 2970
    assert run.cost_summary["estimated_known_total_lkr"] == 2050 + 2970
    assert run.cost_summary["coverage_complete"]


def test_missing_and_unknown_rates_are_not_zero(tmp_path):
    def mutate(m, r):
        r["cost_rates.csv"] = [x for x in r["cost_rates.csv"] if x["category"] != "allowance_person_day"]
        next(x for x in r["cost_rates.csv"] if x["rate_id"] == "R_TRIP")["amount_lkr"] = ""
    run = run_folder(build_scenario(tmp_path, mutate))
    frame = run.frames["costs"].query("bundle_id == 'B1'").set_index("category")
    assert frame.loc["allowance_person_day", "status"] == "rate_not_configured"
    assert frame.loc["trip", "status"] == "rate_unknown"
    assert frame.loc["trip", "amount_lkr"] != frame.loc["trip", "amount_lkr"]  # NaN, not 0
    assert not run.cost_summary["coverage_complete"]
    assert "trip (rate_unknown)" in run.cost_summary["missing_components"]


def test_explicit_zero_rate_differs_from_missing_rate(tmp_path):
    def mutate(m, r):
        next(x for x in r["cost_rates.csv"] if x["rate_id"] == "R_ALLOW")["amount_lkr"] = "0"
    run = run_folder(build_scenario(tmp_path, mutate))
    frame = run.frames["costs"].query("bundle_id == 'B1'").set_index("category")
    assert frame.loc["allowance_person_day", "status"] == "estimated"
    assert frame.loc["allowance_person_day", "amount_lkr"] == 0.0  # explicit zero, counted as covered
    assert run.cost_summary["coverage_complete"]


def test_excluded_category_is_not_counted_as_missing(tmp_path):
    def mutate(m, r):
        m["cost_categories_included"] = ["trip", "vehicle_day", "distance_km", "fuel_km", "personnel_person_day"]
    run = run_folder(build_scenario(tmp_path, mutate))
    assert _costs(run, "B1")["allowance_person_day"][1] == "excluded_by_scenario"
    assert run.cost_summary["coverage_complete"]


def test_unknown_distance_keeps_distance_cost_unknown(tmp_path):
    def mutate(m, r):
        set_travel(r, "S1", "D1", "30", "")
    run = run_folder(build_scenario(tmp_path, mutate))
    assert _costs(run, "B1")["distance_km"][1] == "distance_unknown"


def test_one_cost_set_per_bundle_day(tmp_path):
    run = run_folder(build_scenario(tmp_path))
    counts = run.frames["costs"].groupby(["bundle_id", "day", "category"]).size()
    assert (counts == 1).all()
    assert len(run.frames["costs"].query("category == 'trip'")) == len(run.result.routes)


# ------------------------------------------------------------------ checker
def test_checker_detects_duplicate_costs_and_time_tampering(tmp_path):
    scenario = load_scenario(build_scenario(tmp_path))
    result = build_schedule(scenario)
    costs = [row for rt in result.routes for row in route_costs(scenario, rt)]
    assert check_schedule(result, costs)["passed"].all()
    duplicated = check_schedule(result, costs + [costs[0]]).set_index("check")
    assert not duplicated.loc["cost_arithmetic", "passed"]
    route = result.routes[0]
    bad_stop = dataclasses.replace(route.stops[0], work_end_min=route.stops[0].work_end_min - 5)
    result.routes[0] = dataclasses.replace(route, stops=(bad_stop,) + route.stops[1:])
    tampered = check_schedule(result, costs).set_index("check")
    assert not tampered.loc["time_accounting_and_working_limits", "passed"]


def test_checker_detects_shared_resource_conflict(tmp_path):
    scenario = load_scenario(build_scenario(tmp_path))
    result = build_schedule(scenario)
    b2 = next(b for b in scenario.bundles if b.bundle_id == "B2")
    scenario.bundles[1] = dataclasses.replace(b2, equipment_ids=("E1", "E2"))  # now shares E1 with B1 on DAY1
    costs = [row for rt in result.routes for row in route_costs(scenario, rt)]
    checks = check_schedule(result, costs).set_index("check")
    assert not checks.loc["resource_conflicts_and_availability", "passed"]


# ------------------------------------------------------------ input contract
@pytest.mark.parametrize("mutate, message", [
    (lambda m, r: m.update({"timezone": "UTC"}), "Asia/Colombo"),
    (lambda m, r: m.update({"capacity_mode": "ml_prediction"}), "declared_assumption"),
    (lambda m, r: r["bundles.csv"][0].update({"pilot_ids": "P9"}), "unknown pilot"),
    (lambda m, r: r["travel.csv"][0].update({"travel_minutes": "-5"}), "non-negative"),
    (lambda m, r: r["travel.csv"].append(dict(r["travel.csv"][0])), "duplicate directed travel"),
    (lambda m, r: r["availability.csv"][0].update({"available": "yes"}), "True or False"),
    (lambda m, r: r["jobs.csv"][0].update({"planning_due_date": "06/01/2031"}), "YYYY-MM-DD"),
    (lambda m, r: r["jobs.csv"][0].update({"input_status": "maybe"}), "input_status"),
    (lambda m, r: r["cost_rates.csv"].append({"rate_id": "R_X", "category": "accommodation", "applies_to": "*",
                                              "amount_lkr": "1", "input_status": "assumption", "provenance": "x"}),
     "unsupported category"),
    (lambda m, r: m.pop("working_day"), "working_day"),
])
def test_invalid_inputs_raise_with_explanations(tmp_path, mutate, message):
    with pytest.raises(ScenarioError) as exc:
        load_scenario(build_scenario(tmp_path, mutate))
    assert message in str(exc.value) or any(message in i["message"] or message in i["field"] for i in exc.value.issues)


def test_missing_files_are_listed(tmp_path):
    with pytest.raises(ScenarioError) as exc:
        load_scenario(build_scenario(tmp_path, drop=("travel.csv", "availability.csv")))
    missing = {i["file"] for i in exc.value.issues if i["message"] == "required input file is missing"}
    assert missing == {"travel.csv", "availability.csv"}


def test_job_without_area_or_duration_is_warned_and_unscheduled(tmp_path):
    def mutate(m, r):
        r["jobs.csv"][0].update({"required_area_ha": "", "service_duration_min": ""})
    run = run_folder(build_scenario(tmp_path, mutate))
    assert any(i["severity"] == "warning" for i in run.result.scenario.issues)
    assert "NO_SERVICE_DURATION" in run.frames["unassigned"].set_index("job_id").loc["J1", "reason_codes"]


# ------------------------------------------------------------------- script
def _script():
    spec = importlib.util.spec_from_file_location("run_schedule", REPO / "scripts" / "run_schedule.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_runs_demo_without_private_data(capsys, monkeypatch):
    monkeypatch.delenv("AGRIFLIGHT_DATA_DIR", raising=False)
    assert _script().main([]) == 0
    assert "FICTIONAL DEMO SCENARIO" in capsys.readouterr().out


def test_script_refuses_outputs_inside_repository():
    assert _script().main(["--output-dir", str(REPO / "outputs_test")]) == 2
    assert not (REPO / "outputs_test").exists()


def test_script_reports_missing_inputs_for_private_scenario(tmp_path, capsys):
    folder = build_scenario(tmp_path, lambda m, r: m.update({"data_origin": "approved_private"}),
                            drop=("bundles.csv",))
    assert _script().main(["--scenario-dir", str(folder), "--output-dir", str(tmp_path / "out")]) == 2
    assert "bundles.csv" in capsys.readouterr().err


def test_script_writes_private_scenario_outputs_outside_repo(tmp_path):
    folder = build_scenario(tmp_path, lambda m, r: m.update({"data_origin": "approved_private"}))
    out = tmp_path / "Analysis_Private" / "scheduling"
    assert _script().main(["--scenario-dir", str(folder), "--output-dir", str(out)]) == 0
    assert (out / "itinerary.csv").exists() and (out / "run_metadata.json").exists()
