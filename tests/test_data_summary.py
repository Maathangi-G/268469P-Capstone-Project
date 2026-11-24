from __future__ import annotations

import datetime as dt

from agriflight.data.loader import load_operations_csv
from agriflight.services.data_summary import (
    date_ranges_by_record_type,
    missing_value_summary,
    record_type_counts,
    summarize_dataset,
)
from conftest import make_csv

ROWS = (
    "OBS_1,UNIT_1,CLIENT_A,planned_visit,2026-01-01,,planned,10,synthetic_demo",
    "OBS_2,UNIT_1,CLIENT_A,capture_observation,2026-01-01,2026-01-03,recorded,10,synthetic_demo",
    "OBS_3,UNIT_2,CLIENT_A,planned_visit,2026-02-01,,planned,20,synthetic_demo",
    "OBS_4,UNIT_3,,trial_visit,,2026-03-05,trial,,synthetic_demo",
    "OBS_5,,CLIENT_B,capture_observation,2026-02-01,not-a-date,recorded,5,synthetic_demo",
    "OBS_6,UNIT_2,CLIENT_B,completed_service,2026-02-01,2026-02-02,done,5,synthetic_demo",
)


def _frame():
    return load_operations_csv(make_csv(*ROWS))


def _counts(frame) -> dict[str, int]:
    table = record_type_counts(frame)
    return dict(zip(table["record_type"], table["source_records"]))


def test_record_types_counted_separately_not_merged():
    counts = _counts(_frame())
    assert counts == {
        "planned_visit": 2,
        "capture_observation": 2,
        "trial_visit": 1,
        "completed_service": 1,  # undocumented value kept visible, not folded in
    }
    # Plans and observations are never summed into a "completed" figure.
    assert "completed" not in " ".join(record_type_counts(_frame()).columns)


def test_documented_types_listed_even_when_absent():
    frame = load_operations_csv(make_csv(ROWS[0]))
    assert _counts(frame) == {"planned_visit": 1, "capture_observation": 0, "trial_visit": 0}


def test_summary_headline_counts():
    summary = summarize_dataset(_frame())
    assert summary.source_record_count == 6
    assert summary.distinct_operating_units == 3  # blank unit not counted as a unit
    assert summary.distinct_clients == 2


def test_date_ranges_exclude_invalid_and_blank_and_stay_per_type():
    ranges = date_ranges_by_record_type(_frame()).set_index(["record_type", "date_field"])
    capture_actual = ranges.loc[("capture_observation", "actual_date")]
    assert capture_actual["valid_dates"] == 1  # "not-a-date" excluded
    assert capture_actual["earliest"] == dt.date(2026, 1, 3)
    planned_actual = ranges.loc[("planned_visit", "actual_date")]
    assert planned_actual["valid_dates"] == 0
    assert planned_actual["earliest"] is None
    plan_dates = ranges.loc[("planned_visit", "planned_date")]
    assert (plan_dates["earliest"], plan_dates["latest"]) == (dt.date(2026, 1, 1), dt.date(2026, 2, 1))


def test_missing_value_summary():
    table = missing_value_summary(_frame()).set_index("field")
    assert table.loc["actual_date", "blank_cells"] == 2
    assert table.loc["operating_unit_id", "blank_cells"] == 1
    assert table.loc["area_ha", "blank_percent"] == round(100 / 6, 1)
    assert "required for planned_visit" in table.loc["planned_date", "blank_policy"]
    assert "source_row" not in table.index


def test_bundled_demo_summary(demo_csv_path):
    summary = summarize_dataset(load_operations_csv(demo_csv_path))
    assert summary.source_record_count == 27
    assert summary.distinct_operating_units == 6
    assert summary.distinct_clients == 3
    counts = dict(zip(summary.record_type_counts["record_type"], summary.record_type_counts["source_records"]))
    assert counts == {
        "planned_visit": 12,
        "capture_observation": 10,
        "trial_visit": 4,
        "completed_service": 1,
    }
