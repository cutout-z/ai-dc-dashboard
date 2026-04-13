"""Download and parse AEMO data for grid capacity and demand analysis.

Sources:
- Generation Information page (quarterly Excel workbook)
- Aggregated operational demand data (CSV)
"""

import os
import sys
import requests
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "aemo"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# AEMO Generation Information page — latest workbook URL
# Updated quarterly; check https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information
GEN_INFO_URL = "https://aemo.com.au/-/media/files/electricity/nem/planning_and_forecasting/generation_information/2026/nem-generation-information-jan-2026.xlsx"

# Fuel type classification
FUEL_CATEGORIES = {
    # Clean baseload
    "Hydro": "Clean Baseload",
    "Battery": "Storage",
    "Biomass": "Clean Baseload",
    "Geothermal": "Clean Baseload",
    # Intermittent / VRE
    "Wind": "VRE",
    "Solar": "VRE",
    "Solar / Wind": "VRE",
    "Wind / Solar": "VRE",
    # Fossil
    "Black Coal": "Fossil",
    "Brown Coal": "Fossil",
    "Natural Gas": "Fossil",
    "Gas": "Fossil",
    "Natural Gas / Fuel Oil": "Fossil",
    "Natural Gas / Diesel": "Fossil",
    "Diesel": "Fossil",
    "Coal Seam Methane": "Fossil",
    "Waste Coal Mine Gas": "Fossil",
    # Other
    "Water": "Clean Baseload",
}


