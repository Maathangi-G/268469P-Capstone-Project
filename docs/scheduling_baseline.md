# Rule-based scheduling baseline (milestone 4, version 1)

A deterministic, rule-based scheduler that turns **explicit planning inputs**
into draft daily itineraries and estimated costs. It is the reference against
which a later optimisation method (OR-Tools) will be compared. It is **not**
an optimiser, uses **no** machine learning, and its outputs are **draft
planning results, not dispatch authorisation**. No weather, airspace or
operational safety clearance is implied.

This is a different baseline from `HistoricalMeanBaseline`, the
coverage-prediction baseline, which remains unfitted on operational targets.
The scheduler's capacity comes only from declared scenario assumptions
(`capacity_mode = declared_assumption`).

## Run

```powershell
python scripts/run_schedule.py                       # fictional demo; prints a summary
python scripts/run_schedule.py --output-dir ..\Analysis_Private\scheduling_demo
streamlit run app/app.py                             # Synthetic mode -> "Scheduling baseline" tab
```

A non-synthetic (approved private) scenario must be stored **outside** the
repository. Its outputs go to a folder outside any Git repository and outside
the dataset package (default `..\Analysis_Private\scheduling_v0_1`). If inputs
are missing, the script lists them and stops. It never substitutes fictional
resources or capacity values.

## The rule

For each planning day (ascending), for each resource bundle (ascending `bundle_id`):

1. **The bundle operates only if** every pilot, vehicle and equipment item in it has an explicit `available = True` row for that day, and none of them has already been used by another bundle that day. A missing availability row means *not available*.
2. **Starting at the bundle's depot at the working-day start**, repeatedly choose, among unscheduled jobs that are *eligible* and whose addition still gives a *feasible* day route:
   - the job with the **earliest `planning_due_date`**;
   - ties broken by **travel minutes from the current location**, then **`job_id`**.
3. **Stop** when no further job fits. The route returns to the depot. Each job is assigned at most once.

A job is **eligible** for a bundle and day when all of these hold:
- the day is inside the job's hard booking dates and not one of its blocked dates;
- the bundle's vehicle type, equipment types and pilot skills meet the job's requirements;
- a service duration is known: an explicit job duration, or area ÷ the bundle's declared work rate;
- setup plus service fits within one working day.

A day route is **feasible** when all of these hold:
- every leg exists in the directed travel matrix;
- each job's work fits its daily access window (the team waits if it arrives early);
- the break rule is met;
- the return to the depot is no later than the working-day end.

**Break rule:** a day longer than `break_after_minutes` includes one break of `break_minutes`. The break is taken after the first job whose work ends at or after that point; if no job does, it is taken after the last job, before the return leg.

**Hard vs soft:**
- **Hard:** booking dates, blocked dates, access windows, resource availability, no shared physical resource across bundles, compatibility, working limits and return to the depot.
- **Soft:** three date windows, reported in separate columns. None of them ever excludes a job.

| Output column | Window | Deviation |
| --- | --- | --- |
| `offset_from_due_date_days` | none | Signed scheduled date minus planning due date (negative = early). |
| `operational_window_pm5`, `..._deviation_days` | due date ± 5 days | max(0, abs(offset) − 5) |
| `proposal_window_pm3`, `..._deviation_days` | due date ± 3 days | max(0, abs(offset) − 3) |
| `job_preferred_window`, `job_preferred_window_deviation_days` | the job's own supplied window (never replaced by a formula) | Signed days outside (negative = early, positive = late, 0 = inside). |

Example: in the demo, JOB_09 is due 2030-03-02 and scheduled on 2030-03-06 (offset +4).

| Window | Deviation |
| --- | --- |
| Operational ±5 | 0 |
| Proposal ±3 | 1 |
| Job preferred window (2030-02-28 to 2030-03-04) | +2 |

**Resource policy (conservative version-1 restriction):**
- A physical resource (pilot, vehicle or drone/equipment) used by a bundle is **reserved for that whole day**.
- Bundles are considered in `bundle_id` order, so an earlier bundle has priority.
- A bundle that is available but receives no job reserves nothing.
- **Within-day handovers are not supported.** A resource cannot serve one bundle in the morning and another in the afternoon.

## Version-1 limits

- Each team-day starts and ends at its depot. There are no overnight stays and no accommodation.
- No job splitting. Each job must be completed within one day. Larger jobs are reported as `MULTI_DAY_UNSUPPORTED`: *multi-day planning is not supported by this baseline version*, which is **not** a statement about company capability.
- No partial completion is inferred.
- The break is not inserted in the middle of a job.
- Shared resources are reserved per whole day; there are no within-day handovers.
- Greedy and myopic: an early choice can block a later job. Such jobs are reported as `CAPACITY_USED_BY_EARLIER_JOBS`.
- Unscheduled jobs are reported as **"not scheduled by this baseline"**, with structured reasons. This is **not** a proof of infeasibility.

