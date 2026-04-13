"""Fetch AEMO grid data via NEMOSIS (nemweb.com.au MMS tables).

This bypasses aemo.com.au Cloudflare protection by pulling from the
MMS data archives on nemweb.com.au. We combine DUDETAILSUMMARY (region,
station) with DUDETAIL (registered capacity) and the NEM Registration
List (fuel source) to produce the grid_capacity.parquet file.

Also integrates the AEMO Generation Information workbook (if available)
for committed/proposed generation pipeline data.
"""

import os
import sys
from pathlib import Path

import pandas as pd
from nemosis import dynamic_data_compiler

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "data" / "raw" / "aemo" / "nemosis_cache"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RAW_DIR = BASE_DIR / "data" / "raw" / "aemo"

# Path to NEM Registration List (authoritative fuel source data)
# Downloaded from: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/participant-information/nem-registration-and-exemption-list
NEM_REG_LIST_PATH = RAW_DIR / "NEM-Registration-and-Exemption-List.xls"

# Fallback: map registration list fuel sources to our standard names
REG_FUEL_MAP = {
    "Fossil": "Fossil",          # broad category — use descriptor for detail
    "Solar": "Solar",
    "Wind": "Wind",
    "Hydro": "Hydro",
    "Battery Storage": "Battery",
    "Renewable/ Biomass / Waste": "Biomass",
    "Renewable/ Biomass / Waste and Fossil": "Biomass",
    "-": "Other",
}

# Map fuel descriptors to more specific types
REG_DESCRIPTOR_MAP = {
    "Black Coal": "Black Coal",
    "Brown Coal": "Brown Coal",
    "Natural Gas": "Natural Gas",
    "Diesel": "Diesel",
    "Coal Seam Methane": "Natural Gas",
    "Waste Coal Mine Gas": "Natural Gas",
    "Natural Gas / Fuel Oil": "Natural Gas",
    "Natural Gas / Diesel": "Natural Gas",
    "Natrual Gas/ Diesel": "Natural Gas",  # AEMO typo in registration list
    "Ethane": "Natural Gas",
    "Kerosene": "Diesel",
    "Water": "Hydro",
    "Solar": "Solar",
    "Wind": "Wind",
    "Grid": "Battery",
    "Landfill Methane / Landfill Gas": "Biomass",
    "Bagasse": "Biomass",
    "Biomass": "Biomass",
    "Sewerage / Waste Water": "Biomass",
}

# DUID suffix/substring patterns — fallback for DUIDs not in registration list
DUID_FUEL_PATTERNS = {
    "WF": "Wind", "WN": "Wind",
    "SF": "Solar", "PV": "Solar",
    "BESS": "Battery", "BL": "Battery",
    "PUMP": "Hydro",
}

