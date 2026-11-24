"""Headless Streamlit smoke test (no browser).

Uses streamlit.testing.AppTest to execute the script and inspect rendered
elements. This verifies the app runs and shows key content; it does not
replace manual interaction testing in a browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "app" / "app.py"


def _all_text(at: AppTest) -> str:
    parts = []
    for kind in ("markdown", "warning", "error", "info", "success", "caption", "title", "subheader"):
        parts += [str(el.value) for el in getattr(at, kind)]
    return "\n".join(parts)


def test_app_runs_with_bundled_demo():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
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
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.radio[0].set_value("Upload a CSV (demonstration schema)").run()
    assert not at.exception
    assert "No data loaded" in _all_text(at)
