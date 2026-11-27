# CP-SAT scheduling optimizer and baseline comparison (milestone 5)

An OR-Tools CP-SAT model that schedules the same planning inputs as the
deterministic rule-based baseline ([scheduling_baseline.md](scheduling_baseline.md))
under the **same operating rules**. A reproducible comparison runs both methods.

All results described here come from **fictional scenarios**. They show how
the model behaves, not company-level performance. The outputs are draft
plans, not dispatch authorisation. No ML is involved: capacity comes from
declared scenario assumptions. The coverage baseline remains unfitted.

## Environment

| Item | Tested version |
| --- | --- |
| Python | 3.14.7 (project virtual environment) |
| OR-Tools | 9.15.6755 (CP-SAT Python API) |
| protobuf | 6.33.6 (required by OR-Tools `<6.34`; it was 7.36.2 before installation; Streamlit accepts `>=5.26.1,<8`) |

Install into the project virtual environment with:

```powershell
python -m pip install -e ".[app,dev,optimizer]"
# or, to reproduce the exact tested solver environment without freezing unrelated packages:
python -m pip install "ortools==9.15.6755" "protobuf>=6.33.1,<6.34"
python -m pip check
```

Notes:

- The `optimizer` extra is `ortools>=9.15,<9.16`.
- OR-Tools 9.15 itself requires `protobuf>=6.33.1,<6.34`. Installing it therefore replaces a newer protobuf 7.x, which Streamlit (`protobuf>=5.26.1,<8`) also accepts. Without OR-Tools:

- the rest of the app and its tests still run;
- the optimizer tests are skipped;
- the comparison script and the app's comparison section say that OR-Tools is missing.

## Run

```powershell
python scripts/compare_schedulers.py                      # all fictional scenarios
python scripts/compare_schedulers.py --time-limit 20 --seed 42 --workers 1
python scripts/compare_schedulers.py --output-dir ..\Analysis_Private\scheduler_comparison
streamlit run app/app.py   # Synthetic mode -> Scheduling baseline -> "Run optimizer comparison"
```

The app solves **only when the button is pressed**. A stored result is shown
only while the scenario's file hash and the solver settings are unchanged.

## Why CP-SAT

The problem is small but combinatorial. It combines yes/no choices (which
team-day does which job), sequencing (visit order on directed travel),
time windows and a break rule, and resource exclusivity across teams.

CP-SAT handles all of these directly:

- Boolean and integer variables;
- conditional constraints (`only_enforce_if`);
- a circuit constraint for connected tours;
- proofs of optimality when the search completes.

It runs locally, needs no licence, and accepts a fixed seed and a single
worker for reproducible experiments.

## The model in plain English

**Team-days.** A team-day is one bundle on one day where every pilot, vehicle
and drone in the bundle is available. Team-days with no eligible job are
left out. Eligibility uses the baseline's shared rules: hard booking dates,
blocked dates, vehicle/equipment/skill compatibility, a known duration, and
work that fits within one day.

**Routes.** Each team-day has a small directed graph with the depot and its
eligible jobs.

- An arc exists **only** where the travel matrix has an entry. A missing edge is never created, so it can never become zero travel.
- A circuit constraint forces the selected arcs into **one connected tour** depot → jobs → depot, or skips the team-day entirely.
- There are no route fragments and no unexplained location changes.
- An intermediate job needs no direct depot edge. Only the actual last job must have an edge back to the depot.

**Time.** Time is measured in integer **seconds**. Every duration given in minutes is multiplied by 60 and rounded **up**: each travel leg, setup and service separately. Break and working-day limits are whole minutes.

Because each value is rounded up on its own, the rounding can **accumulate**: a route with several fractional durations can gain more than one second in total. The integer model is therefore conservative. It can reject a schedule that fits exactly under the baseline's minute timing near a time limit, and its travel objective is in rounded solver units, not exact physical minutes.

Evidence for the current scenarios comes from `rounding_audit` in `scheduling/equivalence.py`:

- **0 of 280 audited durations** change under the conversion across the seven fictional scenarios (159 / 14 / 28 / 32 / 18 / 11 / 18), so solver travel units equal exact travel time in every one of them.
- A regression test with binary-exact fractional durations that end exactly at 16:00 shows the conservative effect. The exact baseline fits; the rounded model overruns by 1 s in total and does not schedule the job.

- Arrival = previous departure + travel.
- Work starts at max(arrival, access-window start), exactly as in the baseline. Waiting is allowed only for an access window; there is no voluntary idling.
- Work end = start + setup + service, and must not exceed the access-window end.
- **Break rule (same as the baseline):** once the day passes the threshold, one break is taken after the first job ending at or after it. If no job does, the break is taken after the last job when the return passes the threshold.
- The return to the depot must be no later than the working-day end.

