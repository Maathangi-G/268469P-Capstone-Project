"""Comparison metrics, script and UI tests (fictional scenarios). Skipped without OR-Tools."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("ortools")

from agriflight.scheduling.comparison import assess, compare_folder, pct_change, scenario_hash  # noqa: E402
from agriflight.scheduling.optimizer import OptimizerConfig  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CMP = REPO / "examples" / "scheduling_comparison"
CFG = OptimizerConfig(time_limit_s=20, random_seed=7, num_workers=1)


def _metric(comp, name, column):
    return comp.table.set_index("metric").loc[name, column]


def test_pct_change_handles_zero_and_unknown():
    assert pct_change(0, 0) == "0%"
    assert pct_change(0, 5).startswith("n/a")
    assert pct_change(None, 5).startswith("n/a")
    assert pct_change(10, 5) == "-50.0%"


def test_different_job_sets_are_disclosed_and_unscheduled_not_compliant():
    comp = compare_folder(CMP / "c4_windows_asymmetric", CFG)
    assert comp.same_job_set is False
    assert any("Different scheduled job sets" in n for n in comp.notes)
    assert _metric(comp, "operational_pm5_compliant", "baseline") == "2 of 3 jobs (2 of 2 scheduled)"
    assert _metric(comp, "operational_pm5_compliant", "optimizer") == "3 of 3 jobs (3 of 3 scheduled)"
    assert _metric(comp, "unscheduled_ids", "baseline") == "Q"


def test_baseline_recomputed_not_hardcoded_and_tie_case():
    comp = compare_folder(CMP / "c2_baseline_good", CFG)
    assert assess(comp) == "tied on the stated objective"
    assert _metric(comp, "known_estimated_cost_lkr", "baseline") == _metric(comp, "known_estimated_cost_lkr", "optimizer")


def test_demo_same_jobs_and_cost_incomplete_for_both():
    comp = compare_folder(REPO / "examples" / "scheduling_demo", CFG)
    assert comp.same_job_set is True
    assert _metric(comp, "cost_coverage_complete", "baseline") == "False"
    assert _metric(comp, "cost_coverage_complete", "optimizer") == "False"
    assert comp.baseline.checks_passed and comp.optimizer_run.checks_passed


def test_empty_baseline_metrics_are_safe():
    comp = compare_folder(CMP / "c5_route_continuation", CFG)
    assert _metric(comp, "scheduled_count", "baseline") == "0"
    assert _metric(comp, "known_estimated_cost_lkr", "baseline") == "0.0"
    assert "n/a (baseline is 0)" in _metric(comp, "scheduled_count", "difference (optimizer - baseline)")


def test_scenario_hash_changes_with_inputs(tmp_path):
    import shutil
    copy = tmp_path / "c1"
    shutil.copytree(CMP / "c1_tiny_manual", copy)
    before = scenario_hash(copy)
    (copy / "jobs.csv").write_text((copy / "jobs.csv").read_text() + "\n", encoding="utf-8")
    assert scenario_hash(copy) != before


def _script():
    spec = importlib.util.spec_from_file_location("compare_schedulers", REPO / "scripts" / "compare_schedulers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_runs_and_refuses_output_in_repo(capsys, tmp_path):
    assert _script().main(["--scenario-dir", str(CMP / "c1_tiny_manual")]) == 0
    assert "C1_TINY_MANUAL" in capsys.readouterr().out
    assert _script().main(["--scenario-dir", str(CMP / "c1_tiny_manual"),
                           "--output-dir", str(REPO / "cmp_out_test")]) == 2
    out = tmp_path / "Analysis_Private" / "cmp"
    assert _script().main(["--scenario-dir", str(CMP / "c1_tiny_manual"), "--output-dir", str(out)]) == 0
    assert (out / "run_metadata.json").exists() and (out / "c1_tiny_manual" / "comparison.csv").exists()


def test_comparison_ui_runs_only_on_button():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(REPO / "app" / "app.py"), default_timeout=120).run()
    assert not at.exception
    assert any("Press **Run optimizer comparison**" in str(i.value) for i in at.info)
    at.selectbox(key="cmp_scenario").set_value("c1_tiny_manual").run()
    at.button(key="cmp_run").click().run()
    assert not at.exception
    assert any("Verdict on the stated objective" in str(m.value) for m in at.markdown)
    at.number_input(key="cmp_limit").set_value(5.0).run()  # settings changed -> stale result hidden
    assert any("Press **Run optimizer comparison**" in str(i.value) for i in at.info)