def download_file(url: str, dest: Path, force: bool = False) -> Path:
    """Download a file if it doesn't already exist."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  Already exists: {dest.name}")
        return dest
    print(f"  Downloading: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    resp = requests.get(url, timeout=120, headers=headers)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"  Saved: {dest.name} ({len(resp.content) / 1024 / 1024:.1f} MB)")
    return dest


# Map AEMO 'Commitment Status' values to our canonical status labels
_COMMITMENT_STATUS_MAP = {
    "In Service": "Operating",
    "In Commissioning": "Operating",
    "Committed": "Committed",
    "Committed*": "Committed",
    "Anticipated": "Proposed",
    "Publicly Announced": "Proposed",
    "Announced Withdrawal": "Withdrawn",
}


def _parse_consolidated_gen_info(xlsx_path: Path) -> pd.DataFrame:
    """Parse the consolidated 'Generator Information' sheet (Jan 2026+ format)."""
    print("  Parsing consolidated 'Generator Information' sheet")

    df_peek = pd.read_excel(xlsx_path, sheet_name="Generator Information",
                            header=None, nrows=10, engine="openpyxl")
    header_row = 0
    for i, row in df_peek.iterrows():
        row_vals = [str(v).strip() for v in row.values if pd.notna(v)]
        # The real header row has column titles like "Region", "Site Name", "DUID"
        if "Region" in row_vals and "Site Name" in row_vals:
            header_row = i
            break

    df = pd.read_excel(xlsx_path, sheet_name="Generator Information",
                       header=header_row, engine="openpyxl")

    # Normalise column names
    df.columns = [str(c).strip() for c in df.columns]

    # Map to canonical column names
    col_map = {
        "Region": "nem_region",
        "Site Name": "station_name",
        "Technology Type": "fuel_type",
        "Agg Nameplate Capacity (MW AC)": "nameplate_mw",
        "Site Owner": "owner",
        "DUID": "duid",
        "Expected Closure Year": "retirement_year",
        "Full Commercial Use Date": "commission_year",
        "Commitment Status": "commitment_status",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Map commitment status to our canonical status labels
    df["status"] = df["commitment_status"].map(_COMMITMENT_STATUS_MAP).fillna("Other")
    df = df[df["status"] != "Other"]

    # Drop rows without station name
    df = df.dropna(subset=["station_name"])

    # Clean up numeric capacity
    df["nameplate_mw"] = pd.to_numeric(df["nameplate_mw"], errors="coerce")

    # Fuel category mapping
    df["fuel_category"] = df["fuel_type"].map(
        lambda x: FUEL_CATEGORIES.get(str(x).strip(), "Other") if pd.notna(x) else "Other"
    )

    # Map new technology types not in FUEL_CATEGORIES
    tech_map = {
        "Battery Storage": "Storage",
        "Solar PV": "VRE",
        "Gas Turbine": "Fossil",
        "Coal": "Fossil",
    }
    mask = df["fuel_category"] == "Other"
    df.loc[mask, "fuel_category"] = df.loc[mask, "fuel_type"].map(
        lambda x: tech_map.get(str(x).strip(), "Other") if pd.notna(x) else "Other"
    )

    # Clean NEM region
    df["nem_region"] = df["nem_region"].astype(str).str.strip().str.upper()

    # Select output columns
    common_cols = ["nem_region", "station_name", "fuel_type", "nameplate_mw", "status"]
    optional_cols = ["owner", "duid", "retirement_year", "commission_year", "fuel_category"]
    all_cols = common_cols + [c for c in optional_cols if c in df.columns]
    df = df[all_cols]

    print(f"  Total generators parsed: {len(df)}")
    print(f"  By status: {df['status'].value_counts().to_dict()}")

    return df


def parse_generation_info(xlsx_path: Path) -> pd.DataFrame:
    """Parse the AEMO Generation Information workbook into a clean DataFrame.

    Supports two workbook formats:
    1. Legacy (pre-2026): separate sheets per status (ExistingGeneration, Committed, Proposed)
    2. Consolidated (Jan 2026+): single 'Generator Information' sheet with 'Commitment Status' column
    """
    xl = pd.ExcelFile(xlsx_path, engine="openpyxl")
    sheet_names = xl.sheet_names
    print(f"  Sheets found: {sheet_names}")

    # --- Consolidated format: single 'Generator Information' sheet ---
    if "Generator Information" in sheet_names:
        return _parse_consolidated_gen_info(xlsx_path)

    # --- Legacy format: multiple sheets by status ---
    frames = []

    for sheet in sheet_names:
        sheet_lower = sheet.lower().strip()

        # Determine status from sheet name
        if "existing" in sheet_lower and "gen" in sheet_lower:
            status = "Operating"
        elif "committed" in sheet_lower and "gen" in sheet_lower:
            status = "Committed"
        elif "proposed" in sheet_lower and "gen" in sheet_lower:
            status = "Proposed"
        elif "withdraw" in sheet_lower or "retire" in sheet_lower:
            status = "Withdrawn"
        else:
            continue

        print(f"  Parsing sheet: {sheet} -> {status}")

        # Read with header detection — AEMO sheets often have merged header rows
        # Try reading first 10 rows to find the header
        df_peek = pd.read_excel(xlsx_path, sheet_name=sheet, header=None, nrows=10,
                                engine="openpyxl")

        # Find the header row — look for a row containing typical column names
        header_row = 0
        for i, row in df_peek.iterrows():
            row_str = " ".join(str(v).lower() for v in row.values if pd.notna(v))
            if any(kw in row_str for kw in ["region", "station", "fuel", "capacity", "technology"]):
                header_row = i
                break

        df = pd.read_excel(xlsx_path, sheet_name=sheet, header=header_row,
                           engine="openpyxl")

        # Normalise column names
        df.columns = [str(c).strip().lower().replace("\n", " ") for c in df.columns]

        # Map common column name variations
        col_map = {}
        for col in df.columns:
            if "region" in col and "nem" not in col_map:
                col_map[col] = "nem_region"
            elif "station" in col and "name" in col and "station_name" not in col_map:
                col_map[col] = "station_name"
            elif ("fuel" in col or "technology" in col) and "fuel_type" not in col_map:
                col_map[col] = "fuel_type"
            elif "nameplate" in col and "capacity" in col and "nameplate_mw" not in col_map:
                col_map[col] = "nameplate_mw"
            elif col in ("capacity (mw)", "max cap (mw)", "reg cap (mw)") and "nameplate_mw" not in col_map:
                col_map[col] = "nameplate_mw"
            elif "owner" in col and "owner" not in col_map:
                col_map[col] = "owner"
            elif ("expected" in col and "closure" in col) or ("retire" in col and "year" in col):
                col_map[col] = "retirement_year"
            elif "expected" in col and ("commission" in col or "start" in col):
                col_map[col] = "commission_year"
            elif "duid" in col:
                col_map[col] = "duid"

        df = df.rename(columns=col_map)
        df["status"] = status

        # Keep only rows with actual data
        if "station_name" in df.columns:
            df = df.dropna(subset=["station_name"])
        elif "nem_region" in df.columns:
            df = df.dropna(subset=["nem_region"])

        frames.append(df)

    if not frames:
        print("  WARNING: No generation sheets found!")
        return pd.DataFrame()

    # Combine all sheets
    # Use only the common columns across sheets
    common_cols = ["nem_region", "station_name", "fuel_type", "nameplate_mw", "status"]
    optional_cols = ["owner", "duid", "retirement_year", "commission_year"]

    all_cols = common_cols + [c for c in optional_cols if any(c in f.columns for f in frames)]

    result_frames = []
    for df in frames:
        available = [c for c in all_cols if c in df.columns]
        result_frames.append(df[available])

    combined = pd.concat(result_frames, ignore_index=True)

    # Clean up
    if "nameplate_mw" in combined.columns:
        combined["nameplate_mw"] = pd.to_numeric(combined["nameplate_mw"], errors="coerce")

    if "fuel_type" in combined.columns:
        combined["fuel_category"] = combined["fuel_type"].map(
            lambda x: FUEL_CATEGORIES.get(str(x).strip(), "Other") if pd.notna(x) else "Other"
        )

    # Clean NEM region
    if "nem_region" in combined.columns:
        combined["nem_region"] = combined["nem_region"].astype(str).str.strip().str.upper()

    print(f"  Total generators parsed: {len(combined)}")
    print(f"  By status: {combined['status'].value_counts().to_dict()}")

    return combined


def build_grid_capacity(gen_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate generation info into grid capacity by region, fuel category, and status."""
    if gen_df.empty:
        return pd.DataFrame()

    grid = (
        gen_df.groupby(["nem_region", "fuel_category", "status"])
        .agg(
            capacity_mw=("nameplate_mw", "sum"),
            num_stations=("station_name", "nunique"),
        )
        .reset_index()
    )

    # Round for cleanliness
    grid["capacity_mw"] = grid["capacity_mw"].round(1)

    return grid


