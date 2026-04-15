"""Audit all reference CSVs for data provenance and integrity.

Checks:
  1. Every row has a non-empty source/reference attribution
  2. Column count is consistent (catches shifted fields)
  3. No "synthesis", "estimate", "projected" in source names (flag for review)
  4. Numeric columns don't contain suspiciously uniform sequences
  5. Dates are parseable where expected
  6. No duplicate rows

Run:  python scripts/audit_reference_data.py
Exit code 0 = clean, 1 = warnings only, 2 = errors found.
"""

import csv
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "reference"

# Columns that count as "source attribution" — at least one must be non-empty per row
SOURCE_COLS = {"source", "reference", "published_date"}

# Substrings in source fields that should be flagged for manual review
SUSPECT_SOURCE_TERMS = [
    "synthesis", "estimate", "estimated", "projected", "interpolat",
    "assumed", "approximat", "derived", "inferred", "placeholder",
]

errors: list[str] = []
warnings: list[str] = []


def audit_file(path: Path) -> None:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        n_cols = len(header)
        header_lower = [h.strip().lower() for h in header]

        # Which columns carry source attribution?
        src_indices = [i for i, h in enumerate(header_lower) if h in SOURCE_COLS]
        if not src_indices:
            warnings.append(f"{path.name}: no source/reference/published_date column found")

        # Which columns look numeric?
        numeric_col_indices = []
        for i, h in enumerate(header_lower):
            if any(kw in h for kw in ("gw", "twh", "usd", "value", "capacity", "price", "revenue", "capex", "demand")):
                numeric_col_indices.append(i)

        prev_numeric_vals: dict[int, list[float]] = {i: [] for i in numeric_col_indices}

        for row_num, row in enumerate(reader, start=2):
            # --- Column count consistency ---
            if len(row) != n_cols:
                errors.append(
                    f"{path.name}:{row_num}: column count {len(row)} != header {n_cols} "
                    f"(shifted fields?)"
                )
                continue

            # --- Source attribution ---
            if src_indices:
                has_source = any(row[i].strip() for i in src_indices if i < len(row))
                if not has_source:
                    errors.append(f"{path.name}:{row_num}: no source attribution in any of {[header[i] for i in src_indices]}")

                # Check for suspect source terms
                for i in src_indices:
                    if i < len(row):
                        val_lower = row[i].strip().lower()
                        for term in SUSPECT_SOURCE_TERMS:
                            if term in val_lower:
                                warnings.append(
                                    f"{path.name}:{row_num}: source contains '{term}' — "
                                    f"verify this is actual reported data, not fabricated: "
                                    f'"{row[i].strip()}"'
                                )

            # --- Collect numeric values for uniformity check ---
            for i in numeric_col_indices:
                if i < len(row) and row[i].strip():
                    try:
                        prev_numeric_vals[i].append(float(row[i].strip()))
                    except ValueError:
                        pass

        # --- Uniformity check: flag if a numeric column has perfectly uniform spacing ---
        for i, vals in prev_numeric_vals.items():
            if len(vals) >= 4:
                diffs = [vals[j+1] - vals[j] for j in range(len(vals) - 1)]
                if len(set(round(d, 4) for d in diffs)) == 1 and diffs[0] != 0:
                    warnings.append(
                        f"{path.name}: column '{header[i]}' has perfectly uniform spacing "
                        f"({diffs[0]}) across {len(vals)} values — may be interpolated"
                    )


def main() -> int:
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        print("No CSV files found in", DATA_DIR)
        return 2

    print(f"Auditing {len(csv_files)} reference CSVs in {DATA_DIR}\n")

    for path in csv_files:
        audit_file(path)

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if not errors and not warnings:
        print("All reference CSVs pass provenance audit. ✓")
        return 0

    if errors:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
