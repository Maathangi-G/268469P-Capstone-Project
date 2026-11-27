# Technical checkpoint notes (checkpoint date: 30 November 2026)

Milestone: **Foundation - Data Readiness Dashboard (v0.1.0)**.
Recorded on 24 November 2026. Final submission: 23 December 2026.

This is a foundation milestone. There is no trained model, no scheduler, and
no analysis of real company records in this repository.

## Implemented

- Demonstration data contract (`docs/data_contract.md`, `src/agriflight/data/schema.py`).
- Hand-written synthetic dataset, 27 rows, 6 fictional units, 3 fictional
  clients, with 7 documented intentional quality issues
  (`data/sample/demo_operations.csv`, `data/sample/README.md`).
- Loader: text-preserving CSV reading, `source_row` provenance, clear errors
  for empty, missing, non-UTF-8 and malformed files.
- Validator: structured issue table covering missing columns, missing
  required values, duplicate IDs, invalid dates, record-type-conditional
  dates, invalid/negative areas, unexpected record types and non-synthetic origin.
- Summary service: rows per record type (never merged), distinct units and
  clients, valid date ranges per record type, blank-value summary.
- Streamlit dashboard with Overview, Data Explorer (filters, in-memory CSV
  upload), Data Quality and Project Status views.
- Installable package (`pip install -e ".[app,dev]"`), `.gitignore` privacy
  rules, Streamlit configured for localhost-only, headless use with usage
  statistics disabled.

## Test outcomes (actual)

Environment: Windows 11, Python 3.14.7, pandas 3.1.1, Streamlit 1.67.0,
pytest 9.2.0.

| Check | Result |
| --- | --- |
| `python -m pytest` (loader 16, validation 21, summary 6, app smoke 2) | **45 passed**, 0 failed |
| Bundled demo validation | Exactly the 7 documented issues detected, all severity `error` |
| Headless app test (`streamlit.testing.AppTest`) | Script runs without exception; demo notice, "Validation failed: 7 error(s)", four tabs and the 27-row metric are rendered; upload mode with no file renders without error |
| Server startup (`streamlit run app/app.py`) | Server started; `/_stcore/health` returned `ok` on 127.0.0.1; not reachable on the LAN address |
| Fresh clone following README commands | Install succeeded, 45 passed, server started; working tree stayed clean. A first attempt in a very long folder path failed during `pip install` (Windows path-length limit, Streamlit package files) - see README Windows note |

## Not yet verified

- Manual interaction in a real browser (clicking tabs, filters, uploading a
  file, visual layout). Only headless script execution and server startup
  were checked automatically.
- Behaviour on Python versions other than 3.14.7, and on macOS/Linux.

## Current limitations

- Only the demonstration schema is supported; raw company workbooks cannot be
  loaded (a reviewed adapter is planned).
- `source_row` assumes no line breaks inside quoted CSV values.
- No completed-service, cadence, overdue or cancellation logic exists by
  design; the business rules are not confirmed.

## Unresolved decisions

- Service periods/episodes to which the 30-day +/-5-day target applies
  (the proposal stated approximately +/-3 days; current guidance is +/-5).
- Cadence anchor date.
- How multi-day captures count as one completed service.
- Source precedence where trackers overlap.
- Approval of operating-unit, farm/division and alias mappings.
- Client onboarding/service start dates.

## Milestone 2 - read-only operational dataset integration (25 November 2026, awaiting student review)

Implemented (uncommitted at the time of writing):
- Explicit data modes: synthetic (default) and private, with the private package located through
  `AGRIFLIGHT_DATA_DIR`. There is no fallback to synthetic data.
- Read-only loading of 18 package tables, with strict date/boolean/number parsing and recognition of
  header-only templates.
- Application checks run on load: required columns, primary keys, foreign keys, hierarchy, allowed
  values, and snapshot/manifest reconciliation. These are displayed separately from the package's
  supplied findings.
- Four descriptive views: divisions and readiness; source observations by layer; budget and vehicle
  evidence (with counting safeguards); data quality and readiness.

Actual test outcomes (Windows 11, Python 3.14.7, pandas 3.1.1, Streamlit 1.67.0):

