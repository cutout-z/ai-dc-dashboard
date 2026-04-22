"""Refresh earnings_dates.csv from yfinance calendar data.

Run locally before pushing to update next earnings dates for all tracked tickers.
Writes a log entry to data/fetcher_log.json on completion.

Usage:
    python etl/refresh_earnings_dates.py
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent.parent / "data" / "reference" / "earnings_dates.csv"
LOG_PATH = Path(__file__).parent.parent / "data" / "fetcher_log.json"


def _write_log(status: str, count: int, notes: str = "") -> None:
    try:
        log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {}
    except Exception:
        log = {}
    log["refresh_earnings_dates.py"] = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "count": count,
        "notes": notes,
    }
    LOG_PATH.write_text(json.dumps(log, indent=2))


def main() -> None:
    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))

    tickers = [r["symbol"] for r in rows]
    old_dates = {r["symbol"]: r["earnings_date"] for r in rows}

    logger.info("Refreshing earnings dates for %d tickers...", len(tickers))

    updated = []
    changes = 0

    for ticker in tickers:
        date_str: str | None = None
        try:
            cal = yf.Ticker(ticker).calendar
            if isinstance(cal, dict):
                # Newer yfinance: calendar is a dict
                eds = cal.get("Earnings Date")
                if eds is not None:
                    if hasattr(eds, "__iter__") and not isinstance(eds, str):
                        eds_list = [e for e in eds if e is not None]
                        if eds_list:
                            date_str = pd.Timestamp(eds_list[0]).strftime("%Y-%m-%d")
                    else:
                        date_str = pd.Timestamp(eds).strftime("%Y-%m-%d")
            elif hasattr(cal, "columns"):
                # Older yfinance: calendar is a DataFrame
                if "Earnings Date" in cal.columns:
                    vals = cal.loc["Earnings Date"].dropna()
                    if len(vals):
                        date_str = pd.Timestamp(vals.iloc[0]).strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning("  %s: error — %s", ticker, e)

        new_date = date_str or old_dates.get(ticker, "")
        if date_str and date_str != old_dates.get(ticker):
            logger.info("  %s: %s → %s", ticker, old_dates.get(ticker), date_str)
            changes += 1
        else:
            logger.info("  %s: %s (unchanged)", ticker, new_date)

        updated.append({"symbol": ticker, "earnings_date": new_date})

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "earnings_date"])
        writer.writeheader()
        writer.writerows(updated)

    logger.info("\nDone. %d changed, %d total → %s", changes, len(updated), CSV_PATH)
    _write_log("ok", len(updated), f"{changes} dates changed")


if __name__ == "__main__":
    main()
