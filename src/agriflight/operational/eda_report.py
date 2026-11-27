"""Assemble EDA and coverage-readiness results, and write private outputs.

``build_results`` is shared by the Streamlit view and the reproduction script.
``write_private_outputs`` writes only to a validated folder that is outside
any Git repository and outside the source dataset package.
"""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agriflight import __version__
from agriflight.operational import coverage, eda
from agriflight.operational.contract import DEFAULT_OBSERVATION_LAYER, OBSERVATION_LAYERS
from agriflight.operational.loader import OperationalDataset, manifest_check
from agriflight.operational.summaries import observations_by_month

DEFAULT_OUTPUT_RELATIVE = Path("..") / "Analysis_Private" / "eda_v0_1"


class OutputLocationError(ValueError):
    """The requested private output folder is not safe to write to."""


def build_results(ds: OperationalDataset) -> dict[str, object]:
    results: dict[str, object] = {
        "completeness": eda.completeness(ds),
        "undated_unmapped": eda.undated_unmapped(ds),
        "area_availability": eda.area_availability(ds),
        "area_distribution": eda.area_distribution(ds),
        "area_by_crop_maturity": eda.area_by_crop_maturity(ds),
        "feature_availability": coverage.feature_availability(),
    }
    for layer in OBSERVATION_LAYERS:
        history = eda.unit_history(ds, layer)
        gaps = eda.recorded_date_gaps(ds, layer)
        bands, gap_stats = eda.gap_distribution(gaps)
        monthly, undated = observations_by_month(ds, layer, eda.DATE_BASIS)
        results[f"unit_history_{layer}"] = history
        results[f"history_overview_{layer}"] = eda.history_overview(history)
        results[f"recorded_date_gaps_{layer}"] = gaps
        results[f"gap_distribution_{layer}"] = bands
        results[f"gap_summary_{layer}"] = gap_stats
        results[f"monthly_observations_{layer}"] = monthly
        results[f"undated_{layer}"] = undated
    overlap_table, overlap_stats = eda.overlap_summary(ds)
    results["overlap_summary"] = overlap_table
    results["overlap_overview"] = overlap_stats
    report, reasons = coverage.feasibility_report(ds)
    blocked, message = coverage.training_status(report)
    results["coverage_feasibility"] = report
    results["coverage_exclusions"] = reasons
    results["training_blocked"] = blocked
    results["training_status"] = message
    results["baseline_status"] = coverage.BASELINE_REAL_DATA_STATUS
    return results


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_output_dir(requested: Path, repo_root: Path, data_root: Path) -> Path:
    """Validate the private output folder; create it if needed."""
    out = Path(requested).expanduser().resolve()
    repo_root, data_root = repo_root.resolve(), data_root.resolve()
    if _inside(out, repo_root) or _inside(repo_root, out):
        raise OutputLocationError("Private outputs must be outside the application repository.")
    if _inside(out, data_root) or _inside(data_root, out):
        raise OutputLocationError("Private outputs must be outside the source dataset package.")
    for parent in (out, *out.parents):
        if (parent / ".git").exists():
            raise OutputLocationError(f"Private outputs must not be inside a Git repository ({parent.name}).")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _git_state(repo_root: Path) -> dict[str, object]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True,
                                  timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    status = run("status", "--porcelain", "--untracked-files=no")
    return {"commit": run("rev-parse", "HEAD") or None, "uncommitted_tracked_changes": bool(status)}


