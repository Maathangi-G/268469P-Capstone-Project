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
- Review of decisions D1-D16 and approval to commit: not yet given at that point (approval recorded below).

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
- Committed as `1b0e9d9` (24 files, scoped `--only` commit; `Data.ipynb` left staged) and pushed to
  `origin/main` under the approval above.

---

## 2026-11-25 - Session 5: milestone 3, EDA, coverage feasibility and guarded baseline

### Student input
- Specified the milestone: reproducible EDA (completeness, history, gaps between recorded capture dates, area
  evidence, overlap), a coverage-target feasibility report, a feature-availability review, a guarded
  historical-mean baseline, one app view plus a script, private outputs only in `..\Analysis_Private\eda_v0_1`,
  fictional-fixture tests and documentation. No staging, commit or push before review.
- Restated that the multi-day allocation details are unknown.

### AI work (uncommitted, awaiting student review)
- Inspected the repository (tests before changes: 94 passed) and profiled the six additional tables
  (aggregate output only). Recalculated the target findings from the files rather than hardcoding them.
- Extended the existing contract and validation: an "analysis" role for the new tables, a "template" role
  in which zero rows are valid, extra foreign keys, and a check of the overlap review's division-or-unit
  reference. No second loader was written.
- Wrote `operational/eda.py`, `operational/coverage.py`, `operational/eda_report.py`,
  `baselines/baseline.py`, `scripts/run_eda.py`, the *EDA & coverage readiness* tab, fixture extensions,
  five new test files and documentation (`docs/eda_methodology.md` and updates).
- Ran the script on the real package. 26 private files were written to `..\Analysis_Private\eda_v0_1`.
  The package's manifest hashes are unchanged.
- Defects found and fixed by the assistant: a nullable-dtype error in the finiteness check; a test that
  mixed exclusion reasons across sources; and the new `models/` package, which was hidden by the
  repository's `models/` ignore rule (renamed to `baselines/`).

### AI decisions (pending student review)
| # | Decision | Alternatives considered |
| --- | --- | --- |
| D17 | Eligibility requires observed category + finite non-negative value + explicit verified flag + any eligibility flag + valid date; a verified zero is eligible. | Accepting numeric values without a verification flag (would treat unverified values as labels). |
| D18 | Sources without a verification column (e.g. trial extent) are never eligible. | Treating trial extent as observed daily coverage (a trial job is not daily capacity). |
| D19 | Gaps are per layer and operation unit, using distinct dates, with neutral length bands up to 180+ days. | Per division (identity links are not approved); bands around 30 days (would suggest cadence labels). |
| D20 | Only an explicit `confirmed_duplicate` resolution counts as a confirmed duplicate. | Inferring confirmation from other resolution text. |
| D21 | The feature-availability classification (three classes) is an AI-proposed review aid, **provisional** and not validated. | No classification. |
| D22 | The baseline is not fitted on real data even if eligible records appear later; fitting needs a separate approved split. | Auto-fitting whenever eligible rows exist. |
| D23 | The app view never writes files; only the script exports, to a validated folder outside any Git repository. | An export button in the app. |
| D24 | Charts are exported as Altair HTML (already installed with Streamlit). | Adding matplotlib as a new dependency. |

### AI verification (performed by the assistant, not the student)
- Test suite after changes: 131 passed.
- Headless app run on the real package: the new tab and all layer selections rendered without exception.
  The blocked status and the baseline status were displayed.
- Server startup: health `ok`, localhost only.

### Student actions
- 2026-11-27: the student **approved committing and pushing** this milestone, subject to final checks
  (stated by the student).
- Not stated by the student: review of the new code, manual browser checks of the new tab, or individual
  review or validation of decisions D17-D24. D21 remains provisional.

### Status at commit (as recorded by the assistant)
- EDA was executed on operational records; the results are private, in `..\Analysis_Private\eda_v0_1`.
- Coverage-target eligibility is zero in the inspected package.
- `HistoricalMeanBaseline` is implemented and tested with fictional fixtures only.
- It has not been fitted or evaluated on operational targets.
- No real predictive-performance results are available.
- Correction: the milestone changes 26 files (15 modified, 11 new), not 27 as first reported by the assistant.
- Committed as `244ecac` (26 files, scoped `--only` commit with a `Co-Authored-By: Claude Opus 5.5` trailer)
  and pushed to `origin/main` under the approval above.

---

## 2026-11-27 - Session 6: milestone 4, rule-based scheduling baseline

### Student input
- Specified the milestone: a deterministic rule-based scheduling baseline with explicit input contracts, a
  fictional scenario, cost estimates without double counting, an independent checker, one app view and a
  script. Kept separate from the coverage baseline. No staging, commit or push before review.
- New standing instructions for future work: no automatic staging, committing or pushing; **no
  `Co-Authored-By: Claude` trailer on future commits**; show the proposed file list and full commit
  message before approval; keep this log truthful.
- Asked the assistant to merge `{"attribution": {"commit": ""}}` into the repository's untracked
  `.claude/settings.local.json`.

