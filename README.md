# AgriFlight AI - Data Readiness Dashboard

Capstone project (Master's in Data Science and AI, G. Maathangi, 268469P):
**Agri-Flight AI - decision support for agricultural drone-operation planning.**

> **Current scope: foundation milestone (v0.1.0).** This repository contains a
> documented demonstration data schema, reusable loading and data-quality
> validation modules, a local Streamlit dashboard and automated tests.
> It does **not** yet contain a trained model, a scheduler, route optimisation,
> or any analysis of real company records.

## Privacy warning

This is a public repository. **Never commit company data**: raw workbooks,
the private dataset package, exports, screenshots of real records, or any file
with real farm, client, pilot, coordinate or cost information.
The only data in this repository is `data/sample/demo_operations.csv`, which is
**entirely synthetic** (see [data/sample/README.md](data/sample/README.md)).
`.gitignore` blocks common private paths, but it does not protect files that
are already tracked: always review `git status` and `git diff --cached`.

The dashboard reads uploaded CSVs in memory only and never writes them to
disk. It is configured to listen on `localhost` only.

## Requirements

- Python 3.10+ (developed and tested on Python 3.14.7, Windows 11)
- pandas, Streamlit, pytest (installed below)

## Installation

From the repository root:

```bash
python -m venv .venv
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[app,dev]"
```

The editable install makes the `agriflight` package (in `src/`) importable from
the app, the tests and notebooks.

## Run the dashboard

```bash
streamlit run app/app.py
```

Run it from the repository root, then open <http://localhost:8501> (or
<http://127.0.0.1:8501>) in a browser. The app runs headless and bound to this
machine only (see `.streamlit/config.toml`); stop it with `Ctrl+C`.

## Run the tests

```bash
python -m pytest
```

## Using the synthetic demo

1. Start the dashboard; the sidebar defaults to **Bundled synthetic demo**.
2. **Overview**: record counts by type, distinct units/clients and valid date
   ranges. Counts are *source rows*, not completed flights or services.
3. **Data Explorer**: filter by operating unit and record type. Choose
   *Upload a CSV* in the sidebar to inspect another file in the
   [demonstration schema](docs/data_contract.md).
4. **Data Quality**: the demo intentionally contains 7 issues (duplicate ID,
   missing unit ID, impossible date, negative area, non-numeric area,
   undocumented record type), so validation is expected to **fail**.
5. **Project Status**: implemented vs. pending work and open business decisions.

## Implemented vs. planned

| Area | Status |
| --- | --- |
| Synthetic demonstration dataset + data contract | Implemented |
| CSV loader (text-preserving, row provenance) | Implemented, tested |
| Data-quality validator (structured issue table) | Implemented, tested |
| Summary service (counts, date ranges, blanks) | Implemented, tested |
| Streamlit dashboard (4 views, in-memory upload) | Implemented; headless smoke-tested |
| Adapter from private company workbooks | Planned - needs approved mappings and rules |
| Completed-service event ledger, cadence (30 +/- 5 days) evaluation | Planned - business rules unconfirmed |
| Coverage prediction (baseline + ML), scheduling, routing, cost & scenario analysis | Planned (see proposal) |

## Repository layout

```
app/app.py                         Streamlit UI (presentation only)
src/agriflight/data/schema.py      Demonstration schema definition
src/agriflight/data/loader.py      CSV loading
src/agriflight/data/validation.py  Data-quality rules -> issue table
src/agriflight/services/           Summaries and project-status content
data/sample/                       Synthetic demonstration data only
tests/                             pytest suite (incl. headless app smoke test)
docs/                              Architecture, data contract, checkpoint notes
```

See [docs/architecture.md](docs/architecture.md),
[docs/data_contract.md](docs/data_contract.md) and
[docs/technical_checkpoint.md](docs/technical_checkpoint.md).
