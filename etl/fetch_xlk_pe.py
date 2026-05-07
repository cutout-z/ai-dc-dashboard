"""Fetch S&P 500 trailing P/E history from Robert Shiller's online dataset.

Usage:
    python etl/fetch_xlk_pe.py

Source: Robert Shiller (Yale) — ie_data.xls (updated monthly).
Data: S&P 500 composite trailing P/E = Price / 12-month trailing EPS, 1871–present.
Filtered to 1995–present for the dashboard chart.

Note: This is the BROAD S&P 500 — not InfoTech-specific. The InfoTech sector
historically trades at a significant premium to the broad index (roughly 1.5–2x
the broad P/E at cycle peaks). Sector-specific historical forward P/E is paywalled
(Bloomberg/FactSet). This is the best free, verifiable proxy available.

Output: data/reference/sp500_pe.csv
  columns: date (YYYY-MM-DD), trailing_pe, source
"""

import io
import sys
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent.parent / "data" / "reference"
OUT_PATH = DATA_DIR / "sp500_pe.csv"

SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
START_YEAR = 1995


def fetch_sp500_pe() -> None:
    print("Fetching S&P 500 P/E from Shiller data (Yale)...")
    try:
        resp = requests.get(SHILLER_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  HTTP error: {e}")
        sys.exit(1)

    try:
        df = pd.read_excel(io.BytesIO(resp.content), sheet_name="Data", header=7)
    except Exception as e:
        print(f"  Excel parse error: {e}")
        sys.exit(1)

    # Date is numeric YYYY.MM (e.g. 1995.01 = Jan 1995, 1995.1 = Oct 1995)
    df["Date"] = pd.to_numeric(df["Date"], errors="coerce")
    df["P"] = pd.to_numeric(df["P"], errors="coerce")
    df["E"] = pd.to_numeric(df["E"], errors="coerce")
    df = df.dropna(subset=["Date", "P", "E"])
    df = df[df["E"] > 0]  # guard against divide-by-zero
    df = df[df["Date"] >= START_YEAR]

    # Parse YYYY.MM format → first of month
    def _parse_date(d: float) -> str:
        year = int(d)
        # fractional part .01 = Jan, .10 = Oct, .1 = Oct (same)
        frac = round((d - year) * 100)
        month = max(1, min(12, frac if frac > 0 else 1))
        return f"{year}-{month:02d}-01"

    df["date"] = df["Date"].apply(_parse_date)
    df["trailing_pe"] = (df["P"] / df["E"]).round(2)
    df["source"] = "Robert Shiller / Yale ie_data.xls — S&P 500 trailing P/E"

    out = df[["date", "trailing_pe", "source"]].sort_values("date").drop_duplicates("date")
    out.to_csv(OUT_PATH, index=False)

    latest = out.iloc[-1]
    print(f"  Wrote {len(out)} months to {OUT_PATH}")
    print(f"  Date range: {out['date'].min()} → {out['date'].max()}")
    print(f"  Latest: {latest['date']}  P/E = {latest['trailing_pe']:.1f}x")
    print(f"  Dot-com peak (2000): ~{out[out['date'].str.startswith('2000')]['trailing_pe'].max():.1f}x")


if __name__ == "__main__":
    fetch_sp500_pe()