# Station name prefix → fuel type (fallback for DUIDs not in registration list)
STATION_FUEL_MAP = {
    # Black Coal
    "BAYSW": "Black Coal", "ERARING": "Black Coal", "LIDDELL": "Black Coal",
    "MP": "Black Coal", "VP": "Black Coal", "LD": "Black Coal",
    "CALL": "Black Coal", "CALLIDE": "Black Coal", "G/STONE": "Black Coal",
    "KOGAN": "Black Coal", "MILLMERN": "Black Coal", "STANWELL": "Black Coal",
    "TARONG": "Black Coal", "HUNTER": "Natural Gas",  # Hunter Power (gas peaker, ex-Liddell site)
    # Brown Coal
    "LOYYB": "Brown Coal", "LOYYA": "Brown Coal", "YALLOUR": "Brown Coal",
    # Natural Gas
    "TALLAWAR": "Natural Gas", "COLONGRA": "Natural Gas", "URANQ": "Natural Gas",
    "MORTLK": "Natural Gas", "JEERB": "Natural Gas", "JEERA": "Natural Gas",
    "NEWPORT": "Natural Gas", "LAVNTH": "Natural Gas",
    "B2PS": "Natural Gas", "B3PS": "Natural Gas", "BARCALDN": "Natural Gas",
    "CONDAMINE": "Natural Gas", "OAKEY": "Natural Gas", "ROMA": "Natural Gas",
    "SWANB": "Natural Gas", "YARWUN": "Natural Gas", "TORRIS": "Natural Gas",
    "TORRA": "Natural Gas", "TORRB": "Natural Gas",
    "PELICN": "Natural Gas", "OSBORNE": "Natural Gas", "QUARANTN": "Natural Gas",
    "LADBROK": "Natural Gas", "BARKIPS": "Natural Gas", "SNUGGERY": "Natural Gas",
    "BELL_BAY": "Natural Gas", "TAMAR": "Natural Gas", "NPPPPS": "Natural Gas",
    "MSTUART": "Natural Gas", "LNGS": "Natural Gas", "VPGS": "Natural Gas",
    "MCKAY": "Natural Gas", "YABULU": "Natural Gas", "AGLHAL": "Natural Gas",
    "DDPS": "Natural Gas", "SNUG": "Natural Gas", "MINTARO": "Natural Gas",
    "DRY": "Natural Gas", "HASTING": "Natural Gas",
    # Hydro
    "MURRAY": "Hydro", "TUMUT": "Hydro", "SHOALH": "Hydro", "BLOWERING": "Hydro",
    "SNOWY": "Hydro", "SNWY": "Hydro",
    "GORDON": "Hydro", "POATINA": "Hydro", "REECE": "Hydro", "MACKNTSH": "Hydro",
    "TRIBUTE": "Hydro", "JOHN_BUT": "Hydro", "CETHANA": "Hydro",
    "DEVILS_G": "Hydro", "FISHER": "Hydro", "KING": "Hydro", "LEMONTH": "Hydro",
    "MEADOWB": "Hydro", "BASTYAN": "Hydro", "LIAPOOT": "Hydro",
    "DARTM": "Hydro", "EILDONFP": "Hydro", "WPOWERH": "Hydro",
    "KAREEYA": "Hydro", "BARRON": "Hydro", "WIVENHOE": "Hydro",
    "KIDSPH": "Hydro", "LI_WY_CA": "Hydro", "GOVILLB": "Hydro",
    # Interconnectors
    "BASSLINK": "Interconnector", "BLNK": "Interconnector",
    # Natural Gas (additional)
    "LONGFORD": "Natural Gas", "PIONEER": "Natural Gas",
    "MIDLDPS": "Natural Gas", "VICMILL": "Natural Gas",
    "PTINA": "Hydro",
    # Diesel
    "HALLET": "Diesel",
}


def load_registration_fuel_lookup() -> dict:
    """Load DUID→fuel_type mapping from NEM Registration List.

    Returns a dict mapping DUID to a standardised fuel type string.
    Falls back to an empty dict if the file is unavailable.
    """
    if not NEM_REG_LIST_PATH.exists():
        print("  WARNING: NEM Registration List not found — using heuristic classification only")
        return {}

    try:
        df = pd.read_excel(NEM_REG_LIST_PATH, sheet_name="PU and Scheduled Loads")
    except Exception as e:
        print(f"  WARNING: Could not parse NEM Registration List: {e}")
        return {}

    lookup = {}
    for _, row in df.iterrows():
        duid = str(row.get("DUID", "")).strip().replace("\n", "").replace("\r", "")
        if not duid or duid == "nan":
            continue

        primary = str(row.get("Fuel Source - Primary", "")).strip()
        descriptor = str(row.get("Fuel Source - Descriptor", "")).strip()

        # Try descriptor first (more specific), then primary
        fuel = REG_DESCRIPTOR_MAP.get(descriptor)
        if fuel is None:
            fuel = REG_FUEL_MAP.get(primary)

        # Skip entries with no fuel classification (e.g. interconnectors with NaN)
        if fuel is not None:
            lookup[duid] = fuel

    print(f"  Loaded fuel lookup for {len(lookup)} DUIDs from NEM Registration List")
    return lookup


