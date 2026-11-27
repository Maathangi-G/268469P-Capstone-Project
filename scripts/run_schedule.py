"""Run the rule-based scheduling baseline on a scenario folder.

Usage (repository root, virtual environment active):

    python scripts/run_schedule.py                              # fictional demo, prints a summary
    python scripts/run_schedule.py --output-dir ..\\Analysis_Private\\scheduling_demo
    python scripts/run_schedule.py --scenario-dir <approved private scenario> \\
        --output-dir ..\\Analysis_Private\\scheduling_v0_1

A non-synthetic scenario must live outside the repository, and its outputs
must go to a folder outside any Git repository and outside the dataset package.
Missing inputs are reported; nothing is substituted. No network access.
Outputs are draft planning results, not dispatch authorisation.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agriflight import __version__
from agriflight.operational.contract import ENV_VAR
from agriflight.operational.eda_report import OutputLocationError, resolve_output_dir
from agriflight.scheduling import DRAFT_NOTICE, ScenarioError, load_scenario, run_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "examples" / "scheduling_demo"


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rule-based scheduling baseline (draft planning).")
    parser.add_argument("--scenario-dir", type=Path, default=DEMO_DIR)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        scenario = load_scenario(args.scenario_dir)
    except ScenarioError as exc:
        print("ERROR: the scenario lacks required inputs or has invalid values:", file=sys.stderr)
        for issue in exc.issues:
            if issue["severity"] == "error":
                print(f"  - {issue['file']} {issue['record_id']} {issue['field']}: {issue['message']}", file=sys.stderr)
        return 2
    if not scenario.is_synthetic and _inside(args.scenario_dir, REPO_ROOT):
        print("ERROR: non-synthetic scenario inputs must be kept outside the Git repository.", file=sys.stderr)
        return 2
    out_dir = args.output_dir
    if out_dir is None and not scenario.is_synthetic:
        out_dir = REPO_ROOT / ".." / "Analysis_Private" / "scheduling_v0_1"
    if out_dir is not None:
        try:
            out = resolve_output_dir(out_dir, REPO_ROOT, args.scenario_dir)
            data_root = os.environ.get(ENV_VAR, "").strip().strip('"')
            if data_root and (_inside(out, Path(data_root)) or _inside(Path(data_root), out)):
                raise OutputLocationError("Outputs must be outside the source dataset package.")
        except OutputLocationError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    run = run_scenario(scenario)
    scheduled, total = len(run.result.assignments), len(scenario.jobs)
    label = "FICTIONAL DEMO SCENARIO" if scenario.is_synthetic else "PRIVATE SCENARIO - do not commit or share"
    print(f"[{label}] {scenario.scenario_id}: {scheduled} of {total} job(s) scheduled by the baseline; "
          f"{len(run.result.unassigned)} not scheduled; {len(run.result.routes)} bundle-day route(s).")
    print(f"Independent checks passed: {run.checks_passed}")
    print(f"Estimated known cost (LKR): {run.cost_summary['estimated_known_total_lkr']}; "
          f"coverage complete: {run.cost_summary['coverage_complete']} {run.cost_summary['missing_components']}")
    print(DRAFT_NOTICE)
    if out_dir is None:
        return 0 if run.checks_passed else 1
    for name, frame in run.frames.items():
        frame.to_csv(out / f"{name}.csv", index=False)
    meta = {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "agriflight_version": __version__,
            "python": platform.python_version(), "pandas": pd.__version__, "scenario_id": scenario.scenario_id,
            "data_origin": scenario.data_origin, "scenario_folder": Path(args.scenario_dir).name,
            "jobs_scheduled": scheduled, "jobs_total": total, "checks_passed": run.checks_passed,
            "cost_summary": run.cost_summary, "notice": DRAFT_NOTICE, "label": label}
    (out / "run_metadata.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {len(run.frames) + 1} file(s) to: {out}")
    return 0 if run.checks_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
