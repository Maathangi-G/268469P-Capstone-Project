"""Rounding and baseline-equivalence checks (fictional scenarios). Skipped without OR-Tools."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("ortools")

from agriflight.scheduling import load_scenario  # noqa: E402
from agriflight.scheduling.equivalence import baseline_in_model, baseline_objectives, rounding_audit  # noqa: E402
from agriflight.scheduling.optimizer import OptimizerConfig, optimize  # noqa: E402
from agriflight.scheduling.rule_baseline import build_schedule  # noqa: E402
from scheduling_fixtures import DAY1, build_scenario, job, set_travel  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "examples"
SCENARIOS = [EX / "scheduling_demo"] + sorted(p for p in (EX / "scheduling_comparison").iterdir() if p.is_dir())
CFG = OptimizerConfig(time_limit_s=20, random_seed=42, num_workers=1)


@pytest.mark.parametrize("folder", SCENARIOS, ids=lambda p: p.name)
def test_existing_scenarios_have_no_rounding_and_baseline_fits_model(folder):
    sc = load_scenario(folder)
    audit = rounding_audit(sc)
    assert (audit["rounding_added_s"] == 0).all()  # integer conversion changes nothing here
    base = build_schedule(sc)
    assert baseline_in_model(sc, base, CFG)["feasible"]  # hard-constrained, not a hint
    out = optimize(sc, CFG)
    b = baseline_objectives(sc, base)
    o = [int(s["objective_value"]) for s in out.stages]
    key = lambda jobs, days, travel: (-jobs, days, travel)  # noqa: E731
    assert key(*o) <= key(b["scheduled_jobs"], b["preferred_window_days_outside"], b["travel_seconds_solver_units"])


def _boundary(tmp_path, service="380.0078125"):
    # Exact minutes: 29.9921875 travel + 10 setup + 380.0078125 work + 30 break + 30 return = 480.0 (08:00-16:00).
    # Binary-exact fractions so the exact timeline lands precisely on 16:00.
    def mutate(m, r):
        m["horizon_end"] = DAY1
        r["jobs.csv"] = [job("JF", "S1", area="", service_duration_min=service, setup_min="10")]
        set_travel(r, "D1", "S1", "29.9921875")
        set_travel(r, "S1", "D1", "30")
    return load_scenario(build_scenario(tmp_path, mutate))


def test_fractional_rounding_accumulates_and_is_conservative_at_boundary(tmp_path):
    sc = _boundary(tmp_path)
    changed = rounding_audit(sc).query("rounding_added_s > 0")
    assert set(changed["kind"]) == {"travel", "service"}
    assert changed.query("item == 'JF@B1'")["rounding_added_s"].iloc[0] == pytest.approx(0.53125)
    assert changed.query("item == 'D1->S1'")["rounding_added_s"].iloc[0] == pytest.approx(0.46875)
    base = build_schedule(sc)
    assert "JF" in base.assignments and base.routes[0].return_min == 16 * 60  # exact timing fits exactly
    out = optimize(sc, CFG)
    assert "JF" not in out.result.assignments  # rounded-up seconds overrun 16:00 by 1 s in total
    assert baseline_in_model(sc, base, CFG)["status"] == "INFEASIBLE"


def test_fractional_rounding_harmless_away_from_boundary(tmp_path):
    sc = _boundary(tmp_path, service="379.0078125")
    out = optimize(sc, CFG)
    assert "JF" in out.result.assignments
    assert baseline_in_model(sc, build_schedule(sc), CFG)["feasible"]
