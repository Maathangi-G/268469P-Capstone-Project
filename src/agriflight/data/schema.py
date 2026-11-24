"""Single source of truth for the demonstration operations schema.

See docs/data_contract.md for the human-readable contract. This schema is for
the synthetic demonstration CSV only; raw company workbooks need a separate,
reviewed adapter before they can be mapped onto it.
"""

from __future__ import annotations

from dataclasses import dataclass

DATE_FORMAT = "%Y-%m-%d"
SOURCE_ROW_COLUMN = "source_row"
SYNTHETIC_ORIGIN = "synthetic_demo"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    column_required: bool
    value_policy: str
    description: str


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "observation_id",
        True,
        "required, unique",
        "Identifier of one source record (a row), not of a flight or service.",
    ),
    FieldSpec(
        "operating_unit_id",
        True,
        "required",
        "Operating unit the record refers to (a farm, division or crop group).",
    ),
    FieldSpec(
        "client_id",
        True,
        "optional (blank allowed, e.g. a prospective trial client)",
        "Client the operating unit belongs to.",
    ),
    FieldSpec(
        "record_type",
        True,
        "required; one of planned_visit, capture_observation, trial_visit",
        "What kind of record this is. Determines which dates are expected.",
    ),
    FieldSpec(
        "planned_date",
        True,
        "required for planned_visit; optional otherwise; YYYY-MM-DD",
        "Date the visit was planned for.",
    ),
    FieldSpec(
        "actual_date",
        True,
        "required for capture_observation; optional otherwise; YYYY-MM-DD",
        "Date recorded for an actual capture/visit. Blank on a plan is normal.",
    ),
    FieldSpec(
        "recorded_status",
        True,
        "optional free text, kept as recorded and not interpreted",
        "Status text as written in the source. Not a verified completion flag.",
    ),
    FieldSpec(
        "area_ha",
        True,
        "optional; if present, a non-negative number",
        "Area in hectares associated with the record, as recorded.",
    ),
    FieldSpec(
        "data_origin",
        True,
        "required; synthetic_demo for every public demonstration row",
        "Provenance label of the row.",
    ),
)

EXPECTED_COLUMNS: tuple[str, ...] = tuple(f.name for f in FIELDS)
REQUIRED_COLUMNS: tuple[str, ...] = tuple(f.name for f in FIELDS if f.column_required)
REQUIRED_VALUE_COLUMNS: tuple[str, ...] = (
    "observation_id",
    "operating_unit_id",
    "record_type",
    "data_origin",
)
DATE_COLUMNS: tuple[str, ...] = ("planned_date", "actual_date")
NUMERIC_COLUMNS: tuple[str, ...] = ("area_ha",)

ALLOWED_RECORD_TYPES: tuple[str, ...] = (
    "planned_visit",
    "capture_observation",
    "trial_visit",
)

# Date that must be present for a given record type (blank elsewhere is fine).
CONDITIONALLY_REQUIRED_DATE: dict[str, str] = {
    "planned_visit": "planned_date",
    "capture_observation": "actual_date",
}
