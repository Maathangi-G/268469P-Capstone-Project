from __future__ import annotations

from agriflight.operational import coverage
from agriflight.operational.loader import load_package
from agriflight.operational.validation import validate_operational
from operational_fixtures import build_package


def _report(ds):
    report, reasons = coverage.feasibility_report(ds)
    return report.set_index(["table", "target_column"]), reasons


def _reasons_for(reasons, table):
    part = reasons[reasons["table"] == table]
    return dict(zip(part["exclusion_reason"], part["records"]))


def test_empty_template_and_no_verified_targets_block_training(tmp_path):
    ds = load_package(build_package(tmp_path))
    assert validate_operational(ds).empty  # an empty template is not an error
    report, _ = _report(ds)
    template = report.loc[("daily_coverage_template", "measured_covered_ha")]
    assert template["records"] == 0 and template["eligible_for_modelling"] == 0
    assert int(report["eligible_for_modelling"].sum()) == 0
    blocked, message = coverage.training_status(report.reset_index())
    assert blocked and message == coverage.BLOCKED_MESSAGE


def test_categories_kept_distinct_and_non_observed_never_eligible(tmp_path):
    report, _ = _report(load_package(build_package(tmp_path)))
    planned = report.loc[("planned_team_days", "planned_coverage_ha")]
    assert planned["category"] == coverage.PLANNED and planned["nonmissing_numeric_ha"] == 1
    assert planned["eligible_for_modelling"] == 0
    static = report.loc[("area_evidence", "boundary_area_ha")]
    assert static["category"] == coverage.STATIC and static["eligible_for_modelling"] == 0


def test_flags_are_recalculated_not_changed(tmp_path):
    ds = load_package(build_package(tmp_path))
    before = ds.raw["daily_work_evidence"][["target_measured", "training_eligible"]].copy()
    coverage.feasibility_report(ds)
    assert ds.raw["daily_work_evidence"][["target_measured", "training_eligible"]].equals(before)
    report, reasons = _report(ds)
    assert report.loc[("daily_work_evidence", "actual_covered_ha"), "eligible_for_modelling"] == 0
    texts = set(reasons["exclusion_reason"])
    assert "target_measured not True" in texts and "training_eligible not True" in texts
    assert any(t.startswith("supplied blocking_reason:") for t in texts)


def test_invalid_nonfinite_negative_values_are_excluded_with_reasons(tmp_path):
    def mutate(rows, _cols):
        for row, value in zip(rows["daily_work_evidence"], ["inf", "-2"]):
            row.update({"actual_covered_ha": value, "target_measured": "True", "training_eligible": "True"})
    report, reasons = _report(load_package(build_package(tmp_path, mutate)))
    assert report.loc[("daily_work_evidence", "actual_covered_ha"), "eligible_for_modelling"] == 0
    got = _reasons_for(reasons, "daily_work_evidence")
    assert got["target value not finite"] == 1 and got["target value negative"] == 1


def test_verified_zero_is_eligible_but_missing_is_not(tmp_path):
    def mutate(rows, _cols):
        base = {"division_id": "DIV_T1", "work_date": "2026-02-01", "team_id": "TEAM_T1",
                "independent_label_verified": "True", "measurement_method": "fixture"}
        rows["daily_coverage_template"] = [
            {**base, "daily_work_id": "DCW_T1", "measured_covered_ha": "0"},
            {**base, "daily_work_id": "DCW_T2", "measured_covered_ha": ""},
            {**base, "daily_work_id": "DCW_T3", "measured_covered_ha": "8.5", "independent_label_verified": "False"},
            {**base, "daily_work_id": "DCW_T4", "measured_covered_ha": "abc"},
        ]
    ds = load_package(build_package(tmp_path, mutate))
    report, reasons = _report(ds)
    row = report.loc[("daily_coverage_template", "measured_covered_ha")]
    assert row["records"] == 4 and row["eligible_for_modelling"] == 1 and row["eligible_distinct_dates"] == 1
    got = _reasons_for(reasons, "daily_coverage_template")
    assert got["target value missing (not treated as zero)"] == 1
    assert got["target value not numeric"] == 1
    assert got["independent_label_verified not True"] == 1
    frame = coverage.eligible_training_frame(ds, "daily_coverage_template", "measured_covered_ha")
    assert frame["target_ha"].tolist() == [0.0]
    blocked, _ = coverage.training_status(report.reset_index())
    assert not blocked


def test_feature_availability_has_three_classes():
    classes = set(coverage.feature_availability()["availability"])
    assert classes == {"known when preparing a schedule", "known only after work happens",
                       "uncertain timing / provenance"}
