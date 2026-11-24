from __future__ import annotations

import io

import pytest

from agriflight.data.loader import (
    DataLoadError,
    load_operations_csv,
    missing_columns,
    parse_typed_columns,
)
from agriflight.data.schema import EXPECTED_COLUMNS
from conftest import make_csv


def test_loads_valid_csv_with_all_columns_and_source_rows():
    data = make_csv(
        "OBS_1,UNIT_1,CLIENT_A,planned_visit,2026-01-01,,planned,10,synthetic_demo",
        "OBS_2,UNIT_1,CLIENT_A,capture_observation,2026-01-01,2026-01-02,recorded,9.5,synthetic_demo",
    )
    frame = load_operations_csv(data)
    assert len(frame) == 2
    assert list(frame.columns) == ["source_row", *EXPECTED_COLUMNS]
    assert frame["source_row"].tolist() == [2, 3]
    assert missing_columns(frame) == []


def test_bundled_demo_file_loads(demo_csv_path):
    frame = load_operations_csv(demo_csv_path)
    assert len(frame) == 27
    assert set(frame["data_origin"]) == {"synthetic_demo"}


def test_identifiers_are_preserved_as_text():
    data = make_csv(
        "007,0012,00A,planned_visit,2026-01-01,,planned,1,synthetic_demo",
        "1e3,12.50,NaN,planned_visit,2026-01-01,,planned,1,synthetic_demo",
    )
    frame = load_operations_csv(data)
    assert frame["observation_id"].tolist() == ["007", "1e3"]
    assert frame["operating_unit_id"].tolist() == ["0012", "12.50"]
    # "NaN" is a literal string here, not a missing value.
    assert frame["client_id"].tolist() == ["00A", "NaN"]


def test_blanks_stay_blank_and_are_not_filled():
    data = make_csv("OBS_1,UNIT_1,,planned_visit,2026-01-01,,,,synthetic_demo")
    frame = load_operations_csv(data)
    row = frame.iloc[0]
    assert row["client_id"] == ""
    assert row["actual_date"] == ""
    assert row["area_ha"] == ""


def test_source_file_is_not_modified(tmp_path):
    path = tmp_path / "input.csv"
    original = make_csv("OBS_1,UNIT_1,CLIENT_A,planned_visit,2026-01-01,,planned,10,synthetic_demo")
    path.write_bytes(original)
    load_operations_csv(path)
    assert path.read_bytes() == original


def test_accepts_file_like_objects():
    data = make_csv("OBS_1,UNIT_1,CLIENT_A,planned_visit,2026-01-01,,planned,10,synthetic_demo")
    assert len(load_operations_csv(io.BytesIO(data))) == 1
    assert len(load_operations_csv(io.StringIO(data.decode("utf-8")))) == 1


def test_handles_utf8_bom_and_padded_headers():
    data = "﻿ observation_id ,operating_unit_id\nOBS_1,UNIT_1\n".encode("utf-8")
    frame = load_operations_csv(data)
    assert "observation_id" in frame.columns


@pytest.mark.parametrize("content", [b"", b"\n\n"])
def test_empty_input_raises_helpful_error(content):
    with pytest.raises(DataLoadError, match="no data"):
        load_operations_csv(content)


def test_empty_file_on_disk_raises_helpful_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(DataLoadError, match="empty"):
        load_operations_csv(path)


def test_missing_file_raises_helpful_error(tmp_path):
    with pytest.raises(DataLoadError, match="not found"):
        load_operations_csv(tmp_path / "nope.csv")


def test_header_only_returns_empty_frame():
    frame = load_operations_csv(make_csv())
    assert len(frame) == 0
    assert missing_columns(frame) == []


def test_missing_columns_are_listed_not_fatal():
    frame = load_operations_csv(b"observation_id,record_type\nOBS_1,planned_visit\n")
    missing = missing_columns(frame)
    assert "operating_unit_id" in missing
    assert "observation_id" not in missing


def test_non_utf8_input_raises_helpful_error():
    with pytest.raises(DataLoadError, match="UTF-8"):
        load_operations_csv(b"observation_id\n\xff\xfe\xfa\n")


def test_malformed_csv_raises_helpful_error():
    with pytest.raises(DataLoadError, match="parsed"):
        load_operations_csv(b"a,b\n1,2\n3,4,5,6\n")


def test_parse_typed_columns_keeps_raw_text():
    data = make_csv("OBS_1,UNIT_1,C,planned_visit,2026-02-30,,planned,abc,synthetic_demo")
    typed = parse_typed_columns(load_operations_csv(data))
    assert typed.at[0, "planned_date"] == "2026-02-30"
    assert typed["planned_date_parsed"].isna().all()
    assert typed.at[0, "area_ha"] == "abc"
    assert typed["area_ha_parsed"].isna().all()
