from __future__ import annotations

import pytest

from agriflight.operational import eda
from agriflight.operational.loader import load_package
from operational_fixtures import build_package


def _obs(obs_id, layer, unit, date, division=""):
    return {"observation_id": obs_id, "source_layer": layer, "operation_unit_id": unit, "division_id": division,
            "identity_link_method": "via_tracker_unit" if unit else "unresolved", "recorded_actual_date": date,
            "daily_coverage_label_status": "not_recorded_in_supplied_row", "completion_scope": "unconfirmed",
            "observation_status": "actual_date_recorded" if date else "planned_or_undated",
            "source_review_flags_present": "False", "source_id": "SRC_T1", "sheet_id": "SHT_T1", "source_row": "99"}


@pytest.fixture
def ds(tmp_path):
    def mutate(rows, _cols):
        rows["flight_observations"] += [
            _obs("OBS_0006", "main_monthly", "OPU_T1", "2026-03-05", "DIV_T1"),  # same date as OBS_0002
            _obs("OBS_0007", "main_monthly", "OPU_T2", "2026-02-01"),            # single-observation unit
        ]
    return load_package(build_package(tmp_path, mutate))


# ------------------------------------------------------ A. completeness
def test_undated_and_unmapped_counted_per_layer(ds):
    table = eda.undated_unmapped(ds).set_index("source_layer")
    assert table.loc["main_monthly", "source_rows"] == 5
    assert table.loc["main_monthly", "undated_recorded_actual_date"] == 1
    assert table.loc["annual_cycles", "no_unit_and_no_division"] == 1
    assert table.loc["older_archive", "source_rows"] == 1  # layers never merged


def test_unknown_ids_reported_not_dropped(tmp_path):
    def mutate(rows, _cols):
        rows["flight_observations"].append(_obs("OBS_0008", "main_monthly", "OPU_UNKNOWN", "2026-01-15"))
    ds = load_package(build_package(tmp_path, mutate))
    table = eda.completeness(ds, ["main_monthly"]).set_index("field")
    assert table.loc["operation_unit_id", "unknown_reference"] == 1
    assert table.loc["actual_daily_covered_ha", "missing"] == table.loc["actual_daily_covered_ha", "source_rows"]


def test_unit_history_counts_distinct_dates_and_repeats(ds):
    history = eda.unit_history(ds, "main_monthly").set_index("operation_unit_id")
    t1 = history.loc["OPU_T1"]
    assert (t1["source_rows"], t1["dated_observations"], t1["distinct_recorded_dates"]) == (4, 3, 2)
    assert t1["same_date_repeat_rows"] == 1
    assert t1["months_with_records"] == 2
    assert history.loc["OPU_T2", "distinct_recorded_dates"] == 1
    assert history.loc["OPU_T1", "operation_unit"] == "Operation 901"


# ---------------------------------------------------------------- B. gaps
def test_gaps_use_distinct_dates_and_keep_traceability(ds):
    gaps = eda.recorded_date_gaps(ds, "main_monthly")
    t1 = gaps[gaps["operation_unit_id"] == "OPU_T1"]
    assert t1["gap_days"].tolist() == [54]
    row = t1.iloc[0]
    assert row["from_observation_ids"] == "OBS_0001"
    assert row["to_observation_ids"] == "OBS_0002|OBS_0006"  # repetition kept visible, counted once
    assert row["rows_on_to_date"] == 2
    # Source rows are untouched by the gap calculation.
    assert len(ds.tables["flight_observations"]) == 7


def test_single_observation_unit_has_no_gap(ds):
    gaps = eda.recorded_date_gaps(ds, "main_monthly")
    assert "OPU_T2" not in set(gaps["operation_unit_id"])


def test_gaps_are_computed_within_one_layer_only(ds):
    # OBS_0004 (older_archive) shares OPU_T1 but must not create a gap with main_monthly dates.
    assert eda.recorded_date_gaps(ds, "older_archive").empty
    table, summary = eda.gap_distribution(eda.recorded_date_gaps(ds, "main_monthly"))
    assert summary["gaps"] == 1 and summary["median_days"] == 54
    assert int(table["gaps"].sum()) == 1
    assert eda.gap_distribution(eda.recorded_date_gaps(ds, "older_archive"))[1] == {"gaps": 0}


# ---------------------------------------------------------------- C. area
def test_area_grains_and_types_kept_separate_without_sums(ds):
    dist = eda.area_distribution(ds)
    assert not any("sum" in c or "total_ha" == c for c in dist.columns)
    field = dist[(dist["record_grain"] == "field") & (dist["area_type"] == "boundary_area_ha")].iloc[0]
    assert field["records_with_value"] == 2 and field["median_ha"] == pytest.approx(12.75)
    parent = dist[(dist["record_grain"] == "division_or_farm") & (dist["area_type"] == "boundary_area_ha")].iloc[0]
    assert parent["records_with_value"] == 1 and parent["max_ha"] == 25.5  # not 10 + 15.5 + 25.5
    tracker = dist[dist["area_type"] == "tracker_imaging_area_ha"].iloc[0]
    assert tracker["source"].startswith("operation_units")
    avail = eda.area_availability(ds).set_index("record_grain")
    assert avail.loc["field", "with_farm_total_area_ha"] == 0
    assert avail.loc["farm", "identity_unresolved"] == 1
    assert avail["with_effective_date"].sum() == 0


def test_area_by_crop_maturity_labels_missing(ds):
    table = eda.area_by_crop_maturity(ds)
    assert "(not recorded)" in set(table["crop"])


# ------------------------------------------------------------- D. overlap
def test_overlaps_are_candidates_not_confirmed(ds):
    table, summary = eda.overlap_summary(ds)
    assert summary["groups_marked_confirmed_duplicate"] == 0
    assert set(table["status"]) == {"candidate overlap - not a confirmed duplicate"}
    assert summary["distinct_observations_referenced"] == 2


def test_explicit_confirmation_is_the_only_confirmed_status(tmp_path):
    def mutate(rows, _cols):
        rows["observation_overlap_review"][0]["resolution"] = "confirmed_duplicate"
    _, summary = eda.overlap_summary(load_package(build_package(tmp_path, mutate)))
    assert summary["groups_marked_confirmed_duplicate"] == 1
