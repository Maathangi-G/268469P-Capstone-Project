# Operational dataset integration (milestone 2, read-only)

This document describes how the application reads the **private integrated
operational dataset package (layout v0.2)**. It contains structure and rules
only: no record values, counts, costs or analysis results from the real data.

> The package is pseudonymised **real** company data. It is never stored in
> this repository, and its contents must not appear in commits, issues,
> screenshots or public documents.

## Configuration

| Item | Value |
| --- | --- |
| Environment variable | `AGRIFLIGHT_DATA_DIR` |
| Points to | The package **root** (contains `README.md`, `FILE_MANIFEST.json`, `data/`, `docs/`), not `data/` |
| Default mode | Synthetic demonstration. Setting the variable does **not** switch modes. |
| Private mode | Chosen explicitly in the sidebar: *Data mode -> Private operational dataset* |

Windows PowerShell example (run from the repository root; adjust the relative
path to where your private package actually is):

```powershell
$env:AGRIFLIGHT_DATA_DIR = (Resolve-Path "..\Dataset\AgriFlight_Integrated_v0_2").Path
streamlit run app/app.py
```

If the variable is unset, the path does not exist, or required package entries
are missing, private mode shows an error and no data. It never falls back to
synthetic data. Pointing the variable at `data/` produces a hint to use the
package root.

## Components

| Module | Responsibility |
| --- | --- |
| `agriflight.operational.contract` | Columns, types, primary keys, foreign keys and allowed values the app relies on. No row counts are hardcoded. |
| `agriflight.operational.loader` | Resolves the location, checks package structure, and reads `data/*.csv` read-only. Keeps raw text and typed copies, and recognises header-only templates. |
| `agriflight.operational.validation` | Application checks: required columns, blank/duplicate keys, foreign keys (including pipe-separated lists and level-dependent targets), hierarchy agreement, allowed values, snapshot and manifest reconciliation. |
| `agriflight.operational.summaries` | Descriptive tables for the four views, with the counting safeguards below. |
| `agriflight.operational.session` | In-memory per-session cache keyed on package path and file size/mtime. Cleared when switching to synthetic mode. |
| `app/operational_views.py` | Streamlit rendering only. |

## Parsing rules

- Every CSV value is first read as text. IDs keep their exact text (no numeric conversion).
- Dates: strict `YYYY-MM-DD`. Anything else is reported as `invalid_date` and is missing in calculations.
- Booleans: only the text `True` / `False`, after trimming surrounding whitespace (`" True "` parses as True; the raw text is kept unchanged). `"False"` is never true; blank is unknown. Any other non-blank text (e.g. `true`, `1`, `yes`) is unknown and reported as `invalid_boolean`.
- Numbers: `pandas.to_numeric` (scientific notation such as `1e-06` is accepted). A blank value is missing, never zero.
- Lists such as `operation_unit_ids` are pipe-separated text. They are split only to check foreign keys and count members.
- Opaque IDs (`DIV_…`, `FRM_…`, `CLI_…`) are **never split**. Hierarchy comes only from the `farm_id` / `client_id` columns.

## Supported tables

Main tables (with views): `scheduler_division_inputs`, `flight_observations`,
`budget_fuel_trips`, `accommodation_estimates`, `vehicle_rate_evidence`,
`farm_vehicle_evidence`, `budget_expense_lines`, `data_quality_issues`,
`budget_reconciliation`.

Supporting tables (joins and labels): `clients`, `farms`, `divisions`,
`operation_units`, `vehicle_models`, `budget_documents`, `route_index`,
`route_entity_links`, `rules_and_assumptions`.

Templates (header only, recognised as **unfilled input contracts**):
`service_completion_template`, `daily_coverage_template`,
`pilot_availability_template`, `physical_vehicle_template`,
`schedule_change_template`.

Not loaded in this milestone: the restricted identity/location package,
original budget archives, the presentation workbook and other raw sources.

