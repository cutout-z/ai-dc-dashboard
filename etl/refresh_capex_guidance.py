"""Refresh capex guidance staleness after earnings reports.

Checks which tracked companies reported earnings recently, fetches their
latest quarterly capex actuals from yfinance, and flags stale guidance
entries that need updating via web research.

Writes data/stale_guidance.json for the skill runner to pick up. If any
tickers are stale, the skill launches a web research agent to find the
updated guidance figures.

Usage:
    python etl/refresh_capex_guidance.py          # default 14-day lookback
    python etl/refresh_capex_guidance.py 30        # 30-day lookback
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "reference"
GUIDANCE_PATH = DATA_DIR / "capex_guidance.csv"
HISTORY_PATH = DATA_DIR / "capex_guidance_history.csv"
STALE_PATH = Path(__file__).parent.parent / "data" / "stale_guidance.json"
LOG_PATH = Path(__file__).parent.parent / "data" / "fetcher_log.json"

LOOKBACK_DAYS = 14


def _write_log(status: str, count: int, notes: str = "") -> None:
    try:
        log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {}
    except Exception:
        log = {}
    log["refresh_capex_guidance.py"] = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "count": count,
        "notes": notes,
    }
    LOG_PATH.write_text(json.dumps(log, indent=2))


def load_guidance() -> list[dict]:
    with open(GUIDANCE_PATH) as f:
        return list(csv.DictReader(f))


def get_last_earnings_date(ticker_symbol: str) -> datetime | None:
    """Get the most recent past earnings date for a ticker."""
    try:
        t = yf.Ticker(ticker_symbol)
        ed = t.earnings_dates
        if ed is None or ed.empty:
            return None
        now = pd.Timestamp.now(tz="America/New_York")
        past = ed[ed.index <= now]
        if past.empty:
            return None
        return past.index.max().to_pydatetime().date()
    except Exception as e:
        logger.warning("  %s: could not fetch earnings dates — %s", ticker_symbol, e)
        return None


def get_quarterly_capex(ticker_symbol: str) -> tuple[str | None, float | None]:
    """Fetch latest quarterly capex actual from yfinance cash flow statement.

    Returns (quarter_end_date, capex_usd_b) or (None, None).
    """
    try:
        t = yf.Ticker(ticker_symbol)
        cf = t.quarterly_cashflow
        if cf is None or cf.empty:
            return None, None

        capex_row = None
        for label in ["Capital Expenditure", "CapitalExpenditure"]:
            if label in cf.index:
                capex_row = cf.loc[label]
                break

        if capex_row is None:
            return None, None

        latest_date = cf.columns[0]
        val = capex_row.iloc[0]
        if pd.isna(val):
            return None, None

        capex_b = round(abs(float(val)) / 1e9, 2)
        return str(latest_date.date()), capex_b
    except Exception as e:
        logger.warning("  %s: could not fetch quarterly capex — %s", ticker_symbol, e)
        return None, None


def main() -> None:
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else LOOKBACK_DAYS
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback)).date()

    print(f"Checking capex guidance staleness (lookback: {lookback} days, cutoff: {cutoff})...")

    guidance_rows = load_guidance()
    tickers = sorted(set(row["ticker"] for row in guidance_rows))
    print(f"  Tracking {len(tickers)} tickers: {', '.join(tickers)}")

    stale = []
    fresh = []
    quarterly_actuals = []

    for ticker in tickers:
        last_earnings = get_last_earnings_date(ticker)
        if last_earnings is None:
            print(f"  {ticker}: could not determine last earnings date")
            continue

        # Fetch latest quarterly capex
        q_date, q_capex = get_quarterly_capex(ticker)
        if q_date and q_capex:
            quarterly_actuals.append({
                "ticker": ticker,
                "quarter_end": q_date,
                "capex_usd_b": q_capex,
            })

        if last_earnings < cutoff:
            print(f"  {ticker}: last reported {last_earnings} (before cutoff)")
            continue

        print(f"  {ticker}: last reported {last_earnings} (recent)")

        # Check if guidance CSV already reflects this earnings date
        ticker_rows = [r for r in guidance_rows if r["ticker"] == ticker]
        latest_guidance_date = max(
            (r["guidance_date"] for r in ticker_rows if r.get("guidance_date")),
            default="1970-01-01",
        )
        gdate = datetime.strptime(latest_guidance_date, "%Y-%m-%d").date()

        if gdate >= last_earnings:
            print(f"    -> guidance already current ({latest_guidance_date})")
            fresh.append(ticker)
        else:
            print(f"    -> STALE: guidance from {latest_guidance_date}, earnings on {last_earnings}")

            company = next((r["company"] for r in ticker_rows), ticker)

            # Find the forward-looking guidance row (highest fiscal year)
            fy_row = max(
                ticker_rows,
                key=lambda r: r.get("fiscal_year", ""),
                default={},
            )

            stale.append({
                "ticker": ticker,
                "company": company,
                "last_earnings_date": str(last_earnings),
                "last_guidance_date": latest_guidance_date,
                "fiscal_year": fy_row.get("fiscal_year", ""),
                "fy_end_month": fy_row.get("fy_end_month", ""),
                "prior_guidance_usd_b": fy_row.get("guidance_usd_b", ""),
                "prior_low": fy_row.get("guidance_low", ""),
                "prior_high": fy_row.get("guidance_high", ""),
                "q_capex_usd_b": q_capex if q_date else None,
                "search_query": (
                    f"{company} {fy_row.get('fiscal_year', '')} earnings "
                    f"capex capital expenditure guidance {last_earnings}"
                ),
            })

    # Write stale_guidance.json
    output = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": lookback,
        "cutoff": str(cutoff),
        "stale_tickers": stale,
        "fresh_tickers": fresh,
        "quarterly_actuals": quarterly_actuals,
    }

    STALE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STALE_PATH.write_text(json.dumps(output, indent=2))

    # Summary
    print()
    if quarterly_actuals:
        print("Quarterly capex actuals (latest):")
        for qa in quarterly_actuals:
            print(f"  {qa['ticker']}: ${qa['capex_usd_b']}B (Q ending {qa['quarter_end']})")

    print()
    if stale:
        print(f"{len(stale)} tickers need guidance refresh:")
        for s in stale:
            prior = s["prior_guidance_usd_b"]
            low, high = s["prior_low"], s["prior_high"]
            range_str = f"${low}-{high}B" if low and high else f"${prior}B"
            print(
                f"  {s['ticker']} ({s['company']}): {s['fiscal_year']} "
                f"prior {range_str}, reported {s['last_earnings_date']}"
            )
        print(f"\nWrote {STALE_PATH}")
    else:
        print("All guidance is current — no updates needed.")

    total = len(stale) + len(fresh)
    print(f"\nDone. {len(stale)} stale, {len(fresh)} current, "
          f"{len(quarterly_actuals)} quarterly actuals fetched.")

    _write_log("ok", total, f"{len(stale)} stale, {len(fresh)} current")


if __name__ == "__main__":
    main()
