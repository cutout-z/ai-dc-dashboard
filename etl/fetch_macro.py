"""Fetch macro data for bubble gauges — GDP from FRED, funding deals from news.

Usage:
    python etl/fetch_macro.py              # update GDP only
    python etl/fetch_macro.py --deals      # also scan for new funding deals

GDP source: FRED API (key from macOS Keychain 'fred-api-key' or OpenBB config).
Fallback: FRED public CSV endpoint (no key needed, less reliable).
"""

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent.parent / "data" / "reference"

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"


def _get_fred_key() -> str | None:
    """Retrieve FRED API key from Keychain → OpenBB config → None."""
    # 1. macOS Keychain
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "fred-api-key", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    # 2. OpenBB user_settings.json
    openbb_path = Path.home() / ".openbb_platform" / "user_settings.json"
    if openbb_path.exists():
        try:
            data = json.loads(openbb_path.read_text())
            key = data.get("credentials", {}).get("fred_api_key")
            if key:
                return key
        except Exception:
            pass

    return None


# ── GDP from FRED ────────────────────────────────────────────

def _fetch_gdp_api(api_key: str) -> list[dict] | None:
    """Fetch annual GDP via official FRED API."""
    params = {
        "series_id": "GDPA",
        "api_key": api_key,
        "file_type": "json",
        "observation_start": "2019-01-01",
        "sort_order": "asc",
    }
    resp = requests.get(FRED_API_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for obs in data.get("observations", []):
        if obs["value"] == ".":
            continue
        rows.append({
            "year": int(obs["date"][:4]),
            "gdp_nominal_bn": round(float(obs["value"]), 1),
            "source": "FRED API series GDPA (BEA NIPA)",
        })
    return rows if rows else None


def _fetch_gdp_csv() -> list[dict] | None:
    """Fallback: fetch from FRED public CSV endpoint (no key needed)."""
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        "?id=GDPA&cosd=2019-01-01&coed=2030-12-01"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    reader = csv.DictReader(lines)

    rows = []
    for row in reader:
        rows.append({
            "year": int(row["observation_date"][:4]),
            "gdp_nominal_bn": round(float(row["GDPA"]), 1),
            "source": "FRED series GDPA (BEA NIPA)",
        })
    return rows if rows else None


def fetch_gdp():
    """Fetch annual GDP from FRED (API key preferred, CSV fallback)."""
    api_key = _get_fred_key()
    rows = None

    if api_key:
        print("Fetching GDP from FRED API (key found)...")
        try:
            rows = _fetch_gdp_api(api_key)
        except Exception as e:
            print(f"  FRED API failed: {e} — falling back to CSV endpoint")

    if not rows:
        print("Fetching GDP from FRED CSV endpoint (no key)...")
        try:
            rows = _fetch_gdp_csv()
        except Exception as e:
            print(f"  CSV endpoint also failed: {e}")
            return

    if not rows:
        print("  No data returned from FRED.")
        return

    out = DATA_DIR / "us_gdp_annual.csv"
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    print(f"  Wrote {len(df)} years to {out}")
    print(f"  Latest: {df.iloc[-1]['year']} — ${df.iloc[-1]['gdp_nominal_bn'] / 1000:.1f}T")


# ── Funding deals ────────────────────────────────────────────

DEAL_SCHEMA = [
    "date", "entity", "amount_bn", "type", "is_circular",
    "counterparty", "source", "notes",
]


def scan_for_new_deals():
    """Placeholder for future AI-powered deal scanning.

    This will eventually use the news RSS feeds already in the dashboard
    to detect new AI funding/debt deals and prompt for confirmation
    before appending to funding_deals.csv.

    For now, prints instructions for manual update.
    """
    deals_path = DATA_DIR / "funding_deals.csv"
    df = pd.read_csv(deals_path)
    latest_date = pd.to_datetime(df["date"]).max().strftime("%Y-%m-%d")

    print(f"\nFunding deals CSV has {len(df)} deals (latest: {latest_date})")
    print("\nTo add a new deal, append a row to data/reference/funding_deals.csv:")
    print(f"  Columns: {', '.join(DEAL_SCHEMA)}")
    print("  type: equity | debt | ipo | balance_sheet | hybrid")
    print("  is_circular: true if investor is also major customer/supplier")
    print("\nOr run the /ai-research skill which will scan news for new deals.")


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch macro data for bubble gauges")
    parser.add_argument("--deals", action="store_true", help="Also check for new funding deals")
    args = parser.parse_args()

    fetch_gdp()

    if args.deals:
        scan_for_new_deals()
    else:
        print("\nTip: Run with --deals to check funding_deals.csv status.")


if __name__ == "__main__":
    main()
