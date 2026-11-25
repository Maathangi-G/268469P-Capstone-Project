# AI-assistance and decision log

This log records how an AI coding assistant (Claude, model `claude-opus-5-5`,
running in Claude Code in VS Code) was used in this capstone. It separates:

- **AI-generated**: code, data or text written by the assistant.
- **AI decision**: a design choice the assistant made on its own judgement
  (not specified by the student). These need the student's review.
- **Student input**: instructions, requirements or business context the
  student provided.
- **Student action**: something the student did themselves: reviewed, changed,
  ran, verified or approved. Recorded **only when the student reports it**.

The assistant adds AI entries. Student-action entries are written or confirmed
by the student. Commits made with AI help carry a `Co-Authored-By: Claude`
trailer. Published history is not rewritten to remove it.

---

## 2026-11-24 - Session 1: foundation milestone (v0.1.0)

### Student input
- Requested a working "AgriFlight AI - Data Readiness Dashboard" with a synthetic
  dataset, loading and validation modules, a Streamlit dashboard, tests, docs,
  and commits pushed to the existing GitHub repository. Supplied the business
  context: varying onboarding dates, a 30-day +/-5-day target with unconfirmed
  scope/anchor/completion rules, distinct record kinds, and the
  `monitoring_interval_days` caveat. Specified what must not be done (no model,
  labels or claimed improvements).
- That brief explicitly authorised committing and pushing.

### AI-generated
- All files in commits `0d1edb7`, `ab9c9d5`, `790dbeb` and `b1b94cb`: package code
  (`src/agriflight/`), dashboard (`app/app.py`), synthetic dataset and its README,
  tests (45), `README.md`, `CLAUDE.md`, `docs/architecture.md`,
  `docs/data_contract.md`, `docs/technical_checkpoint.md`, `.gitignore`,
  `pyproject.toml`, `.streamlit/config.toml`.
- The synthetic rows were written from scratch by the assistant. They were not
  derived from company records.
- Commit messages, and the commit and push themselves (under the student's
  configured Git identity, with the Co-Authored-By trailer).

### AI decisions (not specified by the student; pending student review)
| # | Decision | Alternatives considered |
| --- | --- | --- |
| D1 | Used +/-5 days (student brief) and documented that the submitted proposal said approximately +/-3. | Use +/-3 from the proposal; ask first. |
| D2 | Demo-schema rule: `planned_visit` requires `planned_date`; `capture_observation` requires `actual_date`; `trial_visit` requires neither. | Make all dates optional; require at least one date on every row. |
| D3 | `client_id` value optional (e.g. a prospective trial client). | Make it required. |
| D4 | `area_ha` may be 0; only negative or non-numeric values are errors. | Treat 0 as a warning. |
| D5 | Dates accepted only as strict `YYYY-MM-DD`. Other formats (e.g. `01/02/2026`) are invalid, not guessed. | Lenient parsing (ambiguous day/month). |
| D6 | `data_origin` other than `synthetic_demo` is a warning (privacy reminder), not an error. | Reject the file; ignore the field. |
| D7 | Added `schema.py` (single schema definition), `project_status.py` and a headless app smoke test beyond the suggested structure. | Keep rules inside the loader/validator; no app test. |
| D8 | Streamlit configured as headless, localhost-only, with usage statistics off. | Streamlit defaults (listens on the LAN, auto-opens a browser). |
| D9 | Grouped the work into 4 commits (the fourth for a Windows install note). | 3 commits as suggested in the brief. |

### AI verification (performed by the assistant, not the student)
- `python -m pytest`: 45 passed (Windows 11, Python 3.14.7).
- Server startup health check `ok` on 127.0.0.1; not reachable on the LAN address.
- Fresh clone following the README: install, 45 passed, startup OK. A first
  attempt in a long folder path failed (Windows path limit).
- Scanned the files to be committed for confidential terms. Confirmed that the
  private ZIP and raw data were not tracked. Verified the remote `main` at `b1b94cb`.

### Incidents
- A non-headless Streamlit launch auto-installed a "developing-with-streamlit"
  skill into the user profile (`~/.agents/skills`, `~/.claude/skills`). It was
  outside the repository and was reported to the student. Not removed: awaiting
  the student's decision. The config was switched to headless afterwards.

### Student actions
- _None recorded yet._ Manual browser testing of the dashboard and review of
  decisions D1-D9 are outstanding.

---

## 2026-11-25 - Session 2: working agreement

### Student input
- From now on: work in small, reviewable increments. Before committing or pushing,
  explain the logic, alternatives, tests and limitations. Let the student inspect
  and run the changes, then wait for approval. Maintain this log accurately.
  Do not rewrite history to conceal AI involvement.

### AI-generated
- This log file (`docs/ai_assistance_log.md`): uncommitted, awaiting student review.

### Student actions
- _None recorded yet._

---

## 2026-11-25 - Session 3: read-only requirements review

### Student input
- Requested a read-only review of `Agri-Flight_AI_268469P.pdf` against the code, and named that file as
  the submitted proposal.

### AI work
- First search: the named file was not yet in the workspace. The assistant reported this and did not
  guess between three different drafts. It also corrected itself: in Session 1 it had called a draft
  "the submitted proposal" without confirmation.
- After the file was added, the assistant confirmed by SHA-256 that it is byte-identical to the
  draft used in Session 1, then produced the requirements extraction, classification and cadence
  comparison (proposal +/-3 days vs operational +/-5 days, kept separate). No files were changed.

### Student actions
- _None recorded._

---