**Assignment and resources.**

- Each job is visited by at most one team-day.
- A physical resource can be in at most one **used** team-day per day. This is the whole-day reservation: no handovers.
- There are no overnight stays and no job splitting.

**Validation.** After solving, each team-day's visit order is rebuilt with the
baseline's exact timeline function (minutes, no rounding) and then checked by
the shared independent checker. An itinerary that fails is **rejected**
(`invalid_result_rejected`); it is never reported as an improvement. Both
methods are therefore judged with the same timing semantics.

The baseline's team-ID priority, earliest-due-first selection and immediate
direct-return check are **greedy construction rules**. They are not
constraints of the optimizer.

## Objective (lexicographic, three sequential solves)

1. **Maximise the number of scheduled jobs.**
2. Then **minimise the total absolute days outside each job's supplied preferred window**. Early and late days add up; they never cancel. The signed values stay in the outputs.
3. Then **minimise total travel time**, including depot legs.

How the stages fit together:

- Each stage fixes the previous objective at its found value, and the next stage starts from the previous solution as a hint.
- Sequential solves avoid arbitrary large weights.
- The status, objective value and bound of every stage are recorded.
- If an earlier stage is only FEASIBLE (not proven optimal), the result is labelled `feasible_optimality_not_established`. Only `optimal_for_stated_model` means every stage was proven optimal **for this model and objective**.

Notes on the objective:

- **Cost is not optimised.** It is reported with the shared cost module, and the missing allowance rate stays unknown.
- **Counting jobs can favour small jobs.** The comparison therefore also reports scheduled area (where known), the number of jobs without an area, and scheduled service minutes.
- **The due date is not in the objective.** The operational ±5-day and proposal ±3-day windows are reported separately. Only the job's own supplied window is optimised. The optimizer may therefore schedule a job later than the baseline while staying inside its supplied window; this happens in the demo.

## Solver outcomes

| Label | Meaning |
| --- | --- |
| `optimal_for_stated_model` | All three stages OPTIMAL. |
| `feasible_optimality_not_established` | A valid schedule exists, but at least one stage was not proven optimal (time limit, or a later stage found no improvement within its limit). |
| `no_solution_within_limits` | Stage 1 returned UNKNOWN. This is **not** infeasibility. |
| `model_invalid` / `model_infeasible` | Model errors. Infeasibility is unexpected, because an empty schedule is always allowed. |
| `invalid_result_rejected` | The solver's itinerary failed the exact rebuild or the checker. |

Further rules:

- An empty schedule can be a valid, even optimal, result. It is not a failure.
- An unscheduled job is **not** proven impossible. Explanations only go as far as the evidence:
  - structural reasons (`NO_COMPATIBLE_BUNDLE`, `MULTI_DAY_UNSUPPORTED`, `OUTSIDE_HARD_DATES`, `RESOURCES_UNAVAILABLE`, `NO_TRAVEL_CONNECTION`);
  - otherwise `NOT_SELECTED_BY_OPTIMIZER`, stating whether the job fits a team-day on its own.
- **Fallback** (off by default): if the solver produces no schedule, the baseline can be returned, labelled `rule_baseline_fallback`. It is never presented as optimised.
- **Time budget:** `--time-limit` (default 20 s) is **one shared budget per scenario**, not 20 s per stage.
  - The clock starts before the model is built.
  - Each stage gets the remaining budget divided by the number of stages still to run, with a minimum of 0.01 s. A stage with no time left is recorded as `NOT_RUN_TIME_BUDGET`.
  - End-to-end time includes model building, the three solves and the exact rebuild. The checker and cost calculation run afterwards. Termination exactly at the budget boundary is not guaranteed.
- **Incumbents:** if a later stage returns UNKNOWN, the previous stage's validated solution is kept and the result is labelled `feasible_optimality_not_established`. A test covers this.
- **Configuration:**
  - the shared time budget;
  - `random_seed` (default 42), `num_workers` (default 1), and the solver version.
  
  All are recorded. Identical runtimes or tie-breaking across software versions are not promised.

## Scenarios (defined before evaluation)

See [examples/scheduling_comparison/README.md](../examples/scheduling_comparison/README.md):

- the unchanged 11-job demo;
- six fictional scenarios: a tiny manual case, a case where the baseline does well, shared resources, windows with asymmetric travel, route continuation, and work that version 1 cannot schedule.

Input SHA-256 hashes and the configuration are recorded by the script.

## Results on the fictional scenarios

Run on 27 November 2026; seed 42, 1 worker, 20 s budget, OR-Tools 9.15.6755. The baseline was recomputed, not copied.

Re-run unchanged on 27 November 2026 for the final review, with the same outcomes as the first run.

