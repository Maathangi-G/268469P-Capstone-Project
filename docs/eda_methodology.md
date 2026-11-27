# EDA, coverage-target feasibility and baseline (milestone 3)

This document describes **methods and limitations only**. Results computed
from the private dataset are written to a private folder outside this
repository and are not published here.

## Reproduce

From the repository root, with the virtual environment active:

```powershell
$env:AGRIFLIGHT_DATA_DIR = (Resolve-Path "..\Dataset\AgriFlight_Integrated_v0_2").Path
python scripts/run_eda.py
```

- Reads the package in place through the existing operational loader and validation. Nothing in the package is modified.
- Writes CSV tables, two HTML charts, `summary.md` and `run_metadata.json` to `..\Analysis_Private\eda_v0_1` (override with `--output-dir`).
- The output folder is refused if it is inside the application repository, inside the dataset package, or inside any Git repository.
- `run_metadata.json` records the run time, code commit (and whether there were uncommitted changes), Python/pandas versions, package schema version, manifest-hash check and loaded table sizes.
- No network access, credentials or restricted identity package are used.
- The same analyses appear in the app: *Private operational dataset -> EDA & coverage readiness*. The app view never writes files.

## Conventions

| Aspect | Rule |
| --- | --- |
| Unit | Source observation rows, unless stated. Never equated with unique flights, services or pilot-days. |
| Layers | `main_monthly`, `older_archive` and `annual_cycles` are analysed separately. `main_monthly` is the default. They are never concatenated. |
| Date basis | `recorded_actual_date` for observations; `recorded_date` as supplied for the overlap review. |
| Missing history | Not interpreted as onboarding, inactivity or missed visits. |

## A. Completeness and observation history

- For each layer: missing values for identifiers, dates, assignments (person and equipment references) and targets. Non-blank IDs that do not exist in the reference table are counted as unknown references.
- Undated and unmapped rows (no `operation_unit_id`, no `division_id`) are counted separately per layer.
- For each operation unit within one layer: source rows, dated rows, distinct recorded dates, same-date repeat rows, first and last recorded date, and months with records. Rows without an operation unit are excluded from this table and counted in the unmapped table.

## B. Gaps between recorded capture dates

- These are computed within **one layer and one `operation_unit_id`**: the number of days between consecutive **distinct** valid recorded dates.
- When several rows share a unit and date, that date counts once **for this calculation only**. All contributing observation IDs are listed on each gap row, and no source row is removed.
- Units with a single distinct date have no calculable gap.
- The results are labelled *gaps between recorded capture dates*. They are not verified monitoring-cycle intervals. They are not classified as late or on time, and a short gap is not taken as evidence of a separate completed service.
- Length bands are neutral day ranges, not cadence categories.

## C. Area evidence

- Availability is reported per `record_grain`, with the number of records per area type, identity links, unresolved links and effective dates.
- Distributions (count, minimum, median, maximum) are given per area type and grain, plus by crop and maturity.
- Tracker imaging area (`operation_units`), boundary area, farm total area and contract area are separate area types.
- Areas are **never summed** across rows. Field records and their parent summaries would double count.
- Areas are snapshots without effective dates, not historical daily productivity. Identity and area mappings are shown as supplied, never approved.

## D. Source overlap

- The supplied `observation_overlap_review` is summarised by layer combination and resolution.
- A group counts as a confirmed duplicate only if its resolution explicitly says so. Every other group is a **candidate overlap**.
- No source precedence is chosen.

## Coverage-target feasibility

Each candidate hectare column is assessed from the files at run time. Four meanings are kept distinct:

| Category | Meaning |
| --- | --- |
| Observed completed workload | Work recorded as done. A small completed job does not reveal maximum daily capacity. |
| Estimated achievable capacity | No such source exists in the package. |
| Planned work | What a plan intended. |
| Static farm area | Snapshot area, not daily output. |

A record is **eligible** as a model target only if all of the following hold:

- it is observed workload;
- its value is numeric, finite and non-negative;
- an explicit verification flag is True;
- any supplied eligibility flag is True;
- it has a valid date.

A verified zero is eligible. A missing value is never treated as zero. Eligibility flags in the package are read, never changed.

Each source reports:

- records;
- non-missing numeric values;
- verified measured values;
- eligible records;
- the date coverage of eligible records and their distinct dates;
- non-exclusive exclusion-reason counts.

When no observed-workload source has eligible records, the status is:

> Coverage-model training blocked: no verified daily-hectare targets in the inspected integrated package.

This statement covers the inspected package only. It is not a conclusion about every company source.

A feature-availability review classifies the candidate inputs as known when preparing a schedule, known only after work happens, or of uncertain timing/provenance. This classification is AI-proposed and **provisional**; it has not been validated. Future actual weather, realised outcomes and later revisions must not be used as if they were known at scheduling time.

## Historical-mean baseline

`agriflight.baselines.HistoricalMeanBaseline` predicts the mean of verified training targets of **one** named grain.

It rejects, with an explanation:

- empty input;
- missing columns;
- mixed grains;
- records not explicitly verified;
- missing, non-numeric, non-finite or negative targets.

`chronological_split` keeps evaluation-period outcomes out of fitting.

**Real-data status:** Implemented and tested; not fitted or evaluated on operational targets. Any metrics in the tests come from fictional fixtures and are not company-model performance.

## Status by kind of evidence

| | |
| --- | --- |
| Implemented | EDA functions (A-D), the feasibility report, the feature-availability review, the baseline, the reproduction script and the app view. |
| Executed on real records | EDA A-D and the feasibility report, through the script and a headless app run. Results are private. |
| Tested only with fictional fixtures | Gap and repeat handling, area separation, overlap status, eligibility rules (including verified zero, invalid and non-finite values) and all baseline behaviour. |
| Blocked | Coverage-model training and evaluation, until verified daily-hectare targets exist. |

## Limitations

- History and gaps are per `operation_unit_id`. Layers whose rows are mostly linked by division rather than unit therefore contribute few unit-level rows; see the private undated/unmapped table.
- Recorded dates come from trackers that overlap. Gaps describe recording patterns, not service performance.
- The feature-availability classification is a review aid, not a validated leakage audit.
- The HTML charts load the Vega JavaScript libraries from a public CDN when opened. The data stays embedded in the local file.
