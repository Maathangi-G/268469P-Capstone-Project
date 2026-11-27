"""Reproduce the operational EDA and coverage-readiness outputs (private).

Usage (from the repository root, with the virtual environment active):

    $env:AGRIFLIGHT_DATA_DIR = (Resolve-Path "..\\Dataset\\AgriFlight_Integrated_v0_2").Path
    python scripts/run_eda.py

Outputs go to ..\\Analysis_Private\\eda_v0_1 by default (outside the repository
and outside the dataset package); override with --output-dir. The dataset is
only read. No network access, credentials or restricted identity package are
used. Console output is limited to status lines; results stay in the folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agriflight.operational.contract import ENV_VAR
from agriflight.operational.eda_report import (
    DEFAULT_OUTPUT_RELATIVE,
    OutputLocationError,
    build_results,
    resolve_output_dir,
    write_private_outputs,
)
from agriflight.operational.loader import PackageError, check_package_dir, load_package, resolve_package_dir
from agriflight.operational.validation import finding_counts, validate_operational

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, help=f"package root (default: ${ENV_VAR})")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / DEFAULT_OUTPUT_RELATIVE,
                        help="private output folder (default: ../Analysis_Private/eda_v0_1)")
    args = parser.parse_args(argv)
    try:
        root = check_package_dir(args.data_dir) if args.data_dir else resolve_package_dir()
        out = resolve_output_dir(args.output_dir, REPO_ROOT, root)
    except (PackageError, OutputLocationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    ds = load_package(root)
    findings = validate_operational(ds)
    results = build_results(ds)
    written = write_private_outputs(ds, results, findings, out, REPO_ROOT)
    counts = finding_counts(findings) if not findings.empty else {"error": 0, "warning": 0, "info": 0}
    print(f"Loaded package folder '{root.name}': {len(ds.tables)} tables; application findings {counts}.")
    print(results["training_status"])
    print(f"Historical-mean baseline: {results['baseline_status']}")
    print(f"Wrote {len(written)} private file(s) to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