**Same scheduled job set (like-for-like):**

| Scenario | Scheduled | Days outside window | Travel min (base / opt) | Team-days | Known est. cost LKR (incomplete) | On the stated objective |
| --- | --- | --- | --- | --- | --- | --- |
| demo (11 jobs) | 7 / 7 | 2 / 2 | 338 / 285 | 5 / 3 | 135,380 / 99,730 | optimizer better (travel tier) |
| c1 tiny manual | 2 / 2 | 0 / 0 | 60 / 30 | 1 / 1 | 20,600 / 18,800 | optimizer better (travel); matches the hand-computed optimum |
| c2 baseline good | 4 / 4 | 0 / 0 | 120 / 120 | 2 / 2 | 49,975 / 49,975 | tied |
| c6 unschedulable v1 | 1 / 1 | 0 / 0 | 40 / 40 | 1 / 1 | 18,800 / 18,800 | tied |

**Different scheduled job sets (not like-for-like):**

| Scenario | Scheduled (base / opt) | Days outside window | Travel min | Team-days | Known est. cost LKR (incomplete) | On the stated objective |
| --- | --- | --- | --- | --- | --- | --- |
| c3 shared resource | X / X, Y, Z | 0 / 0 | 50 / 100 | 1 / 1 | 19,160 / 32,840 | optimizer better (job count) |
| c4 windows/asymmetric | P, R / P, Q, R | 1 / 1 | 100 / 95 | 2 / 2 | 38,560 / 38,380 | optimizer better (job count) |
| c5 route continuation | none / A, X | 0 / 0 | 0 / 60 | 0 / 1 | 0 / 19,700 | optimizer better (job count) |

**Solver evidence:**

- Every optimizer stage was OPTIMAL in every scenario, with bound equal to value.
- Total solver time per scenario was 0.004-0.19 s; end-to-end optimize time was 0.006-0.22 s (machine-dependent).
- Every itinerary from both methods passed the independent checker.
- In all seven scenarios the baseline's own assignments and visit orders are **feasible in the optimizer's integer model**. This was checked with `baseline_in_model`, which fixes them as hard constraints (not hints). On the optimizer's measures, the optimizer's objective is lexicographically no worse than the baseline's in each case.

**How to read this:**

- **When "no worse" holds.** A proven-optimal optimizer result can only be called no worse on the stated objective when two conditions hold: the baseline's solution is feasible in the same model, and both are evaluated with the same objective measures and units. Both conditions were verified for these seven scenarios. They would not hold automatically elsewhere: for example, rounding at a time boundary can make a baseline schedule infeasible in the integer model, as the regression test shows.
- **What the comparison does and doesn't show.** It shows *where* the greedy rules lose ground: shared-resource order, due-date order against access windows, and the immediate-return check. It does not show company savings.
- **Not a success rate.** "Better in five, tied in two" describes these seven hand-designed fictional examples. It is not a success rate for any population of real schedules.
- **More work can cost more.** In c3, c4 and c5 the optimizer schedules *more* jobs, so travel and cost can rise. In c3, travel doubles from 50 to 100 minutes, while the known estimated cost rises from LKR 19,160 to LKR 32,840 (about +71%, not double). These differences are not like-for-like.
- **One recorded expectation was wrong.** For c3 I expected the optimizer to drop X. In fact the 4WD team can also do X, so all three jobs were scheduled. The scenario was not changed.
- **Demo details.** The same jobs are scheduled. Service minutes differ (870 vs 855) because one job is done by a different bundle with a different declared work rate. The optimizer packs work into fewer team-days and schedules some jobs later than their due dates, while staying within their supplied windows; ±5 and ±3 compliance counts are unchanged (7 of 11 and 6 of 11).
- **Costs are incomplete.** All costs are known estimates only: the allowance rate is unknown in every scenario. They are not budgets or savings.

## Limitations and what remains

- Fictional inputs only. No approved real planning scenario exists, so nothing is validated on company operations.
- Version-1 rules are shared by both methods: daily return to the depot, whole-day reservation, no handovers, no overnight stays, no job splitting, and one break per day that is never placed inside a job.
- Each duration is rounded up to whole seconds separately inside CP-SAT, so rounding can accumulate along a route (more than one second in total). The exact rebuild and the checker use unrounded minutes. The integer model can therefore exclude a schedule that fits exactly near a limit. No duration in the current seven scenarios is affected, and `scripts/compare_schedulers.py` reports the rounding audit for every run.
- The model is exact over its stated rules (it is not a candidate-route method). Larger instances may hit the time limit, and the status will then say so.
- Still required: overnight and multi-day planning, real approved inputs (due dates, resources, availability, depots, travel matrix, rates), weather and other operational constraints, and ML coverage prediction once verified daily-hectare targets exist.