## Join rules

- `divisions.farm_id -> farms.farm_id -> clients.client_id`, and `divisions.client_id` must agree with the farm's client.
- `scheduler_division_inputs` is one row per `division_id`. Its farm/client must agree with `divisions`.
- `flight_observations.operation_unit_id -> operation_units`; `flight_observations.division_id -> divisions` (blank = unresolved link).
- `budget_fuel_trips.route_id -> route_index`; `route_entity_links.route_id -> route_index` (**one route : many links**).
- `route_entity_links.target_id` and `farm_vehicle_evidence.target_id` refer to `farms` or `divisions`, depending on `target_level`.
- Vehicle model and budget document IDs refer to `vehicle_models` and `budget_documents`.
- Child counts (observations per division, links per route, evidence per target) are computed by group-by and mapped onto the parent. One-to-many tables are never merged into a parent in a way that would repeat its rows.

## Budget counting safeguards

1. One row and one cost per `fuel_trip_id`. The view asserts uniqueness.
2. A route may link to several farms. Its distance and cost are **not** copied or apportioned to each farm.
3. A farm filter shows the trips linked to that farm, labelled *shared trip estimate - not allocated to this farm*.
4. `budget_expense_lines` are summary rollups that overlap the fuel and accommodation detail. They are shown separately and never added to it.
5. `actual_recorded` expense lines are shown separately from estimates and labelled source-reported, unaudited and incomplete.
6. Sums use `min_count=1` and display the number of missing values. If no values are known, the result is "unknown", not zero.
7. Totals are labelled as sums over the selected estimate rows. They are not deduplicated annual spend, not actual spend and not a forecast.
8. Department scope and purpose filters default to *all*. Mixed or unspecified activities are not silently restricted to drone work.
9. Two different checks are kept apart:
   - **Per-record arithmetic** (each fuel or accommodation row): the full reported value, recomputed value and difference are shown side by side. Rows with a difference of at least LKR 1 are counted as discrepancies. Smaller differences are within the reporting tolerance, which matches the package's own; they are not exact matches.
   - **Subtotal reconciliation** (supplied by the package, per source sheet): a reported subtotal compared with the sum of its detail lines. Not all subtotals agree. Mismatched and not-checkable subtotals are listed and preserved as source issues, not repaired.

   Missing amounts stay unknown. Out-of-period trip dates are displayed, not corrected.
10. Units are explicit: LKR, km, litres, km per litre, LKR per litre. Rates are historical budget assumptions, not current prices.

## Descriptive analysis vs operational validation

The views are **descriptive**. They show what the source records contain.
They do not:

- treat source observations as completed flights or services, or add the overlapping layers together;
- treat `last_recorded_capture_date` as a confirmed completion or onboarding date;
- interpret a month without records as a missed or cancelled visit;
- calculate due dates or late-visit labels, or apply either cadence tolerance (operational +/-5 days and proposal +/-3 days are shown separately);
- change `scheduler_ready` or any readiness flag;
- treat vehicle evidence as a mandatory access rule or current fleet availability.

## Two kinds of findings

| Source | Meaning |
| --- | --- |
| `data_quality_issues.csv`, `docs/validation_results.json` | Supplied with the package. Shown as supplied; not re-run by the app. |
| Application checks (`validate_operational`) | Run now by this app on the loaded files. |

A clean result from the application checks means the files match the
structural contract. It does not resolve the package's source issues or
confirm business readiness.

## Limitations

- Only the tables listed above are integrated. Area evidence, planned schedules, trials and daily-work evidence are not yet shown.
- The mapping between tracker operation units and divisions is shown as supplied. No mapping is approved or changed.
- Snapshot reconciliation compares against the package's own schema and manifest. It cannot detect errors that are already in the source.
- Browser interaction must be verified manually. Automated tests use fictional fixtures and headless Streamlit only.
