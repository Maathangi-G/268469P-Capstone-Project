"""Application contract for the integrated operational dataset (v0.2 layout).

This lists only the columns, types and relationships the application relies
on. It describes structure, not data: no record values appear here. Snapshot
row counts are NOT hardcoded; they are read from the package's schema.json and
used for reconciliation only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ENV_VAR = "AGRIFLIGHT_DATA_DIR"
DATE_FORMAT = "%Y-%m-%d"
TRUE_TEXT = "True"
FALSE_TEXT = "False"
LIST_SEPARATOR = "|"

REQUIRED_PACKAGE_ENTRIES: tuple[str, ...] = (
    "README.md",
    "FILE_MANIFEST.json",
    "data",
    "docs",
    "docs/schema.json",
)

OBSERVATION_LAYERS: tuple[str, ...] = ("main_monthly", "older_archive", "annual_cycles")
DEFAULT_OBSERVATION_LAYER = "main_monthly"
OBSERVATION_DATE_FIELDS: tuple[str, ...] = ("recorded_actual_date", "planned_date")

KNOWN_TEMPLATES: tuple[str, ...] = (
    "service_completion_template",
    "daily_coverage_template",
    "pilot_availability_template",
    "physical_vehicle_template",
    "schedule_change_template",
)


@dataclass(frozen=True)
class TableSpec:
    name: str
    # "main" (has a view), "supporting" (joins/labels), "analysis" (EDA and
    # coverage feasibility) or "template" (input contract; zero rows is valid).
    role: str
    primary_key: str
    text_columns: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()
    boolean_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    list_columns: tuple[str, ...] = ()  # pipe-separated ID lists, kept as text
    # Allowed values for columns the UI's safeguards depend on.
    allowed_values: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def required_columns(self) -> tuple[str, ...]:
        ordered = (
            (self.primary_key,)
            + self.text_columns
            + self.date_columns
            + self.boolean_columns
            + self.numeric_columns
            + self.list_columns
        )
        return tuple(dict.fromkeys(ordered))


@dataclass(frozen=True)
class ForeignKey:
    table: str
    column: str
    ref_table: str
    ref_column: str
    is_list: bool = False
    # Only check rows where condition_column == condition_value (polymorphic target_id).
    condition_column: str | None = None
    condition_value: str | None = None


PROVENANCE = ("source_id", "sheet_id", "source_row")

TABLES: dict[str, TableSpec] = {
    spec.name: spec
    for spec in (
        # ---- main tables ------------------------------------------------
        TableSpec(
            "scheduler_division_inputs", "main", "division_id",
            text_columns=("division_name", "farm_id", "farm_name", "client_id",
                          "area_approval_status", "coordinate_access", "readiness_blockers"),
            date_columns=("first_recorded_capture_date", "last_recorded_capture_date",
                          "last_confirmed_service_completion_date", "next_due_date"),
            boolean_columns=("vehicle_requirement_approved", "scheduler_ready"),
            numeric_columns=("identity_link_count", "tracker_imaging_area_ha", "target_interval_days",
                             "operational_tolerance_days", "proposal_tolerance_days", "field_point_count"),
            list_columns=("operation_unit_ids", "vehicle_model_evidence_ids"),
        ),
        TableSpec(
            "flight_observations", "main", "observation_id",
            text_columns=("source_layer", "operation_unit_id", "division_id", "identity_link_method",
                          "equipment_reference", "daily_coverage_label_status", "completed_service_id",
                          "completion_scope", "observation_status", "service_cadence_label") + PROVENANCE,
            date_columns=("planned_date", "recorded_actual_date"),
            boolean_columns=("source_review_flags_present",),
            numeric_columns=("actual_daily_covered_ha",),
            list_columns=("person_ids",),
            allowed_values={"source_layer": OBSERVATION_LAYERS},
        ),
        TableSpec(
            "budget_fuel_trips", "main", "fuel_trip_id",
            text_columns=("budget_document_id", "route_id", "date_check", "department_scope",
                          "purpose_category", "vehicle_model_id", "record_type", "distance_scope",
                          "cost_allocation") + PROVENANCE,
            date_columns=("planned_date", "period_start", "period_end"),
            boolean_columns=("actual_flight_evidence",),
            numeric_columns=("estimated_distance_km", "assumed_efficiency_km_per_l", "fuel_price_lkr_per_l",
                             "reported_estimated_fuel_l", "reported_estimated_fuel_cost_lkr",
                             "recomputed_fuel_l", "recomputed_fuel_cost_lkr", "reported_minus_recomputed_lkr"),
            allowed_values={"record_type": ("estimate",),
                            "cost_allocation": ("unallocated_shared_trip_cost",)},
        ),
        TableSpec(
            "accommodation_estimates", "main", "accommodation_line_id",
            text_columns=("budget_document_id", "department_scope", "cost_category", "rate_basis",
                          "team_multiplier_source", "record_type", "allocation_scope") + PROVENANCE,
            date_columns=("period_start", "period_end"),
            boolean_columns=("actual_overnight_confirmation",),
            numeric_columns=("unit_rate_lkr", "quantity", "days_or_nights", "team_multiplier",
                             "reported_estimated_cost_lkr", "recomputed_cost_lkr",
                             "reported_minus_recomputed_lkr"),
            allowed_values={"record_type": ("estimate",)},
        ),
        TableSpec(
            "vehicle_rate_evidence", "main", "rate_id",
            text_columns=("budget_document_id", "vehicle_model_id", "fuel_type", "rate_status") + PROVENANCE,
            date_columns=("source_period_start", "source_period_end",
                          "valid_from_confirmed", "valid_to_confirmed"),
            numeric_columns=("fuel_price_lkr_per_l", "assumed_efficiency_km_per_l"),
        ),
        TableSpec(
            "farm_vehicle_evidence", "main", "vehicle_evidence_id",
            text_columns=("target_level", "target_id", "farm_id", "vehicle_model_id",
                          "requirement_status", "applies_to_every_division"),
            date_columns=("first_budget_period", "last_budget_period"),
            boolean_columns=("mandatory_vehicle_requirement_confirmed",),
            numeric_columns=("reference_row_count", "weekly_plan_row_count"),
            list_columns=("evidence_record_ids",),
        ),
        TableSpec(
            "budget_expense_lines", "main", "expense_line_id",
            text_columns=("budget_document_id", "record_type", "cost_category", "department_scope",
                          "vehicle_model_id", "expense_grain", "actual_audit_status",
                          "division_allocation", "source_amount_column") + PROVENANCE,
            date_columns=("period_start", "period_end"),
            boolean_columns=("is_additive_to_detail_tables",),
            numeric_columns=("recorded_quantity", "recorded_unit_cost_lkr", "amount_lkr"),
            allowed_values={"record_type": ("estimate", "actual_recorded")},
        ),
        TableSpec(
            "data_quality_issues", "main", "issue_id",
            text_columns=("severity", "issue_code", "table_name", "record_id", "detail",
                          "source_id", "resolution_status"),
        ),
        TableSpec(
            "budget_reconciliation", "main", "reconciliation_id",
            text_columns=("budget_document_id", "detail_table", "source_sheet_id", "check_status",
                          "source_id", "source_row"),
            numeric_columns=("detail_line_count", "missing_amount_count", "reported_total_lkr",
                             "sum_reported_detail_lkr", "reported_minus_detail_lkr"),
        ),
        # ---- supporting tables -----------------------------------------
        TableSpec("clients", "supporting", "client_id", text_columns=("client_name",)),
        TableSpec("farms", "supporting", "farm_id",
                  text_columns=("client_id", "farm_name", "physical_site_equivalence")),
        TableSpec("divisions", "supporting", "division_id",
                  text_columns=("farm_id", "client_id", "division_name", "farm_name", "identity_status")),
        TableSpec(
            "operation_units", "supporting", "operation_unit_id",
            text_columns=("operation_name", "division_id", "farm_id", "identity_link_method",
                          "current_status_snapshot", "recurring_eligibility", "completion_rule_status"),
            boolean_columns=("identity_user_confirmed",),
            numeric_columns=("imaging_area_ha",),
        ),
        TableSpec("vehicle_models", "supporting", "vehicle_model_id",
                  text_columns=("vehicle_model", "vehicle_type", "drive_configuration",
                                "physical_vehicle_identity")),
        TableSpec(
            "budget_documents", "supporting", "budget_document_id",
            text_columns=("document_type", "period_interpretation", "currency", "historical_rate_validity"),
            date_columns=("period_start", "period_end"),
            boolean_columns=("actual_expense_section_present",),
            numeric_columns=("archive_year",),
        ),
        TableSpec("route_index", "supporting", "route_id",
                  text_columns=("route_name", "purpose_category", "travel_distance_kind"),
                  boolean_columns=("road_routing_verified",),
                  numeric_columns=("entity_link_count",)),
        TableSpec(
            "route_entity_links", "supporting", "route_entity_link_id",
            text_columns=("route_id", "target_level", "target_id", "farm_id", "link_method", "approval_status"),
            boolean_columns=("cost_allocation_allowed",),
            list_columns=("candidate_division_ids",),
        ),
        TableSpec("rules_and_assumptions", "supporting", "rule",
                  text_columns=("value", "status", "interpretation")),
        # ---- analysis tables (EDA / coverage feasibility) ---------------
        TableSpec(
            "daily_work_evidence", "analysis", "daily_evidence_id",
            text_columns=("operation_unit_id", "division_id", "blocking_reason"),
            date_columns=("recorded_date",),
            boolean_columns=("target_measured", "training_eligible"),
            numeric_columns=("source_observation_count", "actual_covered_ha"),
            list_columns=("person_ids", "source_observation_ids"),
        ),
        TableSpec(
            "area_evidence", "analysis", "area_record_id",
            text_columns=("division_id", "operation_unit_id", "identity_link_method", "record_grain",
                          "crop", "maturity", "area_scope_status") + PROVENANCE,
            date_columns=("effective_date",),
            numeric_columns=("boundary_area_ha", "farm_total_area_ha", "contract_area_ha"),
        ),
        TableSpec(
            "observation_overlap_review", "analysis", "overlap_group_id",
            text_columns=("division_or_operation_id", "source_layers", "resolution"),
            date_columns=("recorded_date",),
            numeric_columns=("record_count",),
            list_columns=("observation_ids",),
        ),
        TableSpec(
            "planned_team_days", "analysis", "schedule_day_id",
            text_columns=("team_reference", "overnight_plan", "vehicle_model_id", "equipment_reference",
                          "source_id", "sheet_id", "source_row"),
            date_columns=("planned_date",),
            boolean_columns=("actual_execution_confirmed",),
            numeric_columns=("planned_coverage_ha", "planned_travel_km"),
            list_columns=("person_ids",),
        ),
        TableSpec(
            "trial_observations", "analysis", "trial_id",
            text_columns=("division_id", "identity_link_method", "recurring_service_eligibility",
                          "completion_status") + PROVENANCE,
            date_columns=("trial_date",),
            numeric_columns=("recorded_extent_ha",),
        ),
        TableSpec(
            "daily_coverage_template", "template", "daily_work_id",
            text_columns=("division_id", "team_id", "vehicle_id", "equipment_reference",
                          "measurement_method", "evidence_reference"),
            date_columns=("work_date",),
            boolean_columns=("independent_label_verified",),
            numeric_columns=("measured_covered_ha", "working_hours", "travel_hours"),
            list_columns=("person_ids",),
        ),
    )
}

MAIN_TABLES: tuple[str, ...] = tuple(n for n, s in TABLES.items() if s.role == "main")
SUPPORTING_TABLES: tuple[str, ...] = tuple(n for n, s in TABLES.items() if s.role == "supporting")
ANALYSIS_TABLES: tuple[str, ...] = tuple(n for n, s in TABLES.items() if s.role in ("analysis", "template"))

FOREIGN_KEYS: tuple[ForeignKey, ...] = (
    ForeignKey("farms", "client_id", "clients", "client_id"),
    ForeignKey("divisions", "farm_id", "farms", "farm_id"),
    ForeignKey("divisions", "client_id", "clients", "client_id"),
    ForeignKey("scheduler_division_inputs", "division_id", "divisions", "division_id"),
    ForeignKey("scheduler_division_inputs", "farm_id", "farms", "farm_id"),
    ForeignKey("scheduler_division_inputs", "client_id", "clients", "client_id"),
    ForeignKey("scheduler_division_inputs", "operation_unit_ids", "operation_units", "operation_unit_id", is_list=True),
    ForeignKey("scheduler_division_inputs", "vehicle_model_evidence_ids", "vehicle_models", "vehicle_model_id", is_list=True),
    ForeignKey("operation_units", "division_id", "divisions", "division_id"),
    ForeignKey("operation_units", "farm_id", "farms", "farm_id"),
    ForeignKey("flight_observations", "operation_unit_id", "operation_units", "operation_unit_id"),
    ForeignKey("flight_observations", "division_id", "divisions", "division_id"),
    ForeignKey("budget_fuel_trips", "budget_document_id", "budget_documents", "budget_document_id"),
    ForeignKey("budget_fuel_trips", "route_id", "route_index", "route_id"),
    ForeignKey("budget_fuel_trips", "vehicle_model_id", "vehicle_models", "vehicle_model_id"),
    ForeignKey("accommodation_estimates", "budget_document_id", "budget_documents", "budget_document_id"),
    ForeignKey("vehicle_rate_evidence", "budget_document_id", "budget_documents", "budget_document_id"),
    ForeignKey("vehicle_rate_evidence", "vehicle_model_id", "vehicle_models", "vehicle_model_id"),
    ForeignKey("budget_expense_lines", "budget_document_id", "budget_documents", "budget_document_id"),
    ForeignKey("budget_expense_lines", "vehicle_model_id", "vehicle_models", "vehicle_model_id"),
    ForeignKey("budget_reconciliation", "budget_document_id", "budget_documents", "budget_document_id"),
    ForeignKey("route_entity_links", "route_id", "route_index", "route_id"),
    ForeignKey("route_entity_links", "farm_id", "farms", "farm_id"),
    ForeignKey("route_entity_links", "candidate_division_ids", "divisions", "division_id", is_list=True),
    ForeignKey("route_entity_links", "target_id", "farms", "farm_id", condition_column="target_level", condition_value="farm"),
    ForeignKey("route_entity_links", "target_id", "divisions", "division_id", condition_column="target_level", condition_value="division"),
    ForeignKey("farm_vehicle_evidence", "farm_id", "farms", "farm_id"),
    ForeignKey("farm_vehicle_evidence", "vehicle_model_id", "vehicle_models", "vehicle_model_id"),
    ForeignKey("farm_vehicle_evidence", "target_id", "farms", "farm_id", condition_column="target_level", condition_value="farm"),
    ForeignKey("farm_vehicle_evidence", "target_id", "divisions", "division_id", condition_column="target_level", condition_value="division"),
    ForeignKey("daily_work_evidence", "operation_unit_id", "operation_units", "operation_unit_id"),
    ForeignKey("daily_work_evidence", "division_id", "divisions", "division_id"),
    ForeignKey("daily_work_evidence", "source_observation_ids", "flight_observations", "observation_id", is_list=True),
    ForeignKey("area_evidence", "division_id", "divisions", "division_id"),
    ForeignKey("area_evidence", "operation_unit_id", "operation_units", "operation_unit_id"),
    ForeignKey("observation_overlap_review", "observation_ids", "flight_observations", "observation_id", is_list=True),
    ForeignKey("planned_team_days", "vehicle_model_id", "vehicle_models", "vehicle_model_id"),
    ForeignKey("trial_observations", "division_id", "divisions", "division_id"),
    ForeignKey("daily_coverage_template", "division_id", "divisions", "division_id"),
)
# observation_overlap_review.division_or_operation_id may reference either
# divisions or operation_units; checked separately in validation.