| Check | Result |
| --- | --- |
| Test suite before changes | 45 passed |
| Test suite after changes | 94 passed, 0 failed (one test assertion was corrected during development; see AI log) |
| Headless app run against the real private package (not a committed test) | All five private-mode tabs rendered without exception; the layer, date-field, farm and single-division selectors ran without exception; switching back to synthetic mode cleared the private cache |
| Server startup with `AGRIFLIGHT_DATA_DIR` set | `/_stcore/health` returned `ok` on 127.0.0.1; not reachable on the LAN address |
| Private package integrity after the runs | All FILE_MANIFEST.json hashes still match; no files added |

Manual browser verification: reported as completed by the student on 25 November 2026 (not observed by
the AI assistant). Student review of the design decisions and approval to commit are still pending.

## Milestone 3 - EDA, coverage-target feasibility and guarded baseline (25 November 2026; commit approved by the student 27 November 2026)

Methods are described in [eda_methodology.md](eda_methodology.md). Real-data results are private and are not
reproduced here.

| Kind | Status |
| --- | --- |
| Implemented | EDA (completeness, recorded-date history, gaps between recorded capture dates, area evidence, overlap summary); coverage-target feasibility report; feature-availability review; historical-mean baseline; `scripts/run_eda.py`; app tab *EDA & coverage readiness*. |
| Executed on real records | The EDA and feasibility report, via the script (outputs in the private sibling folder) and a headless app run. |
| Tested only with fictional fixtures | All EDA edge cases, eligibility rules and baseline behaviour, including MAE/RMSE arithmetic. |
| Blocked | Coverage-model training: no verified daily-hectare targets in the inspected integrated package. |
| Baseline on real data | Implemented and tested with fictional fixtures; not fitted or evaluated on operational targets. No real predictive-performance results are available. |
| Feature-availability review | AI-proposed and provisional; not validated. |

Actual automated results (Windows 11, Python 3.14.7): tests before the milestone **94 passed**; after it,
**131 passed**. Two defects were found and fixed during development: a dtype error in the finiteness check,
and a test that mixed exclusion reasons across sources. A packaging issue was also caught: the repository's
`models/` ignore rule would have hidden the new package, so it was renamed to `baselines/`. Headless app run
on real data: the new tab and all layer selections rendered without exception. Server startup: health `ok`.
Browser verification of the new tab has not been performed by the student or recorded.

The Data Science component is **not** complete. Coverage prediction, its evaluation and the scheduling
comparison remain outstanding.

## Milestone 4 - rule-based scheduling baseline (27 November 2026, awaiting student review)

Details: [scheduling_baseline.md](scheduling_baseline.md).

| Kind | Status |
| --- | --- |
| Implemented | Scenario input contracts and validator; deterministic greedy day/bundle rule; cost estimation; independent checker; `scripts/run_schedule.py`; synthetic-mode tab *Scheduling baseline*; fictional demo scenario and its generator. |
| Executed on real records | Nothing. No approved real planning scenario exists, and the private dataset was not used. |
| Tested with fictional scenarios | All rule, constraint, cost and checker behaviour. |
| Not claimed | Optimisation, operational validation, ML accuracy, savings, dispatch readiness. No company division is made scheduler-ready. |

Actual automated results (Windows 11, Python 3.14.7): tests before the milestone **131 passed**; after it,
**171 passed**, and **181 passed** after a focused review that added distinct date-window columns and
boundary tests. One test expectation contained an arithmetic error (an expected cost total) and was
corrected; the code's value was right. Fictional demo: 7 of 11 jobs scheduled, 4 not scheduled with
structured reasons, all independent checks passed. Cost coverage is incomplete by design: one rate is
unknown. Browser verification of the new tab has not been performed or recorded.

## Next implementation milestone (planned)

1. Local-only adapter from the private staging tables to a reviewed schema,
   with tests using synthetic fixtures only.
2. Configuration files for the approved rules once confirmed.
3. Deduplicated completed-service event ledger.
4. Cadence-window evaluation and a simple daily-coverage baseline,
   followed by the ML comparison described in the proposal.
