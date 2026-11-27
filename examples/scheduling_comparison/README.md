# Fictional comparison scenarios (defined before evaluation)

These scenarios are **entirely fictional**. They were written, and their
intent recorded here, **before** either method was run on them. They are kept
unchanged and reported in full, including results that do not favour the
optimizer. Regenerate them with `python examples/scheduling_comparison/build_scenarios.py`.

The existing 11-job scenario `examples/scheduling_demo/` is also part of the
comparison, unchanged.

All scenarios share the same rules as the demo:

- working day 08:00-16:00;
- a 30-minute break once the day exceeds 240 minutes;
- return to the depot every day;
- whole-day reservation of shared resources;
- no overnight stays or job splitting;
- the allowance rate is deliberately unknown.

| Scenario | Purpose | Recorded expectation (before running) |
| --- | --- | --- |
| `c1_tiny_manual` | Tiny, manually solvable check of optimizer correctness. One team, two 60-minute jobs, asymmetric travel. | By hand: both jobs can be scheduled with 0 days outside the preferred window. The cheapest route is DEP→A→B→DEP = 30 travel minutes, versus DEP→B→A→DEP = 60. The baseline picks B first because B has the earlier due date. |
| `c2_baseline_good` | A case where the greedy baseline should already do well: two independent teams, each with two nearby jobs. | Both methods schedule all 4 jobs. Travel is likely tied. |
| `c3_shared_resource` | Two bundles share one drone. One job (X) suits only the car team; two jobs (Y, Z) need the 4WD team. | The baseline processes TEAM_1 first, takes X, and so blocks TEAM_2. The optimizer can instead use TEAM_2 for Y and Z. The two methods would then schedule **different job sets**. |
| `c4_windows_asymmetric` | An access window (Q, 08:00-09:45), a booking date (R on day 2 only) and asymmetric travel. | The baseline takes P first (earliest due date), which makes Q miss its access window. Visiting Q first allows both P and Q. R can only be scheduled on day 2, outside its preferred window. |
| `c5_route_continuation` | A valid route exists only as DEP→A→X→DEP: there is no direct DEP→X edge and no direct A→DEP edge. | The baseline's construction cannot add A (no direct return) or reach X. The optimizer can schedule both through the full route. |
| `c6_unschedulable_v1` | Work that version 1 cannot schedule: a multi-day job, a site too far for a same-day return, an incompatible equipment requirement, and an unconnected site. One ordinary job is included. | Both methods schedule only the ordinary job. The others stay unscheduled with structural reasons. |
