"""
ETL: AI Mapping 5.0 → SQLite + CSV
Extracts the Mapping 5.0 (Jan26) sheet with all 5 survey waves.
"""

import sqlite3
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"
CSV_DIR = Path(__file__).parent.parent / "data" / "processed"

MAPPING_FILE = RAW_DIR / "AI_Mapping_5.0.xlsx"

# Column name mapping for clean schema
COLUMN_MAP = {
    "Ticker": "ticker",
    "Factset Ticker": "factset_ticker",
    "Bloomberg ID": "bloomberg_id",
    "ISIN": "isin",
    "Company": "company",
    "Region": "region",
    "GICS Sector": "gics_sector",
    "GICS Industry": "gics_industry",
    "Market Cap (1/30/26; USD)": "market_cap_usd_m",
    "New Exposure": "exposure_latest",
    "New Materiality": "materiality_latest",
    "Pricing Power": "pricing_power_latest",
    "Exposure 1": "exposure_w1",
    "Exposure 2": "exposure_w2",
    "Exposure 3": "exposure_w3",
    "Exposure 4": "exposure_w4",
    "Exposure 5": "exposure_w5",
    "Materiality 1": "materiality_w1",
    "Materiality 2": "materiality_w2",
    "Materiality 3": "materiality_w3",
    "Materiality 4": "materiality_w4",
    "Materiality 5": "materiality_w5",
    "Pricing Power 1": "pricing_power_w1",
    "Pricing Power 2": "pricing_power_w2",
    "Pricing Power 3": "pricing_power_w3",
    "Pricing Power 4": "pricing_power_w4",
    "Pricing Power 5": "pricing_power_w5",
    "Exposure Survey 1 to 2": "exposure_delta_1_2",
    "Exposure Survey 2 to 3": "exposure_delta_2_3",
    "Exposure Survey 3 to 4": "exposure_delta_3_4",
    "Exposure Survey 4 to 5": "exposure_delta_4_5",
    "Materiality Survey 1 to 2": "materiality_delta_1_2",
    "Materiality Survey 2 to 3": "materiality_delta_2_3",
    "Materiality Survey 3 to 4": "materiality_delta_3_4",
    "Materiality Survey 4 to 5": "materiality_delta_4_5",
    "Pricing Survey 2 to 3": "pricing_delta_2_3",
    "Pricing Survey 3 to 4": "pricing_delta_3_4",
    "Pricing Survey 4 to 5": "pricing_delta_4_5",
}

# Ordinal encoding for filtering/sorting
MATERIALITY_ORDER = {
    "Insignificant": 1,
    "Moderate": 2,
    "Significant": 3,
    "Core to Thesis": 4,
}

PRICING_POWER_ORDER = {
    "Low": 1,
    "Neutral": 2,
    "High": 3,
}

EXPOSURE_CATEGORIES = [
    "Adopter",
    "Enabler",
    "Enabler/Adopter",
    "Protected",
    "Disrupted",
    "Wildcard",
    "Don't Know",
]


def clean_na(val):
    """Normalise #N/A, -, and other sentinel values to None."""
    if pd.isna(val):
        return None
    if isinstance(val, str) and val.strip() in ("#N/A", "-", "N/A", ""):
        return None
    return val


def compute_materiality_trend(row):
    """Count how many times materiality moved Up across waves."""
    waves = [row.get(f"materiality_w{i}") for i in range(1, 6)]
    waves = [w for w in waves if w is not None]
    if len(waves) < 2:
        return None
    upgrades = 0
    for i in range(1, len(waves)):
        prev = MATERIALITY_ORDER.get(waves[i - 1], 0)
        curr = MATERIALITY_ORDER.get(waves[i], 0)
        if curr > prev:
            upgrades += 1
        elif curr < prev:
            upgrades -= 1
    return upgrades


def run():
    print(f"Reading {MAPPING_FILE}...")
    df = pd.read_excel(MAPPING_FILE, sheet_name="Mapping 5.0 (Jan26)", header=0)

    # Rename columns
    df = df.rename(columns=COLUMN_MAP)

    # Keep only mapped columns
    keep_cols = [c for c in COLUMN_MAP.values() if c in df.columns]
    df = df[keep_cols]

    # Drop rows without a ticker
    df = df.dropna(subset=["ticker"])

    # Clean #N/A and sentinels
    for col in df.columns:
        df[col] = df[col].apply(clean_na)

    # Add ordinal scores for materiality and pricing power (latest)
    df["materiality_score"] = df["materiality_latest"].map(MATERIALITY_ORDER)
    df["pricing_power_score"] = df["pricing_power_latest"].map(PRICING_POWER_ORDER)

    # Compute materiality trend (net upgrades across waves)
    df["materiality_trend"] = df.apply(compute_materiality_trend, axis=1)

    # Flag the "alpha" cohort: high materiality + pricing power
    df["alpha_flag"] = (
        (df["materiality_score"] >= 3) & (df["pricing_power_score"] >= 3)
    ).astype(int)

    print(f"  {len(df)} stocks loaded")
    print(f"  Alpha cohort (Significant+ materiality & High pricing power): {df['alpha_flag'].sum()}")
    print(f"  Regions: {df['region'].value_counts().to_dict()}")

    # Write to SQLite
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("mapping", conn, if_exists="replace", index=False)

    # Create useful views
    conn.execute("DROP VIEW IF EXISTS v_alpha_stocks")
    conn.execute("""
        CREATE VIEW v_alpha_stocks AS
        SELECT ticker, company, region, gics_sector, gics_industry,
               market_cap_usd_m, exposure_latest, materiality_latest,
               pricing_power_latest, materiality_trend
        FROM mapping
        WHERE alpha_flag = 1
        ORDER BY market_cap_usd_m DESC
    """)

    conn.execute("DROP VIEW IF EXISTS v_materiality_upgraders")
    conn.execute("""
        CREATE VIEW v_materiality_upgraders AS
        SELECT ticker, company, region, gics_sector,
               materiality_w1, materiality_w2, materiality_w3,
               materiality_w4, materiality_w5, materiality_trend
        FROM mapping
        WHERE materiality_trend > 0
        ORDER BY materiality_trend DESC, market_cap_usd_m DESC
    """)

    conn.commit()
    conn.close()

    # Write CSV
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = CSV_DIR / "mapping_5.csv"
    df.to_csv(csv_path, index=False)
    print(f"  Written to {DB_PATH} and {csv_path}")


if __name__ == "__main__":
    run()
