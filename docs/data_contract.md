# Data contract - demonstration operations schema (v0.1)

This contract applies to the **synthetic demonstration CSV** and to any CSV
uploaded to the dashboard. It is not a description of the company's raw
workbooks; those need a separate, reviewed adapter (planned).

The authoritative machine-readable definition is
`src/agriflight/data/schema.py`.

## File format

- UTF-8 CSV (a UTF-8 BOM is accepted), comma-separated, one header row.
- Every value is read as **text**. Blanks remain blank; nothing is converted to
  zero or NaN in the source table.
- Dates: `YYYY-MM-DD` only, and must be real calendar dates.
- `source_row` is added by the loader: spreadsheet row number (header = 1).
  It is reserved and must not appear in the input.

## Fields

All nine columns must be present. The *value* rules differ per field.

| Field | Value rule | Meaning |
| --- | --- | --- |
| `observation_id` | **Required**, unique | Identifier of one source record (row). Not a flight ID or service ID. |
| `operating_unit_id` | **Required** | Operating unit: a farm, division or crop/maturity group. Not necessarily one farm. |
| `client_id` | Optional | Client that owns the unit. May be blank (e.g. prospective trial client). |
| `record_type` | **Required**, one of the values below | Kind of record. |
| `planned_date` | Required for `planned_visit`; optional otherwise | Date the visit was planned for. |
| `actual_date` | Required for `capture_observation`; optional otherwise | Date recorded for an actual capture. Blank on a planned visit is normal. |
| `recorded_status` | Optional free text | Status as written in the source. Not interpreted and not a verified completion flag. |
| `area_ha` | Optional; if present a finite number >= 0 | Hectares associated with the record, as recorded. |
| `data_origin` | **Required** | Provenance. Every public demonstration row is `synthetic_demo`. |

## Record types

| Value | Meaning |
| --- | --- |
| `planned_visit` | A plan to visit a unit on a date. A plan is not evidence that a visit happened. |
| `capture_observation` | A source record that a capture took place on a date. One service may span several observations (e.g. a multi-day capture). |
| `trial_visit` | A trial/demonstration visit, outside the recurring-service assumptions. |

Any other value (for example `completed_service`) is reported as
`UNEXPECTED_RECORD_TYPE`. There is intentionally no "completed service"
type yet.

## Validation rules

| Code | Severity | Rule |
| --- | --- | --- |
| `MISSING_REQUIRED_COLUMN` | error | A schema column is absent. Checks depending on it are skipped. |
| `UNEXPECTED_COLUMN` | info | Extra column present; shown but not used. |
| `NO_DATA_ROWS` | warning | Header present but no rows. |
| `MISSING_REQUIRED_VALUE` | error | Blank `observation_id`, `operating_unit_id`, `record_type` or `data_origin`. |
| `DUPLICATE_OBSERVATION_ID` | error | Same non-blank ID on several rows; every occurrence is reported, none dropped. |
| `INVALID_DATE` | error | Non-blank date that is not a real `YYYY-MM-DD` date. |
| `MISSING_CONDITIONAL_DATE` | error | `planned_visit` without `planned_date`, or `capture_observation` without `actual_date`. |
| `INVALID_NUMBER` | error | Non-blank `area_ha` that is not a finite number. |
| `NEGATIVE_AREA` | error | `area_ha` < 0. |
| `UNEXPECTED_RECORD_TYPE` | error | `record_type` outside the documented values. |
| `NON_SYNTHETIC_ORIGIN` | warning | `data_origin` other than `synthetic_demo` (privacy reminder). |

Blank optional values are **not** issues. They appear only in the
missing-value summary, with the policy for that field.

Validation never deletes rows, fills unknown values, or infers dates or
completion statuses.

## Why observations are not automatically completed services

A completed service is a business concept that has not been defined yet:

- A single service can produce several capture observations (multi-day
  captures), and the rule for when they count as **one** completed service is
  unconfirmed.
- Source trackers overlap, so the same capture may appear in several records;
  source precedence is unconfirmed.
- Planned visits without a matching observation may be missing records,
  unfinished work, or visits outside a client's service period - not
  automatically missed or cancelled visits.
- Clients were onboarded at different times, so a short history is not
  evidence of missed visits.

Therefore this milestone counts **source records** by type and never derives
completed services, overdue labels or cancellations.

## Cadence policy (recorded, not applied)

The stated recurring-service target is **30 days with +/-5 days tolerance**
(the submitted proposal mentioned approximately +/-3 days; the current stated
guidance is +/-5). It is not applied in this milestone because the applicable
service periods, the anchor date and the multi-day completion rule are still
being confirmed. An earlier prepared field called `monitoring_interval_days`
held elapsed days, not a contractual interval, and is not used.
