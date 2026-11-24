"""Static, reviewable statement of milestone status shown in the dashboard.

Kept as data (not UI code) so it is versioned and easy to update honestly.
Nothing here is a measured result.
"""

from __future__ import annotations

MILESTONE = "Foundation milestone - Data Readiness Dashboard (v0.1.0)"

CADENCE_POLICY = {
    "target_interval_days": 30,
    "tolerance_days": 5,
    "status": "Stated business policy. NOT yet applied to any real client records.",
    "note": (
        "The submitted proposal referred to approximately +/-3 days; the current "
        "stated business guidance is +/-5 days. Which service periods it applies to, "
        "the cadence anchor date and how multi-day captures count are unconfirmed."
    ),
}

IMPLEMENTED = [
    "Synthetic demonstration dataset (data/sample/demo_operations.csv) with documented intentional quality issues.",
    "CSV loader that reads every value as text, preserves IDs and blanks, and records source row numbers.",
    "Data-quality validator producing a structured issue table (row, field, code, severity, explanation).",
    "Summary service: record counts by type, distinct units/clients, valid date ranges, blank-value summary.",
    "Local Streamlit dashboard: Overview, Data Explorer (filters + in-memory CSV upload), Data Quality, Project Status.",
    "Automated pytest suite for loader, validator and summary service.",
]

PENDING = [
    "Reviewed adapter from the private company workbooks to this schema (not started; requires approved mappings).",
    "Deduplicated completed-service event ledger.",
    "Cadence-window evaluation (30 days +/-5) on real records.",
    "Daily coverage prediction baseline and ML models (proposal section 3.2).",
    "Cadence-aware scheduling, routing and resource allocation (proposal section 3.3).",
    "Weather-informed replanning, scenario and cost analysis (proposal sections 3.4-3.6).",
]

OPEN_DECISIONS = [
    ("Service periods", "Which client service periods/episodes the 30-day recurring target applies to."),
    ("Cadence anchor", "Whether the interval runs from the last completed service, the planned date, or another anchor."),
    ("Completion rule", "How multi-day captures and partial coverage count as one completed service."),
    ("Source precedence", "Which source wins when the monthly, archive and cycle trackers overlap or disagree."),
    ("Mappings", "Approval of operating-unit, farm/division and alias mappings (no fuzzy match is auto-approved)."),
    ("Onboarding dates", "Client onboarding/service start dates, so short histories are not read as missed visits."),
]

NOT_CLAIMED = [
    "No model has been trained; no accuracy, error or prediction results exist.",
    "No overdue, late or cancellation labels have been calculated for real farms.",
    "No scheduling improvement, travel saving or cost saving is claimed.",
    "Capture observations are not treated as reconciled completed services.",
]
