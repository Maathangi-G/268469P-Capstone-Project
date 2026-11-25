"""Fictional relational fixture package for operational-dataset tests.

Every ID, label, date and amount here is invented for testing. Nothing is
copied or derived from company records. The layout mirrors the package
structure (README.md, FILE_MANIFEST.json, data/, docs/) so the loader can be
exercised end to end.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from agriflight.operational.contract import KNOWN_TEMPLATES, TABLES

F, T = "False", "True"

BASE_ROWS: dict[str, list[dict[str, str]]] = {
    "clients": [
        {"client_id": "CLI_T1", "client_name": "Client 901"},
        {"client_id": "CLI_T2", "client_name": "Client 902"},
    ],
    "farms": [
        {"farm_id": "FRM_T1", "client_id": "CLI_T1", "farm_name": "Farm 901", "physical_site_equivalence": "not_assumed"},
        {"farm_id": "FRM_T2", "client_id": "CLI_T1", "farm_name": "Farm 902", "physical_site_equivalence": "not_assumed"},
        {"farm_id": "FRM_T3", "client_id": "CLI_T2", "farm_name": "Farm 903", "physical_site_equivalence": "not_assumed"},
    ],
    "divisions": [
        {"division_id": "DIV_T1", "farm_id": "FRM_T1", "client_id": "CLI_T1", "division_name": "Division 901", "farm_name": "Farm 901"},
        {"division_id": "DIV_T2", "farm_id": "FRM_T1", "client_id": "CLI_T1", "division_name": "Division 902", "farm_name": "Farm 901"},
        # Opaque ID that does not contain its parent's ID: joins must use farm_id, not string splitting.
        {"division_id": "DIV_ZZ9", "farm_id": "FRM_T3", "client_id": "CLI_T2", "division_name": "Division 903", "farm_name": "Farm 903"},
    ],
    "operation_units": [
        {"operation_unit_id": "OPU_T1", "operation_name": "Operation 901", "division_id": "DIV_T1", "farm_id": "FRM_T1",
         "identity_link_method": "exact_normalized_source_text", "identity_user_confirmed": F, "imaging_area_ha": "12.5"},
        {"operation_unit_id": "OPU_T2", "operation_name": "Operation 902", "division_id": "", "farm_id": "",
         "identity_link_method": "unresolved", "identity_user_confirmed": F, "imaging_area_ha": ""},
    ],
    "vehicle_models": [
        {"vehicle_model_id": "VMD_T1", "vehicle_model": "Test Pickup", "vehicle_type": "pickup", "drive_configuration": "unknown"},
        {"vehicle_model_id": "VMD_T2", "vehicle_model": "Test SUV", "vehicle_type": "SUV", "drive_configuration": "unknown"},
    ],
    "scheduler_division_inputs": [
        {"division_id": "DIV_T1", "division_name": "Division 901", "farm_id": "FRM_T1", "farm_name": "Farm 901", "client_id": "CLI_T1",
         "operation_unit_ids": "OPU_T1", "identity_link_count": "1", "tracker_imaging_area_ha": "12.5",
         "area_approval_status": "source_snapshot_not_contract_approval",
         "first_recorded_capture_date": "2026-01-10", "last_recorded_capture_date": "2026-03-05",
         "target_interval_days": "30", "operational_tolerance_days": "5", "proposal_tolerance_days": "3",
         "field_point_count": "2", "coordinate_access": "separate_restricted_join",
         "vehicle_model_evidence_ids": "VMD_T1|VMD_T2", "vehicle_requirement_approved": F, "scheduler_ready": F,
         "readiness_blockers": "completion_rule_unknown|base_location_missing"},
        {"division_id": "DIV_T2", "division_name": "Division 902", "farm_id": "FRM_T1", "farm_name": "Farm 901", "client_id": "CLI_T1",
         "operation_unit_ids": "", "identity_link_count": "0", "tracker_imaging_area_ha": "",
         "area_approval_status": "source_snapshot_not_contract_approval",
         "target_interval_days": "30", "operational_tolerance_days": "5", "proposal_tolerance_days": "3",
         "field_point_count": "0", "coordinate_access": "separate_restricted_join",
         "vehicle_requirement_approved": F, "scheduler_ready": F,
         "readiness_blockers": "completion_rule_unknown|base_location_missing|tracker_identity_mapping_missing"},
        {"division_id": "DIV_ZZ9", "division_name": "Division 903", "farm_id": "FRM_T3", "farm_name": "Farm 903", "client_id": "CLI_T2",
         "operation_unit_ids": "", "identity_link_count": "0", "tracker_imaging_area_ha": "40",
         "area_approval_status": "source_snapshot_not_contract_approval",
         "target_interval_days": "30", "operational_tolerance_days": "5", "proposal_tolerance_days": "3",
         "field_point_count": "1", "coordinate_access": "separate_restricted_join",
         "vehicle_requirement_approved": F, "scheduler_ready": F, "readiness_blockers": "completion_rule_unknown"},
    ],
    "flight_observations": [
        {"observation_id": "OBS_0001", "source_layer": "main_monthly", "operation_unit_id": "OPU_T1", "division_id": "DIV_T1",
         "identity_link_method": "via_tracker_unit", "planned_date": "2026-01-08", "recorded_actual_date": "2026-01-10",
         "daily_coverage_label_status": "not_recorded_in_supplied_row", "completion_scope": "unconfirmed",
         "observation_status": "actual_date_recorded", "source_review_flags_present": F,
         "source_id": "SRC_T1", "sheet_id": "SHT_T1", "source_row": "0012"},
        {"observation_id": "OBS_0002", "source_layer": "main_monthly", "operation_unit_id": "OPU_T1", "division_id": "DIV_T1",
         "identity_link_method": "via_tracker_unit", "planned_date": "", "recorded_actual_date": "2026-03-05",
         "daily_coverage_label_status": "not_recorded_in_supplied_row", "completion_scope": "unconfirmed",
         "observation_status": "actual_date_recorded", "source_review_flags_present": T,
         "source_id": "SRC_T1", "sheet_id": "SHT_T1", "source_row": "13"},
        {"observation_id": "OBS_0003", "source_layer": "main_monthly", "operation_unit_id": "OPU_T1", "division_id": "DIV_T1",
         "identity_link_method": "via_tracker_unit", "planned_date": "2026-04-01", "recorded_actual_date": "",
         "daily_coverage_label_status": "not_recorded_in_supplied_row", "completion_scope": "unconfirmed",
         "observation_status": "planned_or_undated", "source_review_flags_present": F,
         "source_id": "SRC_T1", "sheet_id": "SHT_T1", "source_row": "14"},
        # Same unit/date as OBS_0001 in another layer: an overlap, not a second visit.
        {"observation_id": "OBS_0004", "source_layer": "older_archive", "operation_unit_id": "OPU_T1", "division_id": "DIV_T1",
         "identity_link_method": "via_tracker_unit", "planned_date": "", "recorded_actual_date": "2026-01-10",
         "daily_coverage_label_status": "not_recorded_in_supplied_row", "completion_scope": "unconfirmed",
         "observation_status": "actual_date_recorded", "source_review_flags_present": F,
         "source_id": "SRC_T1", "sheet_id": "SHT_T2", "source_row": "5"},
        {"observation_id": "OBS_0005", "source_layer": "annual_cycles", "operation_unit_id": "", "division_id": "",
         "identity_link_method": "unresolved", "planned_date": "", "recorded_actual_date": "2026-01-10",
         "daily_coverage_label_status": "not_recorded_in_supplied_row", "completion_scope": "unconfirmed",
         "observation_status": "actual_date_recorded", "source_review_flags_present": F,
         "source_id": "SRC_T1", "sheet_id": "SHT_T3", "source_row": "7"},
    ],
    "budget_documents": [
        {"budget_document_id": "BDG_T1", "archive_year": "2026", "document_type": "weekly_budget",
         "period_start": "2026-01-05", "period_end": "2026-01-11", "period_interpretation": "filename_inferred_not_event_confirmation",
         "currency": "LKR", "actual_expense_section_present": F, "historical_rate_validity": "source_period_only_not_current_quote"},
        {"budget_document_id": "BDG_T2", "archive_year": "2026", "document_type": "weekly_budget",
         "period_start": "2026-01-12", "period_end": "2026-01-18", "period_interpretation": "filename_inferred_not_event_confirmation",
         "currency": "LKR", "actual_expense_section_present": T, "historical_rate_validity": "source_period_only_not_current_quote"},
    ],
    "route_index": [
        {"route_id": "RTE_T1", "route_name": "Itinerary 901", "purpose_category": "drone_imaging_plan",
         "entity_link_count": "3", "travel_distance_kind": "source_estimate_whole_itinerary", "road_routing_verified": F},
        {"route_id": "RTE_T2", "route_name": "Itinerary 902", "purpose_category": "other_or_shared_business_travel",
         "entity_link_count": "1", "travel_distance_kind": "source_estimate_whole_itinerary", "road_routing_verified": F},
    ],
    "route_entity_links": [
        {"route_entity_link_id": "REL_T1", "route_id": "RTE_T1", "target_level": "farm", "target_id": "FRM_T1", "farm_id": "FRM_T1",
         "link_method": "exact_source_name_token_candidate", "approval_status": "not_user_confirmed", "cost_allocation_allowed": F},
        {"route_entity_link_id": "REL_T2", "route_id": "RTE_T1", "target_level": "division", "target_id": "DIV_ZZ9", "farm_id": "FRM_T3",
         "candidate_division_ids": "DIV_ZZ9", "link_method": "exact_source_name_token_candidate",
         "approval_status": "not_user_confirmed", "cost_allocation_allowed": F},
        {"route_entity_link_id": "REL_T3", "route_id": "RTE_T1", "target_level": "farm", "target_id": "FRM_T2", "farm_id": "FRM_T2",
         "link_method": "exact_source_name_token_candidate", "approval_status": "not_user_confirmed", "cost_allocation_allowed": F},
        {"route_entity_link_id": "REL_T4", "route_id": "RTE_T2", "target_level": "farm", "target_id": "FRM_T2", "farm_id": "FRM_T2",
         "link_method": "exact_source_name_token_candidate", "approval_status": "not_user_confirmed", "cost_allocation_allowed": F},
    ],
    "budget_fuel_trips": [
        {"fuel_trip_id": "FTR_T1", "budget_document_id": "BDG_T1", "route_id": "RTE_T1", "planned_date": "2026-01-06",
         "period_start": "2026-01-05", "period_end": "2026-01-11", "date_check": "inside_filename_period",
         "department_scope": "mixed_or_unspecified", "purpose_category": "drone_imaging_plan", "vehicle_model_id": "VMD_T1",
         "estimated_distance_km": "100", "assumed_efficiency_km_per_l": "10", "fuel_price_lkr_per_l": "300",
         "reported_estimated_fuel_l": "10", "reported_estimated_fuel_cost_lkr": "3000", "recomputed_fuel_l": "10",
         "recomputed_fuel_cost_lkr": "3000", "reported_minus_recomputed_lkr": "1e-06", "record_type": "estimate",
         "distance_scope": "whole_trip_row", "cost_allocation": "unallocated_shared_trip_cost", "actual_flight_evidence": F,
         "source_id": "SRC_T2", "sheet_id": "SHT_T4", "source_row": "8"},
        {"fuel_trip_id": "FTR_T2", "budget_document_id": "BDG_T2", "route_id": "RTE_T2", "planned_date": "2026-01-20",
         "period_start": "2026-01-12", "period_end": "2026-01-18", "date_check": "outside_filename_period",
         "department_scope": "agronomy", "purpose_category": "other_or_shared_business_travel", "vehicle_model_id": "VMD_T2",
         "estimated_distance_km": "", "assumed_efficiency_km_per_l": "8", "fuel_price_lkr_per_l": "300",
         "reported_estimated_fuel_l": "", "reported_estimated_fuel_cost_lkr": "500", "recomputed_fuel_l": "",
         "recomputed_fuel_cost_lkr": "", "reported_minus_recomputed_lkr": "", "record_type": "estimate",
         "distance_scope": "whole_trip_row", "cost_allocation": "unallocated_shared_trip_cost", "actual_flight_evidence": F,
         "source_id": "SRC_T3", "sheet_id": "SHT_T5", "source_row": "9"},
    ],
    "accommodation_estimates": [
        {"accommodation_line_id": "ACC_T1", "budget_document_id": "BDG_T1", "period_start": "2026-01-05", "period_end": "2026-01-11",
         "department_scope": "mixed_or_unspecified", "cost_category": "accommodation", "rate_basis": "per_room_night",
         "unit_rate_lkr": "2000", "quantity": "1", "days_or_nights": "2", "team_multiplier": "1",
         "team_multiplier_source": "source_column", "reported_estimated_cost_lkr": "4000", "recomputed_cost_lkr": "4000",
         "reported_minus_recomputed_lkr": "0", "record_type": "estimate", "allocation_scope": "team_or_trip_not_division",
         "actual_overnight_confirmation": F, "source_id": "SRC_T2", "sheet_id": "SHT_T4", "source_row": "20"},
    ],
    "vehicle_rate_evidence": [
        {"rate_id": "RATE_T1", "budget_document_id": "BDG_T1", "vehicle_model_id": "VMD_T1", "fuel_type": "test diesel",
         "source_period_start": "2026-01-05", "source_period_end": "2026-01-11", "fuel_price_lkr_per_l": "300",
         "assumed_efficiency_km_per_l": "10", "rate_status": "historical_budget_assumption_not_current_quote",
         "source_id": "SRC_T2", "sheet_id": "SHT_T4", "source_row": "30"},
    ],
    "farm_vehicle_evidence": [
        {"vehicle_evidence_id": "FVE_T1", "target_level": "farm", "target_id": "FRM_T1", "farm_id": "FRM_T1", "vehicle_model_id": "VMD_T1",
         "reference_row_count": "1", "weekly_plan_row_count": "2", "first_budget_period": "2026-01-05", "last_budget_period": "2026-01-11",
         "evidence_record_ids": "FTR_T1", "requirement_status": "budget_model_evidence_only",
         "mandatory_vehicle_requirement_confirmed": F, "applies_to_every_division": "not_assumed"},
        {"vehicle_evidence_id": "FVE_T2", "target_level": "division", "target_id": "DIV_T1", "farm_id": "FRM_T1", "vehicle_model_id": "VMD_T2",
         "reference_row_count": "0", "weekly_plan_row_count": "1", "first_budget_period": "", "last_budget_period": "",
         "evidence_record_ids": "FTR_T2", "requirement_status": "budget_model_evidence_only",
         "mandatory_vehicle_requirement_confirmed": F, "applies_to_every_division": "not_assumed"},
    ],
    "budget_expense_lines": [
        {"expense_line_id": "EXP_T1", "budget_document_id": "BDG_T1", "record_type": "estimate", "cost_category": "fuel",
         "department_scope": "operations", "period_start": "2026-01-05", "period_end": "2026-01-11", "amount_lkr": "3000",
         "expense_grain": "document_summary_line", "is_additive_to_detail_tables": F, "actual_audit_status": "not_actual",
         "division_allocation": "not_available", "source_id": "SRC_T2", "sheet_id": "SHT_T4", "source_row": "40", "source_amount_column": "D"},
        {"expense_line_id": "EXP_T2", "budget_document_id": "BDG_T2", "record_type": "actual_recorded", "cost_category": "fuel",
         "department_scope": "operations", "period_start": "2026-01-12", "period_end": "2026-01-18", "amount_lkr": "2800",
         "expense_grain": "document_summary_line", "is_additive_to_detail_tables": F,
         "actual_audit_status": "source_reported_not_independently_audited", "division_allocation": "not_available",
         "source_id": "SRC_T3", "sheet_id": "SHT_T5", "source_row": "41", "source_amount_column": "G"},
        {"expense_line_id": "EXP_T3", "budget_document_id": "BDG_T1", "record_type": "estimate", "cost_category": "accommodation",
         "department_scope": "operations", "period_start": "2026-01-05", "period_end": "2026-01-11", "amount_lkr": "",
         "expense_grain": "document_summary_line", "is_additive_to_detail_tables": F, "actual_audit_status": "not_actual",
         "division_allocation": "not_available", "source_id": "SRC_T2", "sheet_id": "SHT_T4", "source_row": "42", "source_amount_column": "D"},
    ],
    "budget_reconciliation": [
        {"reconciliation_id": "REC_T1", "budget_document_id": "BDG_T1", "detail_table": "budget_fuel_trips", "source_sheet_id": "SHT_T4",
         "detail_line_count": "1", "missing_amount_count": "0", "reported_total_lkr": "3000", "sum_reported_detail_lkr": "3000",
         "reported_minus_detail_lkr": "0", "check_status": "agrees_within_LKR_1", "source_id": "SRC_T2", "source_row": "50"},
        {"reconciliation_id": "REC_T2", "budget_document_id": "BDG_T2", "detail_table": "budget_fuel_trips", "source_sheet_id": "SHT_T5",
         "detail_line_count": "1", "missing_amount_count": "0", "reported_total_lkr": "450", "sum_reported_detail_lkr": "500",
         "reported_minus_detail_lkr": "-50", "check_status": "mismatch", "source_id": "SRC_T3", "source_row": "51"},
    ],
    "data_quality_issues": [
        {"issue_id": "ISS_T1", "severity": "review", "issue_code": "OPERATION_DIVISION_LINK_PENDING", "table_name": "operation_units",
         "record_id": "OPU_T2", "detail": "Fictional fixture issue.", "source_id": "", "resolution_status": "open"},
    ],
    "rules_and_assumptions": [
        {"rule": "target_interval_days", "value": "30", "status": "user_stated", "interpretation": "Fixture rule."},
        {"rule": "operational_tolerance_days", "value": "5", "status": "user_stated", "interpretation": "Fixture rule."},
        {"rule": "proposal_tolerance_days", "value": "3", "status": "submitted_proposal", "interpretation": "Fixture rule."},
    ],
}

TEMPLATE_COLUMNS = {name: ["record_id", "evidence_reference"] for name in KNOWN_TEMPLATES}

Mutator = Callable[[dict[str, list[dict[str, str]]], dict[str, list[str]]], None]


def build_package(root: Path, mutate: Mutator | None = None, *, drop_files: tuple[str, ...] = ()) -> Path:
    """Write the fictional package under ``root`` and return the package path.

    ``mutate(rows, columns)`` may edit rows/columns before writing to create
    failure cases. ``drop_files`` lists relative paths not to write.
    """
    pkg = root / "Fixture_Package_v0_2"
    (pkg / "data").mkdir(parents=True, exist_ok=True)
    (pkg / "docs").mkdir(parents=True, exist_ok=True)
    rows = copy.deepcopy(BASE_ROWS)
    columns = {name: list(TABLES[name].required_columns) for name in rows}
    if mutate:
        mutate(rows, columns)

    schema_tables = {}
    for name, cols in columns.items():
        if f"data/{name}.csv" in drop_files:
            continue
        with (pkg / "data" / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for row in rows.get(name, []):
                writer.writerow({c: row.get(c, "") for c in cols})
        schema_tables[name] = {"rows": len(rows.get(name, [])), "columns": cols}
    for name, cols in TEMPLATE_COLUMNS.items():
        (pkg / "data" / f"{name}.csv").write_text(",".join(cols) + "\n", encoding="utf-8")
        schema_tables[name] = {"rows": 0, "columns": cols}

    files = {
        "README.md": "# Fictional fixture package for tests\n",
        "docs/schema.json": json.dumps({"version": "fixture", "tables": schema_tables}, indent=1),
        "docs/validation_results.json": json.dumps({"checks_passed": 2, "checks_total": 2, "all_passed": True,
                                                    "checks": [{"check": "fixture_a", "passed": True},
                                                               {"check": "fixture_b", "passed": True}]}),
    }
    for rel, text in files.items():
        if rel not in drop_files:
            (pkg / rel).write_text(text, encoding="utf-8")
    manifest = []
    for path in sorted(p for p in pkg.rglob("*") if p.is_file()):
        rel = path.relative_to(pkg).as_posix()
        manifest.append({"file": rel, "size_bytes": path.stat().st_size,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if "FILE_MANIFEST.json" not in drop_files:
        (pkg / "FILE_MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return pkg


def file_hashes(pkg: Path) -> dict[str, str]:
    return {p.relative_to(pkg).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in pkg.rglob("*") if p.is_file()}
