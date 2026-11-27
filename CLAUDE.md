# Working rules for AI assistants in this repository

AgriFlight AI capstone (G. Maathangi, 268469P). Public GitHub repository.

## Preserve working code
- Inspect before changing. Do not rewrite or replace working modules,
  reinitialise the repository, or change the remote.
- Keep processing logic in `src/agriflight/`; `app/app.py` only presents results.
- Leave unrelated user changes (including pre-staged files) untouched.

## Keep company data private
- Never commit raw workbooks, the private dataset package
  (`AgriFlight_Dataset_v0_1_PRIVATE.zip`), its extracted contents, exports,
  real-record screenshots or anything with real farm/client/pilot names,
  coordinates or costs.
- Only `data/sample/demo_operations.csv` (synthetic, `data_origin = synthetic_demo`)
  is publishable. New demo data must be written from scratch, not derived from real rows.
- `.gitignore` does not protect already-tracked files: check `git status`,
  `git ls-files` and `git diff --cached` before every commit. Stage explicit paths.

## Private operational dataset (milestone 2)
- Read it in place via `AGRIFLIGHT_DATA_DIR`; never copy, move or edit it, and
  never hardcode a local path in committed files.
- Synthetic mode stays the default; private mode must never fall back to
  synthetic data silently.
- Use only the supplied anonymous labels and IDs; never split opaque IDs; do
  not load the restricted identity/location package.
- Tests use fictional fixtures (`tests/operational_fixtures.py`), never real rows.
- Budget: one cost per fuel trip, no allocation to linked farms, rollups never
  added to detail, actual-recorded kept separate, missing never zero.
- Do not name tracked files with "private", and do not name packages `models/` (the `.gitignore`
  would hide them). Check `git status --ignored` after adding new folders.
- EDA outputs go only to `..\Analysis_Private\...` via `scripts/run_eda.py`; never into the repository.
- Do not fit or report any model on operational data unless verified, eligible targets exist.

## Scheduling baseline (milestone 4)
- Capacity comes only from declared scenario assumptions; no ML, no 500 ha/day default, no
  productivity from pilot scores. Missing travel is no route (never zero); missing availability
  is unavailable; blank cost rates are unknown (never zero).
- Planning due dates must be explicit approved inputs - never derived from
  `last_recorded_capture_date`. Do not change `scheduler_ready` flags in the dataset.
- Real scenarios and their outputs stay outside Git and outside the dataset package.
- Results are drafts, not dispatch authorisation; no optimisation superiority is claimed.

## Work in reviewed increments (future workflow)
- No automatic staging, committing or pushing. Finish, test and report; then wait for the
  student's explicit approval of that specific change set.
- Before asking for approval, show the exact proposed file list and the full commit message
  (including the author/committer that will be recorded).
- Do NOT add a "Co-Authored-By: Claude ..." trailer to future commits. If a commit cannot be
  created without it, do not commit: give the student exact PowerShell commands instead
  (explicit paths, `git commit --only`, `Data.ipynb` and private data excluded).
- Stage explicit paths only (never `git add .` / `-A`); keep `Data.ipynb` staged and excluded.
- Record AI work and student actions separately in `docs/ai_assistance_log.md`; never record
  student review unless stated; never remove earlier records of AI assistance.

## Test before committing
- `python -m pytest` must pass before any commit.
- Add or update tests with every behaviour change.
- Never force-push, rewrite history or backdate commits.

## Do not invent
- No invented business rules, labels, metrics, model results, cost savings or
  scheduling improvements.
- Planned visits, capture observations, trial visits and completed services
  are different things; do not merge or relabel them.
- The 30-day +/-5-day cadence is recorded policy only; do not apply it to real
  records until the service periods, anchor date and completion rule are confirmed.
- `monitoring_interval_days` from the earlier prepared dataset is elapsed days,
  not a contractual interval; do not use it as a target.
- Blank does not mean missed, cancelled or zero.
