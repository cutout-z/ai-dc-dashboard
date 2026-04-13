"""Build the master project database from seed CSV + enrichment.

Reads the seed CSV (manually curated from public sources), applies risk
model, and outputs projects.parquet for the dashboard.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models.risk_model import apply_risk_weight
from models.capex_model import estimate_capex

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_CSV = BASE_DIR / "data" / "reference" / "projects_seed.csv"
OPERATOR_CSV = BASE_DIR / "data" / "reference" / "operator_types.csv"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


def build():
    print("=" * 60)
    print("Building Project Database")
    print("=" * 60)

    # Load seed data
    df = pd.read_csv(SEED_CSV)
    print(f"  Loaded {len(df)} projects from seed CSV")

    # Clean numeric columns
    for col in ["facility_mw", "critical_it_mw", "capex_aud_m", "startup_year", "full_capacity_year", "pue", "wue"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Apply risk model
    df = apply_risk_weight(df, status_col="status", mw_col="facility_mw")

    # Estimate CAPEX where not disclosed
    df = estimate_capex(df)

    # Enrich with operator type from reference table
    operators = pd.read_csv(OPERATOR_CSV)
    df = df.merge(
        operators[["operator", "listed", "ticker"]],
        on="operator",
        how="left",
        suffixes=("", "_ref"),
    )

    # Size classification
    df["size_class"] = pd.cut(
        df["facility_mw"],
        bins=[0, 10, 50, 200, float("inf")],
        labels=["Small (<10MW)", "Mid-size (10-50MW)", "Large (50-200MW)", "Hyperscale (>200MW)"],
    )

    # Save
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "projects.parquet"
    df.to_parquet(out_path, index=False)
    print(f"  Saved: {out_path.name} ({len(df)} rows)")

    # Summary
    print("\n--- Summary ---")
    print(f"  Total projects: {len(df)}")
    print(f"  Total facility MW (unrisked): {df['facility_mw'].sum():,.0f}")
    print(f"  Total facility MW (risked):   {df['risked_mw'].sum():,.0f}")
    print(f"\n  By status:")
    for status, group in df.groupby("status"):
        print(f"    {status}: {len(group)} projects, {group['facility_mw'].sum():,.0f} MW")
    print(f"\n  By operator:")
    for op, group in df.groupby("operator"):
        print(f"    {op}: {len(group)} projects, {group['facility_mw'].sum():,.0f} MW")


if __name__ == "__main__":
    build()
