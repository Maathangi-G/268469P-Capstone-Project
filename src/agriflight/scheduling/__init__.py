"""Rule-based scheduling baseline (draft planning; not optimisation, not dispatch).

This is a DIFFERENT baseline from agriflight.baselines.HistoricalMeanBaseline
(coverage prediction, unfitted). Capacity here comes only from explicit,
declared scenario assumptions.
"""

from agriflight.scheduling.contracts import Scenario, ScenarioError, load_scenario
from agriflight.scheduling.outputs import DRAFT_NOTICE, ScheduleRun, run_folder, run_scenario

__all__ = ["DRAFT_NOTICE", "Scenario", "ScenarioError", "ScheduleRun", "load_scenario", "run_folder", "run_scenario"]
