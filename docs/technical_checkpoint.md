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

## Next implementation milestone (planned)

1. Local-only adapter from the private staging tables to a reviewed schema,
   with tests using synthetic fixtures only.
2. Configuration files for the approved rules once confirmed.
3. Deduplicated completed-service event ledger.
4. Cadence-window evaluation and a simple daily-coverage baseline,
   followed by the ML comparison described in the proposal.
