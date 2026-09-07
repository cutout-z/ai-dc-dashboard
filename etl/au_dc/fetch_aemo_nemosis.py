"""Fetch AEMO grid data via NEMOSIS (nemweb.com.au MMS tables).

This bypasses aemo.com.au Cloudflare protection by pulling from the
MMS data archives on nemweb.com.au. We combine DUDETAILSUMMARY (region,
station) with DUDETAIL (registered capacity) and the NEM Registration
List (fuel source) to produce the grid_capacity.parquet file.

Also integrates the AEMO Generation Information workbook (if available)
for committed/proposed generation pipeline data.

Source horizons are resolved dynamically, never hard-coded (S2-08):

- The registration snapshot (DUDETAILSUMMARY/DUDETAIL) is taken as of the
  first instant of the *latest published AEMO MMS archive month* — a
  publication-lag candidate advanced by the clock, confirmed by the archive
  actually returning data (bounded backstep when the newest month is not out
  yet). A run can never silently re-serve the January-2026 snapshot again.
- Demand (DISPATCHREGIONSUM) refreshes incrementally: only months after the
  last month already present in ``nem_demand_actual.parquet`` are fetched
  (up to the latest published archive month), never a replay of the full
  history. ``--full-demand-backfill`` keeps an explicit full rebuild path.
- Every output records its source vintage in a ``<file>.parquet.vintage.json``
  sidecar (archive month, registration snapshot date, workbook edition), so a
  rewritten file is never mistaken for advanced source coverage.
"""

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from nemosis import dynamic_data_compiler

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if __package__ in (None, ""):
    # Allow running as a plain script (python etl/au_dc/fetch_aemo_nemosis.py)
    # while keeping package imports for the test suite.
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.au_dc.aemo_horizon import (  # noqa: E402
    Month,
    add_months,
    day2_instant,
    first_instant,
    latest_candidate_month,
    max_month,
    month_label,
    parse_month_label,
    registration_snapshot_date,
    window_month_keys,
)
from etl.au_dc.source_vintage import (  # noqa: E402
    vintage_dict,
    write_parquet_with_vintage,
)

AU_DC_DIR = PROJECT_ROOT / "data" / "au_dc"
CACHE_DIR = AU_DC_DIR / "raw" / "aemo" / "nemosis_cache"
PROCESSED_DIR = AU_DC_DIR / "processed"
RAW_DIR = AU_DC_DIR / "raw" / "aemo"

#: Registration/demand snapshot horizon rules (see aemo_horizon docstring).
PUBLICATION_LAG_DAYS = 10
#: How many months the snapshot resolver walks back from the lag candidate
#: when the newest archive month is not actually published yet.
ARCHIVE_BACKSTEP_MAX = 3
#: Full-history demand rebuild origin (kept from the original fetch window).
DEMAND_HISTORY_START: Month = (2020, 1)

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