def classify_fuel(row, reg_lookup: dict = None):
    """Classify a generator's fuel type.

    Priority: (1) NEM Registration List, (2) station name map,
              (3) DUID patterns, (4) dispatch type heuristics.
    """
    duid = str(row.get("DUID", "")).strip()
    station = str(row.get("STATIONID", "")).upper()
    dispatch_type = str(row.get("DISPATCHTYPE", ""))
    schedule_type = str(row.get("SCHEDULE_TYPE", ""))

    # Check for dummy generators (DG_NSW1, DG_QLD1, etc.)
    if station.startswith("DG_"):
        return "Dummy"

    # 0. Load and bidirectional dispatch types (before fuel source checks)
    if dispatch_type == "LOAD":
        return "Load"
    if dispatch_type == "BIDIRECTIONAL":
        return "Battery"

    # 1. Check NEM Registration List (authoritative)
    if reg_lookup and duid in reg_lookup:
        return reg_lookup[duid]

    # 2. Check station name prefix map (hand-curated fallback)
    for prefix, fuel in STATION_FUEL_MAP.items():
        if station.startswith(prefix.upper()):
            return fuel

    # 3. Check DUID suffix patterns
    duid_upper = duid.upper()
    for suffix, fuel in DUID_FUEL_PATTERNS.items():
        if duid_upper.endswith(suffix) or suffix in duid_upper:
            return fuel

    # Semi-scheduled generators are typically wind or solar
    if schedule_type == "SEMI-SCHEDULED":
        return "Wind/Solar (VRE)"

    return "Other"


FUEL_CATEGORIES = {
    "Black Coal": "Fossil",
    "Brown Coal": "Fossil",
    "Natural Gas": "Fossil",
    "Diesel": "Fossil",
    "Hydro": "Clean Baseload",
    "Wind": "VRE",
    "Solar": "VRE",
    "Wind/Solar (VRE)": "VRE",
    "Battery": "Storage",
    "Biomass": "Clean Baseload",
    "Interconnector": "Interconnector",
    "Load": "Load",
    "Dummy": "Dummy",
    "Other": "Other",
}


def load_aemo_pipeline() -> pd.DataFrame:
    """Load committed/proposed generators from the AEMO Gen Info workbook.

    Returns a DataFrame with the same schema as our generators output,
    or an empty DataFrame if the workbook is unavailable.
    """
    gen_info_path = RAW_DIR / "nem-generation-information-latest.xlsx"
    if not gen_info_path.exists():
        print("  No AEMO Gen Info workbook — skipping pipeline data")
        return pd.DataFrame()

    try:
        from etl.fetch_aemo import parse_generation_info
    except ImportError:
        sys.path.insert(0, str(BASE_DIR))
        from etl.fetch_aemo import parse_generation_info

    try:
        gen_df = parse_generation_info(gen_info_path)
    except Exception as e:
        print(f"  WARNING: Could not parse AEMO Gen Info workbook: {e}")
        return pd.DataFrame()

    # Keep only pipeline (committed + proposed)
    pipeline = gen_df[gen_df["status"].isin(["Committed", "Proposed"])].copy()
    if pipeline.empty:
        return pd.DataFrame()

    # Standardise to our schema
    result = pd.DataFrame({
        "duid": pipeline.get("duid", pd.Series(dtype=str)),
        "station_name": pipeline.get("station_name", pd.Series(dtype=str)),
        "nem_region": pipeline.get("nem_region", pd.Series(dtype=str)),
        "dispatch_type": "",
        "schedule_type": "",
        "fuel_type": pipeline.get("fuel_type", pd.Series(dtype=str)),
        "fuel_category": pipeline.get("fuel_category", pd.Series(dtype=str)),
        "nameplate_mw": pipeline.get("nameplate_mw", pd.Series(dtype=float)),
        "max_capacity_mw": pipeline.get("nameplate_mw", pd.Series(dtype=float)),
        "status": pipeline["status"],
    })

    return result


