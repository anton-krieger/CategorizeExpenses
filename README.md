# CategorizeExpenses

An interactive command-line tool to manually categorize expenses from a private CSV file.
Your financial data stays local and is protected from accidental commits via `.gitignore`.

## Requirements

- Python 3.10+
- No third-party packages needed (standard library only)

## Quick start

```bash
# 1. Place your expense CSV in the data/ directory
#    (data/ is gitignored – your data stays private)
mkdir -p data
cp /path/to/my_expenses.csv data/

# 2. Run the categorizer
python categorize.py data/my_expenses.csv

# 3. The categorized output is saved automatically to
#    data/categorized_my_expenses.csv
```

## Usage

```
python categorize.py <input.csv> [options]

positional arguments:
  input                 Path to the input CSV file

options:
  --output <path>       Output CSV path
                        (default: data/categorized_<input filename>)
  --categories <list>   Comma-separated category names
                        (overrides the built-in list)
  --date-col <name>     Column name for the date   (default: Date)
  --desc-col <name>     Column name for description (default: Description)
  --amount-col <name>   Column name for the amount  (default: Amount)
  --redo                Re-categorize rows that already have a category
```

## How it works

1. Each expense row is displayed with its date, description, and amount.
2. You pick a category by entering its number or the first letters of its name.
3. Enter **s** to skip a row, or **q** to save and quit at any time.
4. Progress is saved after every session – already-categorized rows are skipped
   on the next run unless `--redo` is passed.

## Built-in categories

Groceries, Dining, Transport, Housing, Utilities, Health, Entertainment,
Shopping, Travel, Income, Other

Override them with `--categories "Food,Rent,Fun,Salary"`.

## Input CSV format

The CSV must have a header row. The default expected column names are
`Date`, `Description`, and `Amount`. Use `--date-col`, `--desc-col`, and
`--amount-col` to map different column names.

Example:

```csv
Date,Description,Amount
2024-01-03,Supermarket XYZ,-52.40
2024-01-04,Monthly rent,-900.00
2024-01-05,Salary,3000.00
```

## Privacy

- `data/` and `*.csv` are listed in `.gitignore` – they will never be committed.
- Keep your source CSV and the categorized output inside `data/`.
