from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from agriflight.operational.contract import ENV_VAR
from agriflight.operational.eda_report import OutputLocationError, resolve_output_dir
from operational_fixtures import build_package, file_hashes

REPO_ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("run_eda", REPO_ROOT / "scripts" / "run_eda.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_tests_do_not_need_private_dataset(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert _script().main([]) == 2  # clear failure, no fallback data


def test_output_inside_repository_is_refused(tmp_path):
    pkg = build_package(tmp_path)
    with pytest.raises(OutputLocationError, match="repository"):
        resolve_output_dir(REPO_ROOT / "private_outputs", REPO_ROOT, pkg)


def test_output_inside_dataset_is_refused(tmp_path):
    pkg = build_package(tmp_path)
    with pytest.raises(OutputLocationError, match="dataset"):
        resolve_output_dir(pkg / "eda", REPO_ROOT, pkg)


def test_output_inside_any_git_repo_is_refused(tmp_path):
    (tmp_path / "other_repo" / ".git").mkdir(parents=True)
    with pytest.raises(OutputLocationError, match="Git"):
        resolve_output_dir(tmp_path / "other_repo" / "out", REPO_ROOT, tmp_path / "pkg")


def test_script_writes_outputs_and_leaves_package_unchanged(tmp_path):
    pkg = build_package(tmp_path / "data")
    before = file_hashes(pkg)
    out = tmp_path / "Analysis_Private" / "eda_v0_1"
    assert _script().main(["--data-dir", str(pkg), "--output-dir", str(out)]) == 0
    assert file_hashes(pkg) == before
    names = {p.name for p in out.iterdir()}
    assert {"coverage_feasibility.csv", "recorded_date_gaps_main_monthly.csv", "run_metadata.json",
            "summary.md", "application_findings.csv"} <= names
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["results"]["training_blocked"] is True
    assert meta["results"]["baseline_status"].startswith("Implemented and tested; not fitted")
    assert meta["package_folder"] == pkg.name and "PRIVATE" in meta["privacy"]
