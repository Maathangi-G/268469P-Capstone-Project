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
