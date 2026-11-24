from __future__ import annotations

import pytest

from agriflight.data.loader import load_operations_csv
from agriflight.data.validation import validate_operations
from conftest import make_csv

VALID_PLAN = "OBS_1,UNIT_1,CLIENT_A,planned_visit,2026-01-01,,planned,10,synthetic_demo"


def _validate(*rows: str, header: str | None = None):
    data = make_csv(*rows) if header is None else make_csv(*rows, header=header)
    return validate_operations(load_operations_csv(data))


def _codes(report) -> list[str]:
    return report.issues["issue_code"].tolist()


def test_clean_file_passes():
    report = _validate(
        VALID_PLAN,
        "OBS_2,UNIT_1,CLIENT_A,capture_observation,2026-01-01,2026-01-03,recorded,10,synthetic_demo",
        "OBS_3,UNIT_2,,trial_visit,,2026-01-05,trial,,synthetic_demo",
    )
    assert report.passed
    assert report.issues.empty


def test_planned_visit_without_actual_date_is_not_an_issue():
    report = _validate(VALID_PLAN)
    assert report.passed
    assert "actual_date" not in report.issues["field"].tolist()


def test_optional_blank_area_and_client_are_not_issues():
    report = _validate("OBS_1,UNIT_1,,planned_visit,2026-01-01,,,,synthetic_demo")
    assert report.passed


def test_missing_required_columns_reported():
    report = _validate("OBS_1,planned_visit", header="observation_id,record_type")
    assert not report.passed
    assert "operating_unit_id" in report.missing_columns
    missing = report.issues[report.issues["issue_code"] == "MISSING_REQUIRED_COLUMN"]
    assert "operating_unit_id" in missing["field"].tolist()
    assert missing["source_row"].isna().all()


def test_unexpected_extra_column_is_info_only():
    report = _validate(
        VALID_PLAN + ",x",
        header="observation_id,operating_unit_id,client_id,record_type,planned_date,"
        "actual_date,recorded_status,area_ha,data_origin,extra",
    )
    assert report.passed
    assert _codes(report) == ["UNEXPECTED_COLUMN"]


def test_header_only_file_is_flagged_not_reported_as_success():
    report = _validate()
    assert report.row_count == 0
    assert "NO_DATA_ROWS" in _codes(report)


def test_missing_required_identifier():
    report = _validate("OBS_1,,CLIENT_A,planned_visit,2026-01-01,,planned,10,synthetic_demo")
    issue = report.issues.iloc[0]
    assert issue["issue_code"] == "MISSING_REQUIRED_VALUE"
    assert issue["field"] == "operating_unit_id"
    assert issue["source_row"] == 2
    assert issue["severity"] == "error"


def test_duplicate_observation_ids_report_every_occurrence():
    report = _validate(
        VALID_PLAN,
        "OBS_1,UNIT_1,CLIENT_A,capture_observation,2026-01-01,2026-01-01,recorded,10,synthetic_demo",
    )
    dupes = report.issues[report.issues["issue_code"] == "DUPLICATE_OBSERVATION_ID"]
    assert dupes["source_row"].tolist() == [2, 3]
    assert report.row_count == 2  # nothing dropped


def test_invalid_date_strings_detected_with_raw_value():
    report = _validate(
        "OBS_1,UNIT_1,C,planned_visit,2026-02-30,,planned,10,synthetic_demo",
        "OBS_2,UNIT_1,C,capture_observation,2026-01-01,next week,recorded,10,synthetic_demo",
        "OBS_3,UNIT_1,C,planned_visit,01/02/2026,,planned,10,synthetic_demo",
    )
    invalid = report.issues[report.issues["issue_code"] == "INVALID_DATE"]
    assert invalid["raw_value"].tolist() == ["2026-02-30", "next week", "01/02/2026"]
    # An invalid (non-blank) capture date is not double-reported as missing.
    assert "MISSING_CONDITIONAL_DATE" not in _codes(report)


def test_conditionally_required_dates():
    report = _validate(
        "OBS_1,UNIT_1,C,planned_visit,,,planned,10,synthetic_demo",
        "OBS_2,UNIT_1,C,capture_observation,2026-01-01,,recorded,10,synthetic_demo",
        "OBS_3,UNIT_1,C,trial_visit,,,trial,10,synthetic_demo",
    )
    missing = report.issues[report.issues["issue_code"] == "MISSING_CONDITIONAL_DATE"]
    assert list(zip(missing["source_row"], missing["field"])) == [
        (2, "planned_date"),
        (3, "actual_date"),
    ]


@pytest.mark.parametrize("raw", ["abc", "approx 8", "1,5", "inf", "nan"])
def test_invalid_area_values(raw):
    quoted = f'"{raw}"'
    report = _validate(f"OBS_1,UNIT_1,C,planned_visit,2026-01-01,,planned,{quoted},synthetic_demo")
    assert _codes(report) == ["INVALID_NUMBER"]
    assert report.issues.iloc[0]["raw_value"] == raw


def test_negative_area():
    report = _validate("OBS_1,UNIT_1,C,planned_visit,2026-01-01,,planned,-0.5,synthetic_demo")
    assert _codes(report) == ["NEGATIVE_AREA"]


def test_zero_area_is_allowed():
    assert _validate("OBS_1,UNIT_1,C,planned_visit,2026-01-01,,planned,0,synthetic_demo").passed


def test_unexpected_record_type():
    report = _validate("OBS_1,UNIT_1,C,completed_service,2026-01-01,2026-01-02,done,1,synthetic_demo")
    assert _codes(report) == ["UNEXPECTED_RECORD_TYPE"]
    assert report.issues.iloc[0]["raw_value"] == "completed_service"


def test_non_synthetic_origin_is_a_warning():
    report = _validate("OBS_1,UNIT_1,C,planned_visit,2026-01-01,,planned,1,company_export")
    assert report.passed  # warning, not error
    assert report.warning_count == 1
    assert _codes(report) == ["NON_SYNTHETIC_ORIGIN"]


def test_validation_does_not_modify_input():
    frame = load_operations_csv(make_csv("OBS_1,UNIT_1,C,planned_visit,2026-02-30,,planned,-1,synthetic_demo"))
    before = frame.copy()
    validate_operations(frame)
    assert frame.equals(before)


def test_bundled_demo_reports_exactly_the_documented_issues(demo_csv_path):
    report = validate_operations(load_operations_csv(demo_csv_path))
    found = sorted(zip(report.issues["source_row"].tolist(), report.issues["issue_code"]))
    assert found == [
        (17, "INVALID_DATE"),
        (19, "NEGATIVE_AREA"),
        (21, "DUPLICATE_OBSERVATION_ID"),
        (22, "DUPLICATE_OBSERVATION_ID"),
        (23, "MISSING_REQUIRED_VALUE"),
        (25, "INVALID_NUMBER"),
        (26, "UNEXPECTED_RECORD_TYPE"),
    ]
    assert set(report.issues["severity"]) == {"error"}
    assert not report.passed
    assert report.rows_with_errors == 7
