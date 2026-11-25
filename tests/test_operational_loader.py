from __future__ import annotations

import json

import pandas as pd
import pytest

from agriflight.operational.contract import ENV_VAR, TABLES
from agriflight.operational.loader import (
    PackageError,
    load_package,
    parse_boolean,
    parse_number,
    resolve_package_dir,
)
from agriflight.operational.validation import snapshot_table, validate_operational
from operational_fixtures import build_package, file_hashes


@pytest.fixture
def pkg(tmp_path):
    return build_package(tmp_path)


# ---------------------------------------------------------- configuration
def test_unset_variable_gives_clear_error():
    with pytest.raises(PackageError, match=ENV_VAR):
        resolve_package_dir({})


def test_missing_path_gives_clear_error(tmp_path):
    with pytest.raises(PackageError, match="does not exist"):
        resolve_package_dir({ENV_VAR: str(tmp_path / "nowhere")})


def test_file_instead_of_folder(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("x")
    with pytest.raises(PackageError, match="not a folder"):
        resolve_package_dir({ENV_VAR: str(path)})


def test_invalid_package_lists_missing_entries(tmp_path):
    (tmp_path / "empty_pkg").mkdir()
    with pytest.raises(PackageError, match="FILE_MANIFEST.json"):
        resolve_package_dir({ENV_VAR: str(tmp_path / "empty_pkg")})


def test_pointing_at_data_subfolder_explains_root_requirement(pkg):
    with pytest.raises(PackageError, match="package root"):
        resolve_package_dir({ENV_VAR: str(pkg / "data")})


def test_valid_variable_resolves(pkg):
    assert resolve_package_dir({ENV_VAR: f'"{pkg}"'}) == pkg.resolve()


def test_missing_schema_is_invalid_package(tmp_path):
    pkg = build_package(tmp_path, drop_files=("docs/schema.json",))
    with pytest.raises(PackageError, match="schema.json"):
        load_package(pkg)


# ---------------------------------------------------------------- loading
def test_clean_fixture_loads_all_tables_without_app_errors(pkg):
    ds = load_package(pkg)
    assert set(ds.tables) == set(TABLES)
    findings = validate_operational(ds)
    assert findings.empty, findings.to_string()


def test_loading_does_not_modify_package(pkg):
    before = file_hashes(pkg)
    validate_operational(load_package(pkg))
    assert file_hashes(pkg) == before


def test_identifiers_and_source_text_preserved(pkg):
    ds = load_package(pkg)
    obs = ds.tables["flight_observations"].set_index("observation_id")
    assert obs.loc["OBS_0001", "source_row"] == "0012"  # leading zero kept, not a number
    assert ds.raw["flight_observations"]["observation_id"].tolist()[0] == "OBS_0001"
    assert ds.raw["budget_fuel_trips"].set_index("fuel_trip_id").loc["FTR_T1", "reported_minus_recomputed_lkr"] == "1e-06"


def test_blanks_stay_missing_not_zero(pkg):
    ds = load_package(pkg)
    sched = ds.tables["scheduler_division_inputs"].set_index("division_id")
    assert pd.isna(sched.loc["DIV_T2", "tracker_imaging_area_ha"])
    assert ds.raw["scheduler_division_inputs"].set_index("division_id").loc["DIV_T2", "tracker_imaging_area_ha"] == ""
    trips = ds.tables["budget_fuel_trips"].set_index("fuel_trip_id")
    assert pd.isna(trips.loc["FTR_T2", "estimated_distance_km"])
    assert pd.isna(sched.loc["DIV_T1", "next_due_date"])


def test_false_text_parses_as_false():
    parsed, invalid = parse_boolean(pd.Series(["True", "False", "", "false", "yes", "0"]))
    assert parsed.tolist()[:2] == [True, False]
    assert parsed[2:].isna().all()
    assert invalid.tolist() == [False, False, False, True, True, True]


def test_scheduler_ready_false_is_never_true(pkg):
    ds = load_package(pkg)
    ready = ds.tables["scheduler_division_inputs"]["scheduler_ready"]
    assert str(ready.dtype) == "boolean"
    assert ready.eq(False).all()


def test_scientific_notation_and_unknown_numbers():
    parsed, invalid = parse_number(pd.Series(["1e-06", "", "12.5", "n/a"]))
    assert parsed[0] == pytest.approx(1e-06)
    assert pd.isna(parsed[1]) and pd.isna(parsed[3])
    assert invalid.tolist() == [False, False, False, True]


def test_invalid_date_and_boolean_become_findings_with_record_id(tmp_path):
    def mutate(rows, _cols):
        rows["flight_observations"][0]["recorded_actual_date"] = "10/01/2026"
        rows["scheduler_division_inputs"][0]["scheduler_ready"] = "false"

    ds = load_package(build_package(tmp_path, mutate))
    findings = validate_operational(ds)
    got = set(zip(findings["check"], findings["record_id"]))
    assert ("invalid_date", "OBS_0001") in got
    assert ("invalid_boolean", "DIV_T1") in got
    assert ds.raw["flight_observations"]["recorded_actual_date"][0] == "10/01/2026"


def test_header_only_templates_are_unfilled_contracts(pkg):
    ds = load_package(pkg)
    assert set(ds.templates["status"]) == {"unfilled input contract (header only)"}
    assert validate_operational(ds).empty


def test_header_only_main_table_is_an_error_not_a_template(tmp_path):
    def mutate(rows, _cols):
        rows["budget_fuel_trips"] = []

    findings = validate_operational(load_package(build_package(tmp_path, mutate)))
    assert ("table_empty", "budget_fuel_trips") in set(zip(findings["check"], findings["table"]))


def test_missing_main_table_file_is_reported(tmp_path):
    pkg = build_package(tmp_path, drop_files=("data/budget_fuel_trips.csv",))
    ds = load_package(pkg)
    assert not ds.has("budget_fuel_trips")
    findings = validate_operational(ds)
    row = findings[findings["check"] == "table_file_missing"].iloc[0]
    assert row["table"] == "budget_fuel_trips" and row["severity"] == "error"


def test_snapshot_counts_are_reference_only(tmp_path, pkg):
    schema_path = pkg / "docs" / "schema.json"
    schema = json.loads(schema_path.read_text())
    schema["tables"]["clients"]["rows"] = 99
    schema_path.write_text(json.dumps(schema))
    ds = load_package(pkg)
    snap = snapshot_table(ds).set_index("table")
    assert snap.loc["clients", "rows_loaded"] == 2  # counted from the file, not the schema
    assert not snap.loc["clients", "matches_snapshot"]
    findings = validate_operational(ds)
    assert set(findings["check"]) >= {"snapshot_row_count_differs", "manifest_mismatch"}
    assert set(findings["severity"]) == {"warning"}