def fetch_regional_demand():
    """Fetch actual NEM demand by region via NEMOSIS DISPATCHREGIONSUM.

    Aggregates 5-min dispatch data to monthly averages per region.
    Saves to nem_demand_actual.parquet.
    """
    print("\n--- Fetching Actual NEM Demand ---")

    try:
        demand = dynamic_data_compiler(
            start_time="2020/01/01 00:00:00",
            end_time="2026/04/01 00:00:00",
            table_name="DISPATCHREGIONSUM",
            raw_data_location=str(CACHE_DIR),
            select_columns=["REGIONID", "TOTALDEMAND", "SETTLEMENTDATE"],
            fformat="csv",
        )
    except Exception as e:
        print(f"  WARNING: Could not fetch DISPATCHREGIONSUM: {e}")
        return

    print(f"  Fetched {len(demand):,} dispatch intervals")

    demand["SETTLEMENTDATE"] = pd.to_datetime(demand["SETTLEMENTDATE"])
    demand["TOTALDEMAND"] = pd.to_numeric(demand["TOTALDEMAND"], errors="coerce")
    demand["year_month"] = demand["SETTLEMENTDATE"].dt.to_period("M").astype(str)

    monthly = (
        demand.groupby(["REGIONID", "year_month"])
        .agg(
            avg_demand_mw=("TOTALDEMAND", "mean"),
            max_demand_mw=("TOTALDEMAND", "max"),
            intervals=("TOTALDEMAND", "count"),
        )
        .reset_index()
        .rename(columns={"REGIONID": "nem_region"})
    )

    # Compute monthly energy (TWh) = avg_MW * hours_in_month / 1e6
    monthly["hours"] = monthly["intervals"] * 5 / 60  # 5-min intervals
    monthly["energy_twh"] = monthly["avg_demand_mw"] * monthly["hours"] / 1_000_000

    out_path = PROCESSED_DIR / "nem_demand_actual.parquet"
    monthly.to_parquet(out_path, index=False)
    print(f"  Saved: {out_path.name} ({len(monthly)} rows)")

    # Annual summary
    monthly["year"] = pd.to_datetime(monthly["year_month"]).dt.year
    annual = monthly.groupby("year")["energy_twh"].sum()
    print("  Annual NEM demand (TWh):")
    for year, twh in annual.items():
        print(f"    {year}: {twh:.1f} TWh")


