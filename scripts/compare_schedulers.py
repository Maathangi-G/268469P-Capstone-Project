"""Compare the rule-based baseline and the CP-SAT optimizer on fictional scenarios.

Usage (repository root, virtual environment active, ortools installed):

    python scripts/compare_schedulers.py                     # all fictional scenarios, summary to console
    python scripts/compare_schedulers.py --time-limit 20 --seed 42 --workers 1
    python scripts/compare_schedulers.py --output-dir ..\\Analysis_Private\\scheduler_comparison

Writes (only with --output-dir, outside any Git repository): per-scenario
comparison tables, both itineraries, unassigned jobs and run_metadata.json
with input hashes, solver version and configuration. No network access.
Results on fictional scenarios demonstrate model behaviour only.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agriflight import __version__
from agriflight.operational.eda_report import OutputLocationError, resolve_output_dir
from agriflight.scheduling.comparison import OBJECTIVE_PRIORITIES, assess, compare_folder
from agriflight.scheduling.equivalence import baseline_in_model, rounding_audit
from agriflight.scheduling.optimizer import OptimizerConfig, solver_version

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = [REPO_ROOT / "examples" / "scheduling_demo"] + sorted(
    p for p in (REPO_ROOT / "examples" / "scheduling_comparison").iterdir() if p.is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baseline vs CP-SAT optimizer comparison (fictional scenarios).")
    parser.add_argument("--scenario-dir", type=Path, action="append", help="repeatable; default: all fictional")
    parser.add_argument("--time-limit", type=float, default=20.0, help="total CP-SAT seconds per scenario")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--fallback", action="store_true", help="return a LABELLED baseline fallback on solver failure")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if "not installed" in solver_version():
        print("ERROR: OR-Tools is not installed. Install with: python -m pip install \"ortools>=9.15,<9.16\"",
              file=sys.stderr)
        return 2
    cfg = OptimizerConfig(time_limit_s=args.time_limit, random_seed=args.seed, num_workers=args.workers,
                          fallback_to_baseline=args.fallback)
    folders = args.scenario_dir or DEFAULT_SCENARIOS
    out = None
    if args.output_dir:
        try:
            out = resolve_output_dir(args.output_dir, REPO_ROOT, folders[0])
        except OutputLocationError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    print("Objective priorities: " + " | ".join(OBJECTIVE_PRIORITIES))
    print(f"Solver: {solver_version()}; config {cfg}")
    summary, meta_runs, all_valid = [], [], True
    for folder in folders:
        comp = compare_folder(folder, cfg)
        verdict = assess(comp)
        valid = comp.baseline.checks_passed and (comp.optimizer_run is None or comp.optimizer_run.checks_passed)
        all_valid &= valid
        label = "FICTIONAL" if comp.scenario.is_synthetic else "PRIVATE - do not share"
        b_n = len(comp.baseline.result.assignments)
        o_n = len(comp.optimizer_run.result.assignments) if comp.optimizer_run else None
        audit = rounding_audit(comp.scenario)
        rounded = int((audit["rounding_added_s"] > 0).sum())
        fit = baseline_in_model(comp.scenario, comp.baseline.result, cfg)
        solver_s = round(sum(s["wall_time_s"] for s in comp.optimizer.stages), 4)
        print(f"[{label}] {comp.scenario.scenario_id}: baseline {b_n}/{len(comp.scenario.jobs)} jobs, optimizer "
              f"{o_n}/{len(comp.scenario.jobs)} ({comp.optimizer.status_label}); {verdict}")
        print(f"    durations changed by integer-second rounding: {rounded} of {len(audit)}; baseline feasible in "
              f"optimizer model: {fit['status']}; solver {solver_s} s, end-to-end optimize {comp.optimizer.runtime_s} s")
        for note in comp.notes:
            print(f"    note: {note}")
        summary.append({"scenario": comp.scenario.scenario_id, "baseline_scheduled": b_n, "optimizer_scheduled": o_n,
                        "optimizer_status": comp.optimizer.status_label, "verdict_on_stated_objective": verdict,
                        "same_job_set": comp.same_job_set, "checks_valid": valid})
        meta_runs.append({"scenario_id": comp.scenario.scenario_id, "folder": folder.name, "input_sha256": comp.input_hash,
                          "stages": comp.optimizer.stages, "status_label": comp.optimizer.status_label,
                          "fallback_used": comp.optimizer.fallback_used, "message": comp.optimizer.message,
                          "model_size": comp.optimizer.model_size, "optimizer_runtime_s": comp.optimizer.runtime_s,
                          "baseline_runtime_s": round(comp.baseline_runtime_s, 6), "notes": comp.notes,
                          "solver_time_total_s": solver_s, "durations_changed_by_rounding": rounded,
                          "durations_audited": len(audit), "baseline_feasible_in_optimizer_model": fit})
        if out:
            sub = out / folder.name
            sub.mkdir(exist_ok=True)
            comp.table.to_csv(sub / "comparison.csv", index=False)
            comp.baseline.frames["itinerary"].to_csv(sub / "baseline_itinerary.csv", index=False)
            comp.baseline.frames["unassigned"].to_csv(sub / "baseline_unassigned.csv", index=False)
            if comp.optimizer_run:
                comp.optimizer_run.frames["itinerary"].to_csv(sub / "optimizer_itinerary.csv", index=False)
                comp.optimizer_run.frames["unassigned"].to_csv(sub / "optimizer_unassigned.csv", index=False)
    if out:
        pd.DataFrame(summary).to_csv(out / "summary.csv", index=False)
        meta = {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "agriflight_version": __version__,
                "python": platform.python_version(), "pandas": pd.__version__, "solver": solver_version(),
                "config": cfg.__dict__, "objective_priorities": OBJECTIVE_PRIORITIES, "runs": meta_runs,
                "notice": "Fictional scenarios; draft plans; not dispatch authorisation; no company-level claim."}
        (out / "run_metadata.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        print(f"Wrote comparison outputs to: {out}")
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
