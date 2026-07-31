# CategorizeExpenses

An interactive local web app to browse, search, and tag expenses from private
bank-export CSVs. Your financial data stays local: it's read from `data/` (gitignored)
and the app only ever listens on `127.0.0.1` — never on the network or internet.

## Requirements

- Python 3.10+
- `streamlit`, `pandas` (see `requirements.txt`)

## Quick start

```bash
# 1. Place your bank export CSVs in year-named subfolders under data/
#    (data/ is gitignored – your data stays private)
#    One CSV per year is expected; all years are combined automatically.
mkdir -p data/2024 data/2025
cp /path/to/export_2024.csv data/2024/
cp /path/to/export_2025.csv data/2025/

# 2. Create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py
```

This opens `http://127.0.0.1:8501` in your browser. The bundled
`.streamlit/config.toml` pins the server to localhost — do not override this
with `--server.address` when running the app.

## How it works

- **Filter column** – switch between all entries and entries with no tags yet,
  or select one or more tags to filter by.
- **Entries column** – type to search names/purposes, sort by date or price,
  bulk-select rows (or select all/clear in the current view), and apply
  existing or newly created tags to the selection. New tags get a random
  color the first time they're created.
- **Stats column** – income, expense, and net totals, plus per-year and
  per-month breakdowns, all computed on the currently filtered + searched view.

## Data & privacy

- `data/` is entirely gitignored — your source CSVs and all derived files stay local.
- Source CSVs live in year subfolders, e.g. `data/2024/export.csv`, `data/2025/export.csv`.
  All CSVs found in these year folders are loaded and combined into one dataset.
- The app never modifies your source CSVs. It only writes two files:
  - `data/tags.json` – tag name → color definitions
  - `data/tagged_entries.csv` – entry id → tags (the only file that changes as you work)
- The app makes no external network calls and only binds to `127.0.0.1`.

