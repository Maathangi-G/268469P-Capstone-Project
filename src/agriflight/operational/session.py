"""In-memory, per-session caching of the loaded operational dataset.

The cache lives in a plain mapping (Streamlit's session_state in the app),
never on disk. It is keyed by a signature of the package path and each data
file's size and modification time, so switching packages or editing files
reloads instead of showing stale results. The app clears it when switching
back to synthetic mode.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from agriflight.operational.loader import OperationalDataset, load_package
from agriflight.operational.validation import validate_operational

CACHE_KEY = "_agriflight_operational_cache"


@dataclass
class LoadedOperational:
    signature: tuple
    dataset: OperationalDataset
    findings: pd.DataFrame


def package_signature(root: Path) -> tuple:
    root = Path(root).resolve()
    files = sorted((root / "data").glob("*.csv")) + [root / "docs" / "schema.json", root / "FILE_MANIFEST.json",
                                                   root / "docs" / "validation_results.json"]
    stamp = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files if p.exists())
    return (str(root), stamp)


def get_or_load(store: MutableMapping, root: Path) -> LoadedOperational:
    signature = package_signature(root)
    cached = store.get(CACHE_KEY)
    if isinstance(cached, LoadedOperational) and cached.signature == signature:
        return cached
    clear(store)
    dataset = load_package(root)
    loaded = LoadedOperational(signature, dataset, validate_operational(dataset))
    store[CACHE_KEY] = loaded
    return loaded


def clear(store: MutableMapping) -> None:
    store.pop(CACHE_KEY, None)
