# Synthetic demonstration data

`demo_operations.csv` is **entirely synthetic**. It was written by hand for
this repository and is not derived from, sampled from, or scaled from any real
company record. All identifiers (`DEMO_UNIT_###`, `DEMO_CLIENT_*`,
`DEMO_OBS_####`) are fictional and every row has `data_origin = synthetic_demo`.

It contains 27 data rows (spreadsheet rows 2-28) covering six fictional
operating units and three fictional clients. Units have deliberately different
history lengths (DEMO_UNIT_005 and DEMO_UNIT_006 start later) to illustrate
that a short history is not evidence of missed visits.

Schema and rules: see [docs/data_contract.md](../../docs/data_contract.md).

## Illustrative (valid) situations

| Rows | What it shows |
| --- | --- |
| Planned visits with blank `actual_date` | A plan legitimately has no actual date. Not an error. |
| DEMO_OBS_0006 and DEMO_OBS_0007 | Two capture observations on consecutive days for one unit: an example of a multi-day capture. How these count as one completed service is **unresolved** and not decided here. |
| DEMO_OBS_0011 | A planned visit with no matching capture observation. This is **not** labelled as missed or cancelled. |
| DEMO_OBS_0022 | Trial visit with blank `client_id` (optional field). |
| DEMO_OBS_0025 | Planned visit with blank `area_ha` (optional field). |

## Intentional quality issues (test/demo cases)

These are included on purpose so the Data Quality view and tests have
something to detect. They are not mistakes to be "fixed" in the file.

| Spreadsheet row | observation_id | Field | Expected issue code |
| --- | --- | --- | --- |
| 17 | DEMO_OBS_0016 | actual_date = `2026-02-30` | `INVALID_DATE` |
| 19 | DEMO_OBS_0018 | area_ha = `-12.5` | `NEGATIVE_AREA` |
| 21 and 22 | DEMO_OBS_0020 (twice) | observation_id | `DUPLICATE_OBSERVATION_ID` (both rows reported) |
| 23 | DEMO_OBS_0021 | operating_unit_id blank | `MISSING_REQUIRED_VALUE` |
| 25 | DEMO_OBS_0023 | area_ha = `approx 8` | `INVALID_NUMBER` |
| 26 | DEMO_OBS_0024 | record_type = `completed_service` | `UNEXPECTED_RECORD_TYPE` |

Expected total: 7 issue rows, all severity `error`. This is asserted in
`tests/test_validation.py::test_bundled_demo_reports_exactly_the_documented_issues`.
