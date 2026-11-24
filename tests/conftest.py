from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_CSV = REPO_ROOT / "data" / "sample" / "demo_operations.csv"

HEADER = (
    "observation_id,operating_unit_id,client_id,record_type,planned_date,"
    "actual_date,recorded_status,area_ha,data_origin"
)


def make_csv(*rows: str, header: str = HEADER) -> bytes:
    """Build CSV bytes from a header and pre-formatted data rows."""
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


@pytest.fixture
def demo_csv_path() -> Path:
    return DEMO_CSV