## 2026-11-25 - Session 4: milestone 2, read-only operational dataset integration

### Student input
- Specified the milestone: explicit data modes, `AGRIFLIGHT_DATA_DIR`, the tables to integrate, the
  four views, budget safeguards, privacy rules, tests and documentation. No commit or push without
  approval.
- Corrected the dataset location to `Capstone_Project/Dataset/AgriFlight_Integrated_v0_2`
  (outside the repository) after the assistant reported that the first suggested path did not exist.
- Stated that the multi-day completion details are unknown.

### AI work (all uncommitted, awaiting student review)
- Inspected the repository (tests before changes: 45 passed) and the package's README, handoff note,
  schema, supplied validation report, manifest, privacy audit and validator script. Profiled column
  types and categories (aggregate output only).
- Re-ran the package's validator in memory, without writing a report: same outcome as the supplied
  report. Verified the manifest hashes. Neither the package nor its reports were modified.
- Wrote `src/agriflight/operational/` (contract, loader, validation, summaries, session),
  `app/operational_views.py`, changes to `app/app.py` and `project_status.py`, fictional test fixtures,
  four new test files, an extended app smoke test, and documentation updates.
- Corrected one of its own test assertions during development (it matched text that legitimately
  appears on the Project Status tab).

### AI decisions (pending student review)
| # | Decision | Alternatives considered |
| --- | --- | --- |
| D10 | The mode selector is a sidebar selectbox, with synthetic as the default. | A radio button (would have changed the existing test's widget order); auto-switching when the variable is set (rejected by the brief). |
| D11 | New paths are named "operational", not "private". | Naming them "private" (the existing `.gitignore` pattern `*private*` would hide them from Git). |
| D12 | Cache: in-memory `session_state`, keyed on package path plus file size/mtime, cleared in synthetic mode. | `st.cache_data` (shared across sessions); no cache (about 1 s reload per interaction). |
| D13 | Discrepancy threshold LKR 1, matching the package's own reconciliation tolerance. | Any non-zero difference (would count 1e-06 rounding noise). |
| D14 | The monthly time series shows a continuous range including zero months, with a caption saying zero is not a missed visit. | Showing only months that have records. |
| D15 | Person tokens are hidden in observation, fuel-trip and accommodation views. | Showing them (not needed for this milestone). |
| D16 | The app does not import or run the package's own scripts. | Running `validate_dataset.py` from the app. |

### AI verification (performed by the assistant, not the student)
- Test suite after changes: 94 passed.
- Headless app run against the real package: all private-mode tabs and the selectors tested rendered
  without exception.
- Server startup with the variable set: health check `ok`, localhost only.
- Package integrity after the runs: manifest hashes unchanged, no files added.

### Student actions
- 2026-11-25: the student reported completing **manual browser verification** of the private dataset
  integration. The assistant did not observe this verification; it is recorded as the student's own statement.
- Review of decisions D1-D16 and approval to commit: not yet given.

### Pre-commit verification (assistant, 2026-11-25, at the student's request)
- Boolean parsing: `True`/`False` parse correctly. Blank and whitespace-only become unknown. Other text
  (`true`, `FALSE`, `1`, `0`, `yes`, `nan`) becomes unknown and is reported as `invalid_boolean`.
  Surrounding whitespace is trimmed (`" True "` -> True). All 11 boolean columns in the real package
  contain only the exact text `True`/`False`.
- LKR 1 threshold reviewed against the real data. Per-record arithmetic: every non-zero
  reported-minus-recomputed difference is below LKR 0.00001 (floating-point noise; within tolerance,
  not an exact match). Separately, the package's supplied subtotal reconciliation contains one
  subtotal mismatch, well above LKR 1. It is a preserved source issue, so not all subtotals agree.
  On the current data, any threshold between 0.00001 and 100 gives the same per-record counts.
- Test suite: 94 passed.
- Privacy scan of the 38 proposed public files against every distinct value in the 44 package CSVs:
  no real opaque IDs, no absolute paths, emails, coordinates or company names. The matches were schema
  vocabulary (table names, category codes reused in fictional fixtures), common calendar dates and
  round numbers, and the anonymous label format example `Farm 001`.
- Git: no private dataset file is tracked or appears anywhere in the commit history. A copy of the
  package placed inside the repository would be ignored. `Data.ipynb` remains staged and excluded
  from the proposed commit.

### Student decisions and approval (2026-11-25, as stated by the student)
- **Boolean parsing:** keep whitespace trimming (`" True "` / `" False "` parse after trimming). Raw
  values are preserved, blank stays unknown, and unsupported non-blank values still produce
  `invalid_boolean`.
- **Budget tolerance (D13):** keep LKR 1 as the discrepancy-reporting tolerance, with the documented
  boundary behaviour. Show the full reported value, recomputed value and difference. A difference within
  tolerance must not be described as an exact match. Missing amounts stay unknown.
- **Label example:** keep the generic `Farm 001` example; no real records or identifying information
  in examples.
- **Approval:** to commit and push the 24 listed integration files to `main`, subject to final checks.
- Not stated by the student: individual review of the other decisions (D1-D12, D14-D16), or any code
  review or browser check beyond the browser verification reported above.

### Changes made after approval (assistant, at the student's request)
- Clarified the budget wording in `app/operational_views.py` and `docs/operational_dataset.md`:
  per-record arithmetic differences are kept separate from the package's subtotal reconciliation, and
  not all subtotals agree. Documented the accepted boolean trimming behaviour in
  `docs/operational_dataset.md` and the loader docstring. No behaviour changes.