### AI work (uncommitted, awaiting student review)
- Inspected the repository (tests before changes: 131 passed) and the existing private input templates
  (`pilot_availability_template` and `physical_vehicle_template`, both empty; not used as inputs).
- Wrote `src/agriflight/scheduling/` (contracts, rule_baseline, costs, checker, outputs),
  `app/scheduling_view.py`, a new synthetic-mode tab in `app/app.py`, `scripts/run_schedule.py`, the
  fictional `examples/scheduling_demo/` scenario and its generator, two test files plus a fixture builder,
  and documentation (`docs/scheduling_baseline.md` and updates). The private dataset was not used.
- Claude Code settings: version 2.1.332 supports `attribution.commit` (its bundled schema says an empty
  string hides attribution). No managed policy file exists. Created the repository's
  `.claude/settings.local.json` containing only that setting (no earlier file existed) and added it to
  `.gitignore`. Whether it is loaded could not be verified inside this session, which was opened at the
  parent workspace folder.
- Corrected one of its own test expectations (an arithmetic error in an expected cost total).

### AI decisions (pending student review)
| # | Decision | Alternatives considered |
| --- | --- | --- |
| D25 | Bundles are processed in bundle_id order each day, and a resource used by an earlier bundle blocks later bundles that day. | Rejecting overlapping bundles at input (would forbid valid alternate team compositions). |
| D26 | Candidate order: earliest planning due date, then travel minutes from the current location, then job_id. | Nearest-neighbour first (ignores due dates). |
| D27 | Break rule: one break once the day exceeds the threshold, placed after the first job ending past it (else after the last job); never mid-job. | Fixed clock-time break; break inside a job. |
| D28 | A missing availability row means "not available". | Treating missing as available (would invent availability). |
| D29 | Cost levels: trip and vehicle-day once per bundle-day route; km over all legs; person-day rates times pilot count; fuel not added when an all-inclusive rate applies. | Per-job allocation of vehicle-day costs. |
| D30 | Due-date deviation is reported under both ±5 and ±3; the preferred window is reported separately and never excludes a job. | Treating ±5 as a hard window. |
| D31 | The demo scenario lives in `examples/` (not `data/sample/`, which `.gitignore` restricts). | Adding `.gitignore` exceptions. |

### AI verification (performed by the assistant, not the student)
- Test suite after changes: 171 passed.
- Fictional demo run: 7 of 11 jobs scheduled; all independent checks passed.

### Focused review requested by the student (2026-11-27)
- The student asked for clarification of JOB_09's date windows, the cost label and the resource policy,
  with no new features.
- Finding (assistant): the calculations were correct, but the assistant's report wording was ambiguous.
  "2 days outside its preferred window" referred to the job's own supplied window; "within ±5 but not ±3"
  referred to the windows around the due date.
- Changes (assistant), all to labels and coverage:
  - The assignments output now has distinct columns: the signed offset from the due date; the operational
    ±5 and proposal ±3 windows with deviation = max(0, |offset| − tolerance); and the job's own preferred
    window (signed deviation, never replaced by a formula). The redundant true/false columns were removed.
  - The resource-reservation rule was added to the assumptions output.
  - View and documentation wording was updated: known estimated cost is not a complete budget; whole-day
    resource reservation is a conservative version-1 restriction with no within-day handover.
  - Tests were added for window boundaries (early and late at ±3, ±5 and beyond), a JOB_09 regression
    check, a signed custom-window check, and an explicit zero-cost rate versus a missing rate.
- Resource policy confirmed from the code: resources are reserved for the whole day only when their
  bundle actually receives a job; bundles are taken in bundle_id order. Handovers were not implemented.
- Test suite after these changes: 181 passed.

### Student actions
- 2026-11-27: the student **approved committing and pushing** this milestone, limited to the 34 listed
  files (stated by the student).
- Not stated by the student: review of the implementation code, manual browser checks of the new tab, or
  individual review of decisions D25-D31.

### Limitations at commit (as recorded by the assistant)
- Demonstrated on a fictional scenario only; not validated on company operations.
- Capacity and cost rates are declared assumptions, not ML predictions.
- The known estimated cost is incomplete where rates are missing (the allowance rate in the demo).
- Version 1: daily return to depot, whole-day resource reservation, no handovers, no overnight stays,
  no job splitting.
- Commit message written without a Claude co-author trailer, per the student's instruction.
- Committed as `4582e3a` (34 files, scoped `--only` commit; recorded message verified to contain no
  co-author trailer) and pushed to `origin/main`.

---

## 2026-11-27 - Session 7: milestone 5, CP-SAT optimizer and baseline comparison

### Student input
- Specified the milestone: an OR-Tools CP-SAT optimizer under the same operating rules as the rule
  baseline; a lexicographic objective (jobs, then absolute preferred-window days, then travel); honest
  solver-status handling; fictional comparison scenarios defined before evaluation; a comparison view
  and script; tests and documentation. No staging, commit or push.