def fetch_and_build(skip_demand: bool = False):
    print("=" * 60)
    print("AEMO Grid Data via NEMOSIS")
    print("=" * 60)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 0. Load fuel lookup from NEM Registration List
    print("\n0. Loading fuel type lookup...")
    reg_lookup = load_registration_fuel_lookup()

    # 1. Fetch DUDETAILSUMMARY (region, station, schedule type)
    print("\n1. Fetching DUDETAILSUMMARY...")
    summary = dynamic_data_compiler(
        start_time="2026/01/01 00:00:00",
        end_time="2026/01/02 00:00:00",
        table_name="DUDETAILSUMMARY",
        raw_data_location=str(CACHE_DIR),
        select_columns="all",
        fformat="csv",
    )
    print(f"   {len(summary)} units from DUDETAILSUMMARY")

    # 2. Fetch DUDETAIL (registered capacity)
    print("\n2. Fetching DUDETAIL...")
    detail = dynamic_data_compiler(
        start_time="2026/01/01 00:00:00",
        end_time="2026/01/02 00:00:00",
        table_name="DUDETAIL",
        raw_data_location=str(CACHE_DIR),
        select_columns="all",
        fformat="csv",
    )

    detail["REGISTEREDCAPACITY"] = pd.to_numeric(detail["REGISTEREDCAPACITY"], errors="coerce")
    detail["MAXCAPACITY"] = pd.to_numeric(detail["MAXCAPACITY"], errors="coerce")
    detail_latest = detail.sort_values("EFFECTIVEDATE").drop_duplicates("DUID", keep="last")
    print(f"   {len(detail_latest)} unique DUIDs from DUDETAIL")

    # 3. Merge
    print("\n3. Merging...")
    merged = summary.merge(
        detail_latest[["DUID", "REGISTEREDCAPACITY", "MAXCAPACITY"]],
        on="DUID",
        how="left",
    )

    # 4. Classify fuel types using Registration List as primary source
    print("\n4. Classifying fuel types...")
    merged["fuel_type"] = merged.apply(lambda row: classify_fuel(row, reg_lookup), axis=1)
    merged["fuel_category"] = merged["fuel_type"].map(FUEL_CATEGORIES).fillna("Other")

    # 5. Build clean output
    generators = pd.DataFrame({
        "duid": merged["DUID"],
        "station_name": merged["STATIONID"],
        "nem_region": merged["REGIONID"],
        "dispatch_type": merged["DISPATCHTYPE"],
        "schedule_type": merged["SCHEDULE_TYPE"],
        "fuel_type": merged["fuel_type"],
        "fuel_category": merged["fuel_category"],
        "nameplate_mw": merged["REGISTEREDCAPACITY"],
        "max_capacity_mw": merged["MAXCAPACITY"],
        "status": "Operating",  # MMS only has registered (operating) generators
    })

    # 6. Add pipeline (committed/proposed) from AEMO Gen Info workbook
    print("\n5. Loading generation pipeline...")
    pipeline = load_aemo_pipeline()
    if not pipeline.empty:
        print(f"   Added {len(pipeline)} pipeline generators ({pipeline['status'].value_counts().to_dict()})")
        generators = pd.concat([generators, pipeline], ignore_index=True)

    # Exclude loads, dummy generators, and interconnectors from capacity summary
    gen_only = generators[~generators["fuel_category"].isin(["Load", "Dummy", "Interconnector"])]

    # 7. Build grid_capacity summary
    grid_capacity = (
        gen_only.groupby(["nem_region", "fuel_category", "status"])
        .agg(
            capacity_mw=("nameplate_mw", "sum"),
            num_stations=("station_name", "nunique"),
        )
        .reset_index()
    )
    grid_capacity["capacity_mw"] = grid_capacity["capacity_mw"].round(1)

    # 8. Save
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    gen_path = PROCESSED_DIR / "generation_info.parquet"
    generators.to_parquet(gen_path, index=False)
    print(f"\n   Saved: {gen_path.name} ({len(generators)} rows)")

    grid_path = PROCESSED_DIR / "grid_capacity.parquet"
    grid_capacity.to_parquet(grid_path, index=False)
    print(f"   Saved: {grid_path.name} ({len(grid_capacity)} rows)")

    # 9. Fetch actual demand (M4)
    if not skip_demand:
        fetch_regional_demand()

    # 10. Summary
    print("\n" + "=" * 60)
    print("Summary — Generation Capacity")
    print("=" * 60)

    operating = gen_only[gen_only["status"] == "Operating"]
    print("\nOperating — By Region:")
    for region in sorted(operating["nem_region"].unique()):
        rdf = operating[operating["nem_region"] == region]
        print(f"  {region}: {rdf['nameplate_mw'].sum():,.0f} MW ({len(rdf)} units)")

    print(f"\nOperating — By Fuel Category:")
    for cat, mw in operating.groupby("fuel_category")["nameplate_mw"].sum().sort_values(ascending=False).items():
        print(f"  {cat}: {mw:,.0f} MW")

    total = operating["nameplate_mw"].sum()
    print(f"\nTotal Operating Capacity: {total:,.0f} MW")

    # Pipeline summary
    pipeline_data = gen_only[gen_only["status"].isin(["Committed", "Proposed"])]
    if not pipeline_data.empty:
        print(f"\nPipeline — Committed + Proposed:")
        for status, group in pipeline_data.groupby("status"):
            print(f"  {status}: {group['nameplate_mw'].sum():,.0f} MW ({len(group)} generators)")

    other_mw = gen_only[gen_only["fuel_category"] == "Other"]["nameplate_mw"].sum()
    if other_mw > 0:
        print(f"\n  NOTE: {other_mw:,.0f} MW still classified as 'Other'")

    print("\nDone.")


if __name__ == "__main__":
    skip_demand = "--skip-demand" in sys.argv
    fetch_and_build(skip_demand=skip_demand)