def _file_edition_meta(path: Path) -> dict | None:
    """Identity marker for a manually downloaded source file (edition record).

    Parsing an old workbook again does not refresh its publication vintage, so
    the vintage sidecar records *which* file edition supplied the pipeline rows
    (name, mtime, short sha256) instead of implying it is current.
    """
    if path is None or not Path(path).exists():
        return None
    p = Path(path)
    import hashlib
    from datetime import datetime, timezone

    digest = None
    try:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except OSError:
        pass
    meta = {
        "file": p.name,
        "file_mtime_utc": datetime.fromtimestamp(
            p.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }
    if digest:
        meta["sha256_prefix"] = digest
    return meta


def load_aemo_pipeline() -> tuple[pd.DataFrame, dict | None]:
    """Load committed/proposed generators from the AEMO Gen Info workbook.

    Returns (DataFrame with the same schema as our generators output, or an
    empty DataFrame if the workbook is unavailable) and (edition metadata for
    the workbook that supplied the rows, or None when nothing was parsed).
    """
    gen_info_path = RAW_DIR / "nem-generation-information-latest.xlsx"
    if not gen_info_path.exists():
        print("  No AEMO Gen Info workbook — skipping pipeline data")
        return pd.DataFrame(), None

    try:
        from etl.au_dc.fetch_aemo import parse_generation_info
    except ImportError:
        sys.path.insert(0, str(PROJECT_ROOT))
        from etl.au_dc.fetch_aemo import parse_generation_info

    try:
        gen_df = parse_generation_info(gen_info_path)
        edition_meta = _file_edition_meta(gen_info_path)
    except Exception as e:
        print(f"  WARNING: Could not parse AEMO Gen Info workbook: {e}")
        return pd.DataFrame(), None

    # Keep only pipeline (committed + proposed)
    pipeline = gen_df[gen_df["status"].isin(["Committed", "Proposed"])].copy()
    if pipeline.empty:
        return pd.DataFrame(), edition_meta

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

    return result, edition_meta


DEMAND_TABLE = "DISPATCHREGIONSUM"
DEMAND_PATH = PROCESSED_DIR / "nem_demand_actual.parquet"


def _read_existing_demand_months(out_path: Path) -> list[Month] | None:
    """Months present in an existing demand parquet (ascending); None when absent/unreadable."""
    out_path = Path(out_path)
    if not out_path.exists():
        return None
    try:
        existing = pd.read_parquet(out_path)
    except Exception as e:  # unreadable — cannot trust last-present
        print(f"  WARNING: could not read existing {out_path.name}: {e}")
        return None
    if existing is None or existing.empty or "year_month" not in existing.columns:
        return None
    months: list[Month] = []
    for raw in sorted(existing["year_month"].dropna().unique()):
        parsed = parse_month_label(str(raw))
        if parsed is not None:
            months.append(parsed)
    return months or None


def _aggregate_demand_rows(raw: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw DISPATCHREGIONSUM rows to the monthly schema.

    Mirrors the original aggregation exactly (same column maths, same
    unshifted month bucketing) so appended rows stay numerically comparable
    with the historical series.
    """
    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["nem_region", "year_month", "avg_demand_mw", "max_demand_mw",
                     "intervals", "hours", "energy_twh"]
        )
    df = raw.copy()
    df["SETTLEMENTDATE"] = pd.to_datetime(df["SETTLEMENTDATE"], errors="coerce")
    df["TOTALDEMAND"] = pd.to_numeric(df["TOTALDEMAND"], errors="coerce")
    df = df.dropna(subset=["SETTLEMENTDATE"])
    df["year_month"] = df["SETTLEMENTDATE"].dt.to_period("M").astype(str)

    monthly = (
        df.groupby(["REGIONID", "year_month"])
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
    return monthly


def _contiguous_last_month(months: list[Month], history_start: Month) -> Month | None:
    """Last month of the contiguous run starting at ``history_start``.

    AEMO monthly archives are contiguous, so any hole in the stored series is
    a fetch artifact that the next incremental run should backfill. Planning
    from the *contiguous* last month (not the global max) makes a transient
    partial download self-heal: months behind the newest present month get
    re-requested until the run is whole again.
    """
    expected = history_start
    last_contiguous: Month | None = None
    for m in sorted(months):
        if m == expected:
            last_contiguous = m
            expected = add_months(expected, 1)
        elif m > expected:
            break  # hole at `expected`
        # m < expected: duplicate/superseded month — ignore
    return last_contiguous


def _plan_demand_window(
    out_path: Path,
    today: date,
    full_backfill: bool,
) -> dict:
    """Decide which archive months a demand run must fetch.

    Incremental (default): only months after the last *contiguous* month
    already present in the output parquet are fetched, up to the latest
    publication-lag candidate month — complete missing months, never a replay
    of the full history. Full backfill: from DEMAND_HISTORY_START. Returns
    ``{start_month, horizon, mode}`` with mode one of
    ``incremental``/``full``/``noop`` (noop = series already through the
    candidate month).
    """
    horizon = latest_candidate_month(today, PUBLICATION_LAG_DAYS)
    if full_backfill:
        return {"start_month": DEMAND_HISTORY_START, "horizon": horizon, "mode": "full"}
    existing_months = _read_existing_demand_months(out_path)
    last_present = (
        _contiguous_last_month(existing_months, DEMAND_HISTORY_START)
        if existing_months else None
    )
    if last_present is None:
        # No trustworthy contiguous series yet — full history is the only
        # correct first build (also self-heals a file that starts late).
        return {"start_month": DEMAND_HISTORY_START, "horizon": horizon, "mode": "full"}
    start_month = add_months(last_present, 1)
    if start_month > horizon:
        return {"start_month": start_month, "horizon": horizon, "mode": "noop"}
    return {"start_month": start_month, "horizon": horizon, "mode": "incremental"}


def fetch_regional_demand(full_backfill: bool = False, today: date | None = None) -> dict | None:
    """Fetch actual NEM demand by region via NEMOSIS DISPATCHREGIONSUM.

    Publication-lag-aware and incremental: only archive months after the last
    month already in ``nem_demand_actual.parquet`` are requested (or the full
    2020+ history when ``full_backfill`` is set / no series exists yet). The
    output and its vintage sidecar are only written when the run actually
    advanced or rebuilt the series; a failed fetch leaves the previous file
    untouched (last-good preserved).
    """
    today = today or date.today()
    print("\n--- Fetching Actual NEM Demand ---")

    plan = _plan_demand_window(DEMAND_PATH, today, full_backfill)
    if plan["mode"] == "noop":
        print(
            f"  Demand series already extends through "
            f"{month_label(plan['horizon'])} (latest candidate archive); nothing to fetch."
        )
        return None

    start_month, horizon = plan["start_month"], plan["horizon"]
    start_time = first_instant(start_month)
    end_time = first_instant(add_months(horizon, 1))
    requested = window_month_keys(start_month, horizon)
    print(
        f"  Horizon: latest candidate archive month {month_label(horizon)} "
        f"(publication lag {PUBLICATION_LAG_DAYS}d); fetch mode {plan['mode']}"
    )
    print(f"  Requesting months {requested[0]}..{requested[-1]} ({len(requested)} month(s))")

    try:
        demand = dynamic_data_compiler(
            start_time=start_time,
            end_time=end_time,
            table_name=DEMAND_TABLE,
            raw_data_location=str(CACHE_DIR),
            select_columns=["REGIONID", "TOTALDEMAND", "SETTLEMENTDATE"],
            fformat="csv",
        )
    except Exception as e:
        print(f"  WARNING: Could not fetch DISPATCHREGIONSUM: {e}")
        return None
    if demand is None or demand.empty:
        print("  WARNING: fetch returned no dispatch intervals — leaving existing series untouched")
        return None

    print(f"  Fetched {len(demand):,} dispatch intervals")
    monthly = _aggregate_demand_rows(demand)
    monthly = monthly[
        monthly["year_month"].between(requested[0], requested[-1])
    ].copy()
    if monthly.empty:
        print("  WARNING: no complete archive months in the requested window — series untouched")
        return None

    if plan["mode"] == "incremental":
        existing = pd.read_parquet(DEMAND_PATH)
        kept = existing[existing["year_month"] < requested[0]]
        result = pd.concat([kept, monthly], ignore_index=True)
        result = result.drop_duplicates(
            subset=["nem_region", "year_month"], keep="last"
        )
        result = result.sort_values(["nem_region", "year_month"]).reset_index(drop=True)
    else:
        result = monthly.sort_values(["nem_region", "year_month"]).reset_index(drop=True)

    out_path = DEMAND_PATH
    data_through = max_month(result["year_month"]) if len(result) else None
    vintage = vintage_dict(
        out_path.name,
        source_tables=[DEMAND_TABLE],
        extra={
            "series_kind": "actual monthly averages (historical; never projected)",
            "fetch_mode": plan["mode"],
            "data_through_month": month_label(data_through) if data_through else None,
            # The newest month actually present in the output is the honest
            # vintage: if the candidate month's archive was not published yet,
            # data_through trails the horizon and the sidecar says so.
            "archive_month": month_label(data_through) if data_through else None,
        },
        row_count=len(result),
    )
    write_parquet_with_vintage(result, out_path, vintage)
    print(f"  Saved: {out_path.name} ({len(result)} rows, through {vintage['data_through_month']})")

    # Annual summary
    result["year"] = pd.to_datetime(result["year_month"]).dt.year
    annual = result.groupby("year")["energy_twh"].sum()
    print("  Annual NEM demand (TWh):")
    for year, twh in annual.items():
        print(f"    {int(year)}: {twh:.1f} TWh")
    return vintage


def _fetch_summary_snapshot(month: Month, cache_dir: Path) -> pd.DataFrame:
    """DUDETAILSUMMARY rows for the registration state at the first instant of ``month``.

    As-of window reproduces the original fixed snapshot (day 1 00:00 → day 2
    00:00): rows whose START_DATE/END_DATE interval covers the first instant of
    the archive month. Raises/returns empty when the archive is not published.
    """
    return dynamic_data_compiler(
        start_time=first_instant(month),
        end_time=day2_instant(month),
        table_name="DUDETAILSUMMARY",
        raw_data_location=str(cache_dir),
        select_columns="all",
        fformat="csv",
    )


def _resolve_snapshot_month(cache_dir: Path, today: date | None = None) -> tuple[Month, pd.DataFrame]:
    """Resolve the newest published archive month and fetch its registration summary.

    Starts at the publication-lag candidate month for ``today`` and walks back
    at most ARCHIVE_BACKSTEP_MAX months while the archive yields no data (a
    not-yet-published release makes nemosis log "not downloaded" and return
    nothing — never a false claim). The month that actually produced data is
    the returned snapshot month; outputs must record it as their vintage. When
    no month in the window yields data the run fails loudly (fail closed)
    rather than silently re-serving an older snapshot.
    """
    candidate = latest_candidate_month(today or date.today(), PUBLICATION_LAG_DAYS)
    tried: list[str] = []
    month: Month = candidate
    for _ in range(ARCHIVE_BACKSTEP_MAX + 1):
        tried.append(month_label(month))
        try:
            summary = _fetch_summary_snapshot(month, cache_dir)
        except Exception as e:
            print(f"  WARNING: DUDETAILSUMMARY fetch for {month_label(month)} failed: {e}")
            summary = None
        if summary is not None and len(summary) > 0:
            return month, summary
        print(
            f"  WARNING: no registration data published for archive month "
            f"{month_label(month)} — stepping back one month"
        )
        month = add_months(month, -1)
    raise RuntimeError(
        "No published AEMO MMS archive found for the registration snapshot: tried "
        + ", ".join(tried)
        + f" (candidate from today {today or date.today()} with publication lag "
        f"{PUBLICATION_LAG_DAYS}d). Refusing to re-serve an older snapshot silently."
    )


def _fetch_detail_latest(month: Month, cache_dir: Path) -> pd.DataFrame:
    """DUDETAIL rows (registered capacity) with the latest EFFECTIVEDATE per DUID.

    Same as-of semantics as the original query: capacity changes effective
    before the second instant of ``month``, newest version per DUID kept.
    """
    detail = dynamic_data_compiler(
        start_time=first_instant(month),
        end_time=day2_instant(month),
        table_name="DUDETAIL",
        raw_data_location=str(cache_dir),
        select_columns="all",
        fformat="csv",
    )
    detail["REGISTEREDCAPACITY"] = pd.to_numeric(detail["REGISTEREDCAPACITY"], errors="coerce")
    detail["MAXCAPACITY"] = pd.to_numeric(detail["MAXCAPACITY"], errors="coerce")
    detail_latest = detail.sort_values("EFFECTIVEDATE").drop_duplicates("DUID", keep="last")
    return detail_latest


def fetch_and_build(
    skip_demand: bool = False,
    full_demand_backfill: bool = False,
    today: date | None = None,
):
    print("=" * 60)
    print("AEMO Grid Data via NEMOSIS")
    print("=" * 60)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 0. Load fuel lookup from NEM Registration List
    print("\n0. Loading fuel type lookup...")
    reg_lookup = load_registration_fuel_lookup()

    # 1. Resolve the latest published archive month and fetch the registration
    #    snapshot (DUDETAILSUMMARY) as of its first instant — never a hard-coded
    #    window again (S2-08).
    print("\n1. Resolving latest published AEMO MMS archive month...")
    snapshot_month, summary = _resolve_snapshot_month(CACHE_DIR, today=today)
    print(
        f"   Registration snapshot as of {registration_snapshot_date(snapshot_month)} "
        f"(archive month {month_label(snapshot_month)})"
    )
    print(f"   {len(summary)} units from DUDETAILSUMMARY")

    # 2. Fetch DUDETAIL (registered capacity) for the same snapshot month
    print("\n2. Fetching DUDETAIL...")
    detail_latest = _fetch_detail_latest(snapshot_month, CACHE_DIR)
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

    # 6. Add pipeline (committed/proposed) from AEMO Gen Info workbook.
    #    The workbook's edition is recorded separately — re-parsing an old
    #    manual download does not refresh its publication vintage (S2-08).
    print("\n5. Loading generation pipeline...")
    pipeline, workbook_meta = load_aemo_pipeline()
    if not pipeline.empty:
        print(f"   Added {len(pipeline)} pipeline generators ({pipeline['status'].value_counts().to_dict()})")
        generators = pd.concat([generators, pipeline], ignore_index=True)
    if workbook_meta is not None:
        print(f"   Pipeline workbook edition: {workbook_meta['file']}")

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

    # 8. Save — each output carries its source-vintage sidecar (archive month,
    #    registration snapshot date, workbook edition), so a rewritten file is
    #    never mistaken for advanced source coverage (S2-08).
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_label = month_label(snapshot_month)
    snapshot_date = registration_snapshot_date(snapshot_month)

    gen_path = PROCESSED_DIR / "generation_info.parquet"
    gen_vintage = vintage_dict(
        gen_path.name,
        source_tables=["DUDETAILSUMMARY", "DUDETAIL"],
        extra={
            "registration_snapshot": snapshot_date,
            "archive_month": snapshot_label,
            "pipeline_workbook": workbook_meta,
        },
        row_count=len(generators),
    )
    write_parquet_with_vintage(generators, gen_path, gen_vintage)
    print(f"\n   Saved: {gen_path.name} ({len(generators)} rows; snapshot {snapshot_date})")

    grid_path = PROCESSED_DIR / "grid_capacity.parquet"
    grid_vintage = vintage_dict(
        grid_path.name,
        source_tables=["DUDETAILSUMMARY", "DUDETAIL"],
        extra={
            "registration_snapshot": snapshot_date,
            "archive_month": snapshot_label,
            "pipeline_workbook": workbook_meta,
        },
        row_count=len(grid_capacity),
    )
    write_parquet_with_vintage(grid_capacity, grid_path, grid_vintage)
    print(f"   Saved: {grid_path.name} ({len(grid_capacity)} rows; snapshot {snapshot_date})")

    # 9. Fetch actual demand (publication-lag-aware incremental by default;
    #    --skip-demand/--no-demand keeps the legacy skip; --full-demand-backfill
    #    keeps the explicit full-history rebuild path).
    if not skip_demand:
        fetch_regional_demand(full_backfill=full_demand_backfill, today=today)

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
    skip_demand = "--skip-demand" in sys.argv or "--no-demand" in sys.argv
    full_demand_backfill = "--full-demand-backfill" in sys.argv
    if skip_demand and full_demand_backfill:
        print("ERROR: --skip-demand/--no-demand and --full-demand-backfill are mutually exclusive")
        sys.exit(2)
    fetch_and_build(skip_demand=skip_demand, full_demand_backfill=full_demand_backfill)
