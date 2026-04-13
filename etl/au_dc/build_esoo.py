"""Build ESOO regional forecast parquet from reference CSV.

The ESOO (Electricity Statement of Opportunities) provides 10-year
regional supply-demand balance forecasts from AEMO.

Data sourced from AEMO 2025 ESOO (August 2025), Step Change scenario,
10% POE maximum demand. Demand anchored to actual peak records from
AEMO quarterly reports; supply-demand balance reflects confirmed
reliability gaps (QLD 2025-26, SA 2026-27) and major retirements
(Torrens Island B 2026, Eraring 2027, Yallourn 2028).
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
ESOO_CSV = BASE_DIR / "data" / "reference" / "esoo_forecasts.csv"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


def build():
    print("=" * 60)
    print("Building ESOO Forecasts")
    print("=" * 60)

    if not ESOO_CSV.exists():
        print("  No ESOO CSV found — skipping")
        return

    df = pd.read_csv(ESOO_CSV)
    for col in ["year", "max_demand_mw", "available_supply_mw", "surplus_mw"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "esoo_forecasts.parquet"
    df.to_parquet(out_path, index=False)
    print(f"  Saved: {out_path.name} ({len(df)} rows)")

    print(f"\n  Regions: {sorted(df['nem_region'].unique().tolist())}")
    print(f"  Years: {df['year'].min()}-{df['year'].max()}")
    print(f"  Scenario: {sorted(df['scenario'].unique().tolist())}")
    print(f"  Source: AEMO 2025 ESOO Step Change (10% POE)")


if __name__ == "__main__":
    build()
