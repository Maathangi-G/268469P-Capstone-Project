from __future__ import annotations

import pandas as pd
import pytest

from agriflight.operational import summaries as s
from agriflight.operational.loader import load_package
from operational_fixtures import build_package


@pytest.fixture
def ds(tmp_path):
    return load_package(build_package(tmp_path))


# --------------------------------------------------------------- budget
def test_shared_trip_counted_once_per_fuel_trip(ds):
    all_trips = s.fuel_trips_view(ds)
    assert all_trips["fuel_trip_id"].tolist() == ["FTR_T1", "FTR_T2"]
    linked = all_trips.set_index("fuel_trip_id")
    assert linked.loc["FTR_T1", "route_linked_farms"] == 3  # one route, three farms
    totals = s.fuel_trip_totals(all_trips)
    assert totals["reported_estimated_fuel_cost_lkr"] == 3500  # not 3000 x 3 + 500


def test_farm_filter_keeps_shared_trips_without_multiplying_cost(ds):
    farm2 = s.fuel_trips_view(ds, farm_id="FRM_T2")
    assert sorted(farm2["fuel_trip_id"]) == ["FTR_T1", "FTR_T2"]
    assert farm2["fuel_trip_id"].is_unique
    assert set(farm2["cost_basis"]) == {s.SHARED_TRIP_LABEL}
    assert s.fuel_trip_totals(farm2)["reported_estimated_fuel_cost_lkr"] == 3500
    farm1 = s.fuel_trips_view(ds, farm_id="FRM_T1")
    assert farm1["fuel_trip_id"].tolist() == ["FTR_T1"]
    # Full trip estimate shown once, never divided between the three linked farms.
    assert farm1["reported_estimated_fuel_cost_lkr"].iloc[0] == 3000


def test_unknown_amounts_stay_missing_in_totals(ds):
    totals = s.fuel_trip_totals(s.fuel_trips_view(ds))
    assert totals["estimated_distance_km"] == 100 and totals["distance_missing"] == 1
    assert totals["recomputed_fuel_cost_lkr"] == 3000 and totals["recomputed_missing"] == 1
    assert totals["rows_with_discrepancy_over_1_lkr"] == 0  # 1e-06 is rounding noise
    empty_total, missing = s.safe_sum(pd.Series([pd.NA, pd.NA], dtype="Float64"))
    assert empty_total is None and missing == 2  # unknown, not zero


def test_department_scope_not_silently_restricted(ds):
    assert set(s.fuel_trips_view(ds)["department_scope"]) == {"mixed_or_unspecified", "agronomy"}


def test_estimates_actuals_and_rollups_are_separate(ds):
    estimates, actuals = s.expense_lines_split(ds)
    assert estimates["expense_line_id"].tolist() == ["EXP_T1", "EXP_T3"]
    assert actuals["expense_line_id"].tolist() == ["EXP_T2"]
    summary = s.expense_category_summary(estimates).set_index("cost_category")
    assert set(summary["record_type"]) == {"estimate"}
    assert pd.isna(summary.loc["accommodation", "amount_lkr"])  # missing amount is not zero
    assert summary.loc["accommodation", "missing_amounts"] == 1
    # Rollups are not merged into the detail table totals.
    assert s.fuel_trip_totals(s.fuel_trips_view(ds))["reported_estimated_fuel_cost_lkr"] == 3500


def test_reconciliation_mismatch_preserved(ds):
    counts, flagged = s.reconciliation_status(ds)
    assert flagged["reconciliation_id"].tolist() == ["REC_T2"]
    assert flagged["reported_total_lkr"].iloc[0] == 450


def test_vehicle_rates_and_evidence_labelled(ds):
    summary = s.vehicle_rate_summary(s.vehicle_rates_view(ds))
    assert summary["vehicle_model"].tolist() == ["Test Pickup"]
    evidence = s.farm_vehicle_view(ds).set_index("vehicle_evidence_id")
    assert evidence.loc["FVE_T2", "target"] == "Division 901"
    assert evidence.loc["FVE_T1", "target"] == "Farm 901"
    assert not evidence["mandatory_vehicle_requirement_confirmed"].any()


# --------------------------------------------------------- observations
def test_observation_layers_stay_separate(ds):
    layers = s.layer_summary(ds).set_index("source_layer")
    assert layers["source_observations"].to_dict() == {"main_monthly": 3, "older_archive": 1, "annual_cycles": 1}
    assert layers.loc["main_monthly", "without_recorded_actual_date"] == 1


def test_monthly_counts_default_layer_and_undated(ds):
    monthly, undated = s.observations_by_month(ds, "main_monthly", "recorded_actual_date")
    assert monthly.to_dict("list") == {"month": ["2026-01", "2026-02", "2026-03"], "source_observations": [1, 0, 1]}
    assert undated == 1
    archive, _ = s.observations_by_month(ds, "older_archive", "recorded_actual_date")
    assert archive["source_observations"].sum() == 1  # overlap with main layer not merged


def test_observation_records_hide_person_tokens(ds):
    records = s.observation_records(ds, "main_monthly")
    assert "person_ids" not in records.columns
    assert records["division"].iloc[0] == "Division 901"


# ------------------------------------------------------------ divisions
def test_division_table_uses_foreign_keys_and_anonymous_labels(ds):
    table = s.division_table(ds).set_index("division_id")
    assert table.loc["DIV_ZZ9", "farm"] == "Farm 903"
    assert table.loc["DIV_ZZ9", "client"] == "Client 902"  # via client_id, not ID splitting
    assert table.loc["DIV_T1", "source_obs_main_monthly"] == 3
    assert table.loc["DIV_T1", "source_obs_older_archive"] == 1
    assert table.loc["DIV_T1", "vehicle_evidence_division_level"] == 1
    assert table.loc["DIV_T2", "vehicle_evidence_farm_level"] == 1
    assert table.loc["DIV_T2", "vehicle_evidence_division_level"] == 0
    assert pd.isna(table.loc["DIV_T2", "tracker_imaging_area_ha"])
    assert table.loc["DIV_T1", "vehicle_models_in_evidence"] == "Test Pickup, Test SUV"


def test_division_filters(ds):
    assert s.division_table(ds, client_ids=["CLI_T2"])["division_id"].tolist() == ["DIV_ZZ9"]
    assert sorted(s.division_table(ds, farm_ids=["FRM_T1"])["division_id"]) == ["DIV_T1", "DIV_T2"]


def test_readiness_is_never_marked_resolved(ds):
    req = s.readiness_requirements(ds)
    assert not req["status"].str.fullmatch("resolved").any()
    assert (req.loc[req["requirement"] == "Measured daily hectares", "count"] == 0).all()
    assert s.scheduler_ready_count(ds) == (0, 3)
    blockers = s.blocker_counts(ds).set_index("readiness_blocker")["divisions"]
    assert blockers["completion_rule_unknown"] == 3
