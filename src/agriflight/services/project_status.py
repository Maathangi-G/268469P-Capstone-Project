"""Static, reviewable statement of milestone status shown in the dashboard.

Kept as data (not UI code) so it is versioned and easy to update honestly.
Nothing here is a measured result.
"""

from __future__ import annotations

MILESTONE = "Milestone 4 - rule-based scheduling baseline on fictional scenarios (v0.4.0, awaiting student review)"

CADENCE_POLICY = {
    "target_interval_days": 30,
    "operational_tolerance_days": 5,
    "proposal_tolerance_days": 3,
    "status": "Recorded rules only. NOT applied to any real record; no due dates or late-visit labels are calculated.",
    "note": (
        "Operational instruction (student): 30 days +/-5. Submitted proposal (p.1 and p.2 section 3.3): "
        "about 30 days after the previous completed flight, approximately +/-3 days. These are kept "
        "separate and not reconciled. Which service periods apply, the cadence anchor and how multi-day "
        "captures count as a completed service are unconfirmed."
    ),
}

IMPLEMENTED = [
    "Synthetic demonstration dataset (data/sample/demo_operations.csv) with documented intentional quality issues.",
    "CSV loader, validator and summaries for the synthetic demonstration schema.",
    "Explicit data modes: synthetic (default) and private operational dataset via AGRIFLIGHT_DATA_DIR.",
    "Read-only loader for 18 integrated-package tables: text-preserving, strict date/boolean/number parsing.",
    "Application checks: required columns, primary keys, foreign keys, hierarchy, snapshot reconciliation.",
    "Descriptive views: divisions/readiness, source observations by layer, budget and vehicle evidence, data quality.",
    "Budget safeguards: one row per fuel trip, no cost allocation to linked farms, rollups kept separate.",
    "Automated tests with fictional relational fixtures (no real rows).",
    "Reproducible EDA: completeness, recorded-date history, gaps between recorded capture dates, area evidence, overlap.",
    "Coverage-target feasibility report and feature-availability review (results private).",
    "Historical-mean baseline: implemented and tested; not fitted or evaluated on operational targets.",
    "Rule-based scheduling baseline: draft itineraries, estimated costs and an independent checker "
    "(fictional scenarios only; not optimisation, not dispatch authorisation).",
]

PENDING = [
    "Approved completion rule and completed-service ledger (input contract empty).",
    "Verified daily-hectare targets: coverage-model training is blocked until they exist.",
    "Cadence-window evaluation on approved service records.",
    "Fitting/evaluating the baseline and ML models (proposal section 3.2) on verified targets.",
    "Approved real planning scenario (due dates, resources, availability, depots, travel matrix, rates).",
    "OR-Tools scheduling/routing and its comparison with the rule-based baseline (proposal section 3.3).",
    "Overnight stays and multi-day jobs (not supported by the baseline version 1).",
    "Weather-informed replanning, scenario and cost analysis (proposal sections 3.4-3.6).",
]

OPEN_DECISIONS = [
    ("Completion rule", "How multi-day captures and partial coverage count as one completed service (currently unknown)."),
    ("Cadence tolerance", "Operational +/-5 days vs proposal +/-3 days - which applies for evaluation."),
    ("Cadence anchor", "Proposal: previous completed service; no verified completion dates exist yet."),
    ("Service periods", "Which divisions/periods are recurring service; onboarding dates are unknown."),
    ("Source precedence", "How overlapping main_monthly, older_archive and annual_cycles records are reconciled."),
    ("Mappings", "Approval of unresolved operation-unit to division links and route-entity candidates."),
    ("Resources and locations", "Pilot availability, physical vehicles, base location and verified access points."),
]

NOT_CLAIMED = [
    "No model has been trained; no accuracy, error or prediction results exist.",
    "No completed services, due dates, overdue, late or cancellation labels have been derived.",
    "No scheduling improvement, optimisation superiority, travel saving or cost saving is claimed.",
    "Scheduling outputs are drafts on fictional inputs; no company division is made scheduler-ready.",
    "Source observations are not treated as completed flights or reconciled services.",
    "Budget rows are historical estimates, not actual spend or a forecast budget.",
]