def _write_charts(results: dict[str, object], out: Path) -> list[str]:
    try:
        import altair as alt
    except ImportError:  # charts are optional; CSVs carry the same numbers
        return []
    written = []
    monthly = results[f"monthly_observations_{DEFAULT_OBSERVATION_LAYER}"]
    if isinstance(monthly, pd.DataFrame) and not monthly.empty:
        chart = alt.Chart(monthly).mark_bar().encode(
            x=alt.X("month:N", title="Month (recorded_actual_date)"),
            y=alt.Y("source_observations:Q", title="Source observations (rows, not flights)"),
        ).properties(title=f"Source observations per month - layer {DEFAULT_OBSERVATION_LAYER}")
        chart.save(out / f"chart_monthly_observations_{DEFAULT_OBSERVATION_LAYER}.html")
        written.append(f"chart_monthly_observations_{DEFAULT_OBSERVATION_LAYER}.html")
    bands = results[f"gap_distribution_{DEFAULT_OBSERVATION_LAYER}"]
    if isinstance(bands, pd.DataFrame) and not bands.empty:
        chart = alt.Chart(bands).mark_bar().encode(
            x=alt.X("gap_days_band:N", sort=None, title="Gap between recorded capture dates (days)"),
            y=alt.Y("gaps:Q", title="Gaps (count)"),
        ).properties(title=f"Gaps between recorded capture dates - layer {DEFAULT_OBSERVATION_LAYER}")
        chart.save(out / f"chart_gap_distribution_{DEFAULT_OBSERVATION_LAYER}.html")
        written.append(f"chart_gap_distribution_{DEFAULT_OBSERVATION_LAYER}.html")
    return written


def write_private_outputs(ds: OperationalDataset, results: dict[str, object], findings: pd.DataFrame,
                          out: Path, repo_root: Path) -> list[str]:
    """Write CSVs, charts, a summary and run metadata into the validated folder ``out``."""
    written: list[str] = []
    scalars: dict[str, object] = {}
    for name, value in results.items():
        if isinstance(value, pd.DataFrame):
            value.to_csv(out / f"{name}.csv", index=False)
            written.append(f"{name}.csv")
        else:
            scalars[name] = value
    findings.to_csv(out / "application_findings.csv", index=False)
    written.append("application_findings.csv")
    written += _write_charts(results, out)

    manifest = manifest_check(ds) if ds.manifest else pd.DataFrame(columns=["file", "manifest_sha256"])
    metadata = {
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agriflight_version": __version__,
        "code_git": _git_state(repo_root),
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "package_folder": ds.root.name,
        "package_schema_version": ds.schema.get("version"),
        "package_build_date": ds.schema.get("build_date"),
        "manifest_files_matching": int((manifest["manifest_sha256"] == "matches").sum()),
        "manifest_files_checked": len(manifest),
        "tables_loaded": {name: len(frame) for name, frame in ds.raw.items()},
        "application_findings": int(len(findings)),
        "default_layer": DEFAULT_OBSERVATION_LAYER,
        "date_basis": eda.DATE_BASIS,
        "results": scalars,
        "outputs": sorted(written + ["run_metadata.json", "summary.md"]),
        "privacy": "PRIVATE - pseudonymised real data. Do not commit, publish or share.",
    }
    (out / "run_metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    (out / "summary.md").write_text(_summary_markdown(results), encoding="utf-8")
    return sorted(written + ["run_metadata.json", "summary.md"])


def _summary_markdown(results: dict[str, object]) -> str:
    layer = DEFAULT_OBSERVATION_LAYER
    lines = [
        "# PRIVATE - AgriFlight EDA and coverage readiness (generated)",
        "",
        "Pseudonymised real data. Do not commit, publish or share.",
        "Counts are source observation rows unless stated; layers are not combined.",
        "",
        f"## Default layer: {layer} (date basis: {eda.DATE_BASIS})",
        f"- Recorded-date history: {json.dumps(results[f'history_overview_{layer}'], default=str)}",
        f"- {eda.GAP_LABEL}: {json.dumps(results[f'gap_summary_{layer}'], default=str)}",
        f"- Rows without {eda.DATE_BASIS}: {results[f'undated_{layer}']}",
        "",
        "## Source overlap (candidate overlaps, not confirmed duplicates)",
        f"- {json.dumps(results['overlap_overview'], default=str)}",
        "",
        "## Coverage target feasibility",
        f"- {results['training_status']}",
        f"- Historical-mean baseline: {results['baseline_status']}",
        "",
        "See the CSV files in this folder for full tables and run_metadata.json for provenance.",
    ]
    return "\n".join(lines) + "\n"
