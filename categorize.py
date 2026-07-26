"""Interactive expense categorization tool.

Usage:
    python categorize.py <input.csv> [--output <output.csv>] [--categories <cat1,cat2,...>]

The input CSV must contain at least the columns specified via --date-col, --desc-col and
--amount-col (defaults: Date, Description, Amount).  Every other column is displayed as
extra context but not modified.

The output CSV is the input data with an additional "Category" column filled in for each
row.  Already-categorized rows (non-empty Category) are skipped unless --redo is passed.

Both input and output files should live in the data/ directory, which is gitignored to
keep your private financial data out of version control.
"""

import argparse
import csv
import os
import sys
from typing import Literal


DEFAULT_CATEGORIES = [
    "Groceries",
    "Dining",
    "Transport",
    "Housing",
    "Utilities",
    "Health",
    "Entertainment",
    "Shopping",
    "Travel",
    "Income",
    "Other",
]

CATEGORY_COL = "Category"
SEPARATOR = "-" * 60


def parse_args():
    parser = argparse.ArgumentParser(
        description="Interactively categorize expenses from a CSV file."
    )
    parser.add_argument("input", help="Path to the input CSV file")
    parser.add_argument(
        "--output",
        default=None,
        help="Path to the output CSV file (default: data/categorized_<input filename>)",
    )
    parser.add_argument(
        "--categories",
        default=None,
        help="Comma-separated list of categories (overrides the built-in list)",
    )
    parser.add_argument(
        "--date-col",
        default="Date",
        help="Name of the date column (default: Date)",
    )
    parser.add_argument(
        "--desc-col",
        default="Description",
        help="Name of the description column (default: Description)",
    )
    parser.add_argument(
        "--amount-col",
        default="Amount",
        help="Name of the amount column (default: Amount)",
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Re-categorize rows that already have a category",
    )
    return parser.parse_args()


def default_output_path(input_path: str) -> str:
    filename = os.path.basename(input_path)
    name, ext = os.path.splitext(filename)
    output_filename = f"categorized_{name}{ext}"
    return os.path.join("data", output_filename)


def load_csv(path: str) -> tuple[list[str], list[dict]]:
    """Return (fieldnames, rows) from a CSV file."""
    if not os.path.isfile(path):
        print(f"Error: input file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def save_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_category_menu(categories: list[str]) -> None:
    print("\nCategories:")
    for idx, cat in enumerate(categories, start=1):
        print(f"  [{idx:2d}] {cat}")
    print("  [ s] Skip this row")
    print("  [ q] Save & quit")


def prompt_category(
    row: dict,
    categories: list[str],
    date_col: str,
    desc_col: str,
    amount_col: str,
) -> str | Literal["SKIP", "QUIT"]:
    """Display a row and ask the user to pick a category.

    Returns the chosen category string, 'SKIP', or 'QUIT'.
    """
    print(SEPARATOR)
    date = row.get(date_col, "")
    desc = row.get(desc_col, "")
    amount = row.get(amount_col, "")

    print(f"  Date:        {date}")
    print(f"  Description: {desc}")
    print(f"  Amount:      {amount}")

    excluded = {date_col, desc_col, amount_col, CATEGORY_COL}
    extra = {k: v for k, v in row.items() if k not in excluded and v != ""}
    for key, val in extra.items():
        print(f"  {key}: {val}")

    print_category_menu(categories)

    while True:
        try:
            raw = input("\nYour choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "QUIT"

        if raw == "q":
            return "QUIT"
        if raw == "s":
            return "SKIP"
        try:
            idx = int(raw)
            if 1 <= idx <= len(categories):
                return categories[idx - 1]
        except ValueError:
            pass

        # Allow typing the category name directly
        matches = [c for c in categories if c.lower().startswith(raw)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(f"Ambiguous – did you mean one of: {', '.join(matches)}?")
            continue

        print(f"Invalid input. Enter a number between 1 and {len(categories)}, 's', or 'q'.")


def main() -> None:
    args = parse_args()

    categories = (
        [c.strip() for c in args.categories.split(",") if c.strip()]
        if args.categories
        else DEFAULT_CATEGORIES
    )

    output_path = args.output or default_output_path(args.input)

    fieldnames, rows = load_csv(args.input)

    # Ensure Category column exists in fieldnames
    if CATEGORY_COL not in fieldnames:
        fieldnames.append(CATEGORY_COL)
    for row in rows:
        row.setdefault(CATEGORY_COL, "")

    pending = [r for r in rows if args.redo or not r[CATEGORY_COL]]
    already_done = len(rows) - len(pending)

    print(f"\n{SEPARATOR}")
    print(f"  Expense Categorizer")
    print(f"{SEPARATOR}")
    print(f"  Input:   {args.input}")
    print(f"  Output:  {output_path}")
    print(f"  Total rows:   {len(rows)}")
    print(f"  Already done: {already_done}")
    print(f"  To categorize: {len(pending)}")
    print(f"{SEPARATOR}\n")

    if not pending:
        print("All rows are already categorized. Use --redo to re-categorize.")
        save_csv(output_path, fieldnames, rows)
        print(f"Output saved to: {output_path}")
        return

    categorized_count = 0
    for row in pending:
        result = prompt_category(row, categories, args.date_col, args.desc_col, args.amount_col)
        if result == "QUIT":
            print("\nQuitting – saving progress so far.")
            break
        if result == "SKIP":
            continue
        row[CATEGORY_COL] = result
        categorized_count += 1

    save_csv(output_path, fieldnames, rows)
    print(f"\n{SEPARATOR}")
    print(f"  Categorized {categorized_count} row(s) this session.")
    print(f"  Output saved to: {output_path}")
    print(f"{SEPARATOR}\n")


if __name__ == "__main__":
    main()