### AI work (uncommitted, awaiting student review)
- Inspected the repository (tests before changes: 181 passed).
- Environment: checked compatibility first (Streamlit accepts protobuf `>=5.26.1,<8`) and saved a
  pip-freeze snapshot. Then installed `ortools==9.15.6755` into the project virtual environment, which
  added absl-py and immutabledict and downgraded protobuf from 7.36.2 to 6.33.6. `pip check` is clean.
  Read the CP-SAT documentation (statuses, `add_circuit`, `num_workers` / `random_seed`).
- Wrote `scheduling/optimizer.py` and `scheduling/comparison.py`, a `summarize_result` refactor in
  `outputs.py`, a known-zero cost for empty schedules in `costs.py`, `scripts/compare_schedulers.py`,
  a comparison section in `app/scheduling_view.py`, six fictional scenarios with their generator and a
  pre-evaluation README, two test files, and documentation.
- Results: every optimizer stage was OPTIMAL in all seven scenarios, and every itinerary passed the
  checker. One recorded scenario expectation (c3) did not match the observed result; it is reported,
  and the scenario was left unchanged.
- Corrections during development: two test doubles that used an unsolved CP-SAT solver object.

### AI decisions (pending student review)
| # | Decision | Alternatives considered |
| --- | --- | --- |
| D32 | Exact CP-SAT model: one circuit per available team-day, with no candidate-route generation. | Enumerating candidate routes (risks a restricted optimum). |
| D33 | Integer seconds with durations rounded up; results rebuilt with the baseline's exact minute timeline and checked. | Integer minutes (coarser); floating-point timing (unsupported by CP-SAT). |
| D34 | Three sequential solves, each fixing the previous objective (or bounding it, when that stage is only feasible). | A weighted single objective with large constants. |
| D35 | The total time budget is split evenly across the remaining stages; seed 42 and 1 worker by default. | Separate per-stage budgets. |
| D36 | Unscheduled jobs get either structural reasons or NOT_SELECTED_BY_OPTIMIZER, stating whether a solo route fits. | Reusing the baseline's greedy reason codes (inaccurate for an optimizer). |
| D37 | Fallback off by default; when enabled it is explicitly labelled `rule_baseline_fallback`. | Silent fallback. |
| D38 | Optional dependency extra `optimizer = ["ortools>=9.15,<9.16"]`; optimizer tests skip when OR-Tools is absent. | A hard dependency for every user. |
| D39 | An empty schedule has a known cost of 0, not an unknown cost. | Leaving it unknown. |

### AI verification (performed by the assistant, not the student)
- Test suite after changes: 207 passed. With OR-Tools simulated as absent: 181 passed, 2 modules skipped.
- Headless app check of the comparison section: it solves only when the button is pressed, and stale
  results are hidden after the scenario or settings change.

### Focused review requested by the student (2026-11-27)
- The student asked about time rounding and comparison validity, the shared solver budget and incumbent
  handling, result wording (including the c3 cost wording), the environment, and the file count. No new
  features.
- Findings (assistant):
  - The integer-second conversion changes 0 of 280 audited durations across the seven scenarios.
  - With its assignments and visit orders fixed as hard constraints (not hints), the baseline's solution
    is feasible in the optimizer's integer model in all seven scenarios. The optimizer's objective is
    lexicographically no worse in each.
  - `--time-limit` is one shared budget per scenario, split across the remaining stages.
  - A later-stage UNKNOWN keeps the previous incumbent (existing test).
  - Validated empty schedule, no solution and labelled fallback are distinct (existing tests).
- Changes (assistant):
  - Added `scheduling/equivalence.py` (rounding audit and baseline-in-model check) and
    `tests/test_scheduling_equivalence.py`, including a fractional-duration boundary regression showing
    that rounding is conservative and can accumulate.
  - The comparison script now reports the audit, the check and the solver times.
  - Documentation corrected: rounding accumulates; the "no worse" claim is now conditional on
    baseline feasibility and consistent measures; the c3 cost wording (+71%, not double); same-set and
    different-set results in separate tables; no success-rate interpretation; the reproducible install
    constraint.
- Correction: the assistant earlier reported "12 modified, 67 new" files. The actual working tree had
  11 modified and 68 new before this review.
- Test suite after these changes: 216 passed, 0 failed, 0 skipped. `pip check` clean; no dependency
  changes in this review.

### Student actions
- The student reported completing a **manual browser check** of private mode and the optimizer comparison
  section (stated by the student; not observed by the assistant). The date was not specified in the
  approval message.
- 2026-11-27: the student **approved committing and pushing** this milestone, limited to the 81 listed
  files (11 modified, 70 new) (stated by the student).
- Not stated by the student: review of the optimizer code, or approval of decisions D32-D39 as a whole.

### Limitations at commit (as recorded by the assistant)
- Fictional scenarios only; not validated on company operations; no company-level improvement claimed.
- Integer-second rounding is conservative and can exclude schedules that fit exactly at a time limit
  (none of the current scenarios is affected).
- Version 1 rules: no overnight stays, multi-day jobs, handovers or job splitting.
- Commit message written without a Claude co-author trailer, per the student's instruction.
