from __future__ import annotations

from agriflight.operational.loader import load_package
from agriflight.operational.validation import validate_operational
from operational_fixtures import build_package


def _findings(tmp_path, mutate):
    return validate_operational(load_package(build_package(tmp_path, mutate)))


def _pairs(findings, *cols):
    return set(zip(*(findings[c] for c in cols)))


def test_missing_required_column(tmp_path):
    def mutate(_rows, cols):
        cols["budget_fuel_trips"].remove("recomputed_fuel_cost_lkr")

    findings = _findings(tmp_path, mutate)
    assert ("required_column_missing", "budget_fuel_trips", "recomputed_fuel_cost_lkr") in _pairs(
        findings, "check", "table", "column")


def test_simple_foreign_key_orphan(tmp_path):
    def mutate(rows, _cols):
        rows["flight_observations"][0]["division_id"] = "DIV_MISSING"

    findings = _findings(tmp_path, mutate)
    row = findings[(findings["check"] == "foreign_key_orphan") & (findings["table"] == "flight_observations")].iloc[0]
    assert row["record_id"] == "OBS_0001" and row["severity"] == "error"


def test_list_foreign_key_orphan(tmp_path):
    def mutate(rows, _cols):
        rows["scheduler_division_inputs"][0]["operation_unit_ids"] = "OPU_T1|OPU_GONE"

    findings = _findings(tmp_path, mutate)
    assert ("foreign_key_orphan", "scheduler_division_inputs", "DIV_T1") in _pairs(findings, "check", "table", "record_id")


def test_polymorphic_target_checked_against_correct_table(tmp_path):
    def mutate(rows, _cols):
        # A farm-level target that only exists as a division ID is an orphan.
        rows["farm_vehicle_evidence"][0]["target_id"] = "DIV_T1"

    findings = _findings(tmp_path, mutate)
    orphan = findings[(findings["check"] == "foreign_key_orphan") & (findings["table"] == "farm_vehicle_evidence")]
    assert orphan["record_id"].tolist() == ["FVE_T1"]


def test_duplicate_and_blank_primary_keys(tmp_path):
    def mutate(rows, _cols):
        rows["clients"].append({"client_id": "CLI_T1", "client_name": "Client 999"})
        rows["farms"].append({"farm_id": "", "client_id": "CLI_T1", "farm_name": "Farm 999"})

    findings = _findings(tmp_path, mutate)
    checks = _pairs(findings, "check", "table")
    assert ("primary_key_duplicate", "clients") in checks
    assert ("primary_key_blank", "farms") in checks


def test_hierarchy_mismatch_detected(tmp_path):
    def mutate(rows, _cols):
        rows["divisions"][0]["client_id"] = "CLI_T2"  # farm FRM_T1 belongs to CLI_T1

    findings = _findings(tmp_path, mutate)
    assert ("hierarchy_mismatch", "divisions") in _pairs(findings, "check", "table")


def test_unexpected_record_type_breaks_safeguard_assumption(tmp_path):
    def mutate(rows, _cols):
        rows["budget_fuel_trips"][0]["record_type"] = "actual"

    findings = _findings(tmp_path, mutate)
    assert ("unexpected_value", "budget_fuel_trips", "record_type") in _pairs(findings, "check", "table", "column")


def test_source_findings_are_separate_from_app_findings(tmp_path):
    ds = load_package(build_package(tmp_path))
    app_findings = validate_operational(ds)
    assert app_findings.empty
    # The package's own issue table and supplied report are loaded, but not mixed in.
    assert len(ds.tables["data_quality_issues"]) == 1
    assert ds.supplied_validation["checks_total"] == 2
    assert "OPERATION_DIVISION_LINK_PENDING" not in set(app_findings.get("check", []))
