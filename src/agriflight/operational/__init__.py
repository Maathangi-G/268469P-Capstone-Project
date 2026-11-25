"""Read-only integration of the private integrated operational dataset (v0.2).

The dataset itself is never stored in this repository. Its location is given
at run time by the AGRIFLIGHT_DATA_DIR environment variable.
"""

from agriflight.operational.contract import ENV_VAR
from agriflight.operational.loader import (
    OperationalDataset,
    PackageError,
    load_package,
    resolve_package_dir,
)
from agriflight.operational.validation import validate_operational

__all__ = [
    "ENV_VAR",
    "OperationalDataset",
    "PackageError",
    "load_package",
    "resolve_package_dir",
    "validate_operational",
]
