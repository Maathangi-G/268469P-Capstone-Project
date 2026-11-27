"""Headless Streamlit smoke tests (no browser).

Uses streamlit.testing.AppTest to execute the script and inspect rendered
elements. This verifies the app runs and shows key content; it does not
replace manual interaction testing in a browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from agriflight.operational.contract import ENV_VAR  # noqa: E402
from agriflight.operational.session import CACHE_KEY  # noqa: E402
from operational_fixtures import build_package  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "app" / "app.py"
MODE_PRIVATE = "Private operational dataset"
MODE_SYNTHETIC = "Synthetic demonstration (default)"
PRIVATE_TABS = ["Divisions & readiness", "Operational records", "Budget & vehicle evidence", "Data quality",
                "EDA & coverage readiness", "Project Status"]
SYNTHETIC_BANNER = "Every row is fictional"  # wording unique to the synthetic-data banner


def _all_text(at: AppTest) -> str:
    parts = []
    for kind in ("markdown", "warning", "error", "info", "success", "caption", "title", "subheader"):
        parts += [str(el.value) for el in getattr(at, kind)]
    return "\n".join(parts)


def _app() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=60)


@pytest.fixture(autouse=True)
def _no_private_env(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


def test_app_runs_with_bundled_demo():
    at = _app().run()
    assert not at.exception
    text = _all_text(at)
    assert "Synthetic demonstration data" in text
    assert "Validation failed: 7 error(s)" in text
    assert "No validation errors" not in text
    assert [t.label for t in at.tabs] == ["Overview", "Data Explorer", "Data Quality", "Project Status"]
    labels = [m.label for m in at.metric]
    assert "Source records (rows)" in labels
    assert at.metric[0].value == "27"


def test_upload_mode_without_file_does_not_crash():
    at = _app().run()
    at.sidebar.radio[0].set_value("Upload a CSV (demonstration schema)").run()
    assert not at.exception
    assert "No data loaded" in _all_text(at)


def test_synthetic_is_default_even_when_variable_is_set(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(build_package(tmp_path)))
    at = _app().run()
    assert at.sidebar.selectbox[0].value == MODE_SYNTHETIC
    assert "Synthetic demonstration data" in _all_text(at)
    assert CACHE_KEY not in at.session_state


def test_private_mode_without_variable_shows_error_and_no_substitute():
    at = _app().run()
    at.sidebar.selectbox[0].set_value(MODE_PRIVATE).run()
    assert not at.exception
    text = _all_text(at)
    assert "Private operational dataset not loaded" in text and ENV_VAR in text
    assert SYNTHETIC_BANNER not in text
    assert not at.tabs


def test_private_mode_with_invalid_path(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "missing"))
    at = _app().run()
    at.sidebar.selectbox[0].set_value(MODE_PRIVATE).run()
    assert not at.exception
    assert "does not exist" in _all_text(at)


def test_private_mode_with_fixture_package(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(build_package(tmp_path)))
    at = _app().run()
    at.sidebar.selectbox[0].set_value(MODE_PRIVATE).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == PRIVATE_TABS
    text = _all_text(at)
    assert "pseudonymised REAL data" in text
    assert SYNTHETIC_BANNER not in text
    assert "No structural errors from the application checks" in text
    assert "Coverage-model training blocked" in text
    assert "not fitted or evaluated on operational targets" in text


def test_switching_modes_has_no_stale_results(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(build_package(tmp_path / "a")))
    at = _app().run()
    at.sidebar.selectbox[0].set_value(MODE_PRIVATE).run()
    assert CACHE_KEY in at.session_state
    first = at.session_state[CACHE_KEY].dataset.root

    at.sidebar.selectbox[0].set_value(MODE_SYNTHETIC).run()
    assert not at.exception
    assert CACHE_KEY not in at.session_state  # private data dropped
    assert at.metric[0].value == "27"
    assert "pseudonymised REAL data" not in _all_text(at)

    monkeypatch.setenv(ENV_VAR, str(build_package(tmp_path / "b")))
    at.sidebar.selectbox[0].set_value(MODE_PRIVATE).run()
    assert not at.exception
    assert at.session_state[CACHE_KEY].dataset.root != first
