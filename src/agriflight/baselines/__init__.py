"""Baseline models. No model in this package has been fitted to operational targets.

(Named "baselines", not "models": the repository .gitignore excludes models/
directories, which are reserved for private trained artifacts.)
"""

from agriflight.baselines.baseline import (
    BaselineInputError,
    HistoricalMeanBaseline,
    chronological_split,
)

__all__ = ["BaselineInputError", "HistoricalMeanBaseline", "chronological_split"]