Reason codes: `NO_COMPATIBLE_BUNDLE`, `NO_SERVICE_DURATION`, `MULTI_DAY_UNSUPPORTED`, `OUTSIDE_HARD_DATES`, `MISSING_TRAVEL`, `RESOURCES_UNAVAILABLE`, `ACCESS_WINDOW`, `DOES_NOT_FIT_WORKING_DAY`, `CAPACITY_USED_BY_EARLIER_JOBS`.

## Input contracts

A scenario folder contains `scenario.json` and nine CSV files. Every row carries `provenance`, and most carry `input_status` (`approved` or `assumption`).

| File | Key fields | Rules |
| --- | --- | --- |
| `scenario.json` | `scenario_id`, `data_origin`, `timezone`, horizon, `capacity_mode`, `working_day`, `cadence`, included/excluded constraints and cost categories | `timezone` must be `Asia/Colombo` (local dates and times); `capacity_mode` must be `declared_assumption`. |
| `jobs.csv` | job, division and location IDs; required area **or** explicit service duration; setup; `planning_due_date`; preferred window; hard dates; blocked dates; access window; required vehicle type, equipment type and skills | Planning due dates must be explicitly approved planning inputs. They are **never** derived from `last_recorded_capture_date` or any historical observation. |
| `bundles.csv` | bundle, depot, pilots, vehicle, equipment, declared work rate (ha/h), setup | Explicit team composition. Physical resources may appear in several bundles, but never on the same day. |
| `pilots.csv`, `vehicles.csv`, `equipment.csv` | identity plus skills, vehicle type or equipment type | No pilot scores are used. |
| `availability.csv` | resource type and ID, date, `available` (`True`/`False`) | A missing row means not available. |
| `locations.csv` | location ID, kind, `access_point_verified` | Field centroids are not verified entrances. |
| `travel.csv` | directed from/to, minutes, km, source | Not assumed symmetric. A missing entry means no route, never zero travel. A blank km value leaves the distance cost unknown. |
| `cost_rates.csv` | rate ID, category, `applies_to` (vehicle type or `*`), amount in LKR, `includes_fuel` | A blank amount is an unknown cost, never zero. |

The private package's input templates (`pilot_availability_template`,
`physical_vehicle_template`) are still empty. A real scenario needs those
facts approved and mapped into this contract by a reviewed adapter, which is
planned and not part of this milestone.

## Cost estimation

Costs are calculated per bundle-day route:

| Category | Charged as |
| --- | --- |
| `trip` | once |
| `vehicle_day` | once |
| `distance_km` | km of all legs, including the return |
| `fuel_km` | km of all legs, unless the applicable distance or vehicle-day rate already includes fuel |
| `personnel_person_day` | number of pilots |
| `allowance_person_day` | number of pilots |

- Missing rates are reported as `rate_not_configured`, blank amounts as `rate_unknown`, and unknown distances as `distance_unknown`. Each makes cost coverage incomplete; none is replaced by zero.
- An explicitly supplied `0` rate is different: it is costed as 0 and counts as covered.
- The headline figure is the **known estimated cost**. When coverage is incomplete it is **not a complete operating budget**. In the demo, the known estimate is LKR 135,380 and coverage is incomplete because the allowance rate is blank.
- Categories the scenario excludes are reported as excluded.
- Accommodation is `not_applicable_return_to_base`.
- No historical budget or expense summary is added.
- Every value is an **estimate**, not actual expenditure or realised savings.

## Independent checker

`agriflight.scheduling.checker` re-derives the results from the inputs instead of reusing the scheduler's simulation. It checks:

- unique job assignment;
- resource availability and no shared resource per day;
- route continuity and agreement with the travel matrix;
- time accounting: arrival, wait, setup, service, break, departure and return all sum to the route duration;
- working-day limits and the break rule;
- hard constraints;
- cost arithmetic, with exactly one cost set per bundle-day.

## The fictional demo scenario

`examples/scheduling_demo/` is generated by `build_demo.py`. Everything in it is invented: an abstract coordinate plane, made-up rates and availability. It covers:

- a pilot unavailable on one day;
- a drone shared by two bundles;
- a job that needs a 4WD;
- a job whose travel, work and return exceed the working day;
- a job too large for one day;
- a job with a missing return route;
- a job needing equipment no bundle has;
- a hard booking date outside the preferred window;
- an access window;
- a job with an explicit duration;
- an unknown allowance rate.

## Comparing with OR-Tools later (planned)

The later optimisation method will be compared under identical conditions:

- **Same inputs:** the same scenario folders and input contracts.
- **Same evaluation code:** the same `costs.py` cost function and `checker.py` validity checks.
- **Same measures:** jobs scheduled; jobs not scheduled, by reason; total travel minutes and km; estimated known cost and its coverage; preferred-window and due-date deviations under both tolerances; bundle-days used; runtime.
- **Same constraint set**, declared in `scenario.json`. Any extra constraint used by one method must be added to the shared checker first.
- Results on fictional scenarios demonstrate behaviour only. Any claim about real operations needs approved real scenarios.
