"""Refresh earnings_dates.csv from FMP API.

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

from app.lib.fmp import get_earnings_dates, get_fmp_key

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


def _next_earnings_date(symbol: str) -> str | None:
    """Return the next upcoming earnings date for a symbol via FMP."""
    today = datetime.now().date()
    try:
        events = get_earnings_dates(symbol)
        # FMP returns most recent first — find the next upcoming date
        future = [
            e["date"] for e in events
            if e.get("date") and e["date"] >= today.isoformat()
        ]
        if future:
            return min(future)  # earliest upcoming
    except Exception as e:
        logger.warning("  %s: FMP error — %s", symbol, e)
    return None


def main() -> None:
    if not get_fmp_key():
        logger.error("No FMP API key found — set FMP_API_KEY or add to ~/.openbb_platform/user_settings.json")
        raise SystemExit(1)

    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))

    tickers = [r["symbol"] for r in rows]
    old_dates = {r["symbol"]: r["earnings_date"] for r in rows}

    logger.info("Refreshing earnings dates for %d tickers via FMP...", len(tickers))

    updated = []
    changes = 0

    for ticker in tickers:
        date_str = _next_earnings_date(ticker)
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