def main(force_download: bool = False):
    """Run the full AEMO ETL pipeline."""
    print("=" * 60)
    print("AEMO Data ETL")
    print("=" * 60)

    # 1. Download Generation Information
    print("\n1. Looking for Generation Information workbook...")
    gen_info_file = RAW_DIR / "nem-generation-information-latest.xlsx"

    if not gen_info_file.exists():
        print(f"  Attempting download...")
        try:
            download_file(GEN_INFO_URL, gen_info_file, force=force_download)
        except Exception as e:
            print(f"  Auto-download failed ({e})")
            print(f"  AEMO blocks automated downloads. Please download manually:")
            print(f"  1. Go to: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information")
            print(f"  2. Download the NEM Generation Information Excel file")
            print(f"  3. Save as: {gen_info_file}")
            print(f"  4. Re-run this script")
            sys.exit(1)
    else:
        print(f"  Found: {gen_info_file.name}")

    # 2. Parse generation data
    print("\n2. Parsing generation data...")
    gen_df = parse_generation_info(gen_info_file)

    if gen_df.empty:
        print("ERROR: No generation data parsed. Check the workbook format.")
        sys.exit(1)

    # 3. Build grid capacity summary
    print("\n3. Building grid capacity summary...")
    grid_capacity = build_grid_capacity(gen_df)

    # 4. Save processed data
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    gen_path = PROCESSED_DIR / "generation_info.parquet"
    gen_df.to_parquet(gen_path, index=False)
    print(f"  Saved: {gen_path.name} ({len(gen_df)} rows)")

    grid_path = PROCESSED_DIR / "grid_capacity.parquet"
    grid_capacity.to_parquet(grid_path, index=False)
    print(f"  Saved: {grid_path.name} ({len(grid_capacity)} rows)")

    # 5. Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if "nem_region" in grid_capacity.columns:
        print("\nCapacity by Region (MW):")
        region_summary = (
            grid_capacity[grid_capacity["status"] == "Operating"]
            .groupby("nem_region")["capacity_mw"]
            .sum()
            .sort_values(ascending=False)
        )
        for region, mw in region_summary.items():
            print(f"  {region}: {mw:,.0f} MW")

        print("\nCapacity by Fuel Category (MW) — Operating:")
        fuel_summary = (
            grid_capacity[grid_capacity["status"] == "Operating"]
            .groupby("fuel_category")["capacity_mw"]
            .sum()
            .sort_values(ascending=False)
        )
        for fuel, mw in fuel_summary.items():
            print(f"  {fuel}: {mw:,.0f} MW")

        print(f"\nTotal Operating Capacity: {region_summary.sum():,.0f} MW")

    print("\nDone.")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force_download=force)
