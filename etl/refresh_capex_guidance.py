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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.lib.capex_guidance_meta import select_forward_row  # noqa: E402
from app.lib.run_result import (  # noqa: E402
    final_status,
    now_iso,
    read_log_record,
    write_log_record,
)

DATA_DIR = Path(__file__).parent.parent / "data" / "reference"
GUIDANCE_PATH = DATA_DIR / "capex_guidance.csv"
HISTORY_PATH = DATA_DIR / "capex_guidance_history.csv"
STALE_PATH = Path(__file__).parent.parent / "data" / "stale_guidance.json"
LOG_PATH = Path(__file__).parent.parent / "data" / "fetcher_log.json"

LOOKBACK_DAYS = 14


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


def main() -> int:
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else LOOKBACK_DAYS
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback)).date()

    print(f"Checking capex guidance staleness (lookback: {lookback} days, cutoff: {cutoff})...")

    guidance_rows = load_guidance()
    tickers = sorted(set(row["ticker"] for row in guidance_rows))
    print(f"  Tracking {len(tickers)} tickers: {', '.join(tickers)}")

    stale = []
    fresh = []
    quarterly_actuals = []
    unknown_earnings = []

    for ticker in tickers:
        last_earnings = get_last_earnings_date(ticker)
        if last_earnings is None:
            # Unknown is not current: the ticker must not be counted as fresh.
            print(f"  {ticker}: could not determine last earnings date")
            unknown_earnings.append(ticker)
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

            # Find the forward-looking guidance row: the open (non-actual)
            # row whose period ends latest, selected by period end — never by
            # string-maxing the fiscal_year label (CY2026 sorts before FY2025,
            # which would pick a closed period as the "forward" row).
            fy_row = select_forward_row(ticker_rows) or {}

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

    assessed = len(stale) + len(fresh)
    attempted = assessed + len(unknown_earnings)
    status = final_status(attempted - len(unknown_earnings), attempted)

    # Observation coverage: newest embedded earnings date actually assessed
    # (empty when nothing was assessed — absence of data is not freshness).
    assessed_dates = [s["last_earnings_date"] for s in stale] + [
        str(r) for r in (
            get_last_earnings_date(t) for t in fresh
        )
    ]
    coverage_latest = max(assessed_dates) if assessed_dates else None

    if status == "error":
        # Every lookup failed (or nothing was assessable): keep the previous
        # stale_guidance.json untouched so last-good survives, log honestly,
        # and fail the run. The old "All guidance is current" on total outage
        # is exactly the failure this replaces.
        previous = read_log_record(LOG_PATH, "refresh_capex_guidance.py")
        print(
            "\nAll earnings lookups failed (or no ticker was assessable) — "
            "stale_guidance.json left untouched "
            f"(previous run: {previous.get('last_success') or 'never succeeded'})."
        )
        write_log_record(
            LOG_PATH,
            "refresh_capex_guidance.py",
            status="error",
            attempted=attempted,
            succeeded=attempted - len(unknown_earnings),
            observations=assessed,
            notes=(
                f"{len(unknown_earnings)}/{attempted} earnings lookups failed; "
                f"stale_guidance.json preserved"
            ),
            count=assessed,
        )
        return 2

    # Write stale_guidance.json
    output = {
        "schema_version": 2,
        "checked_at": now_iso(),
        "lookback_days": lookback,
        "cutoff": str(cutoff),
        "status": status,
        "attempted": attempted,
        "succeeded": attempted - len(unknown_earnings),
        "tickers_tracked": len(tickers),
        "newest_observed_earnings_date": coverage_latest,
        "unknown_earnings": unknown_earnings,
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
    elif fresh:
        print(
            f"All assessed guidance is current as of newest observed earnings "
            f"{coverage_latest} — no updates needed."
        )
    else:
        print(
            "No ticker was assessable in this window (none reported within the "
            f"{lookback}-day lookback). This is not proof of freshness."
        )

    if unknown_earnings:
        print(
            f"\nWARNING: earnings date unknown for {len(unknown_earnings)} "
            f"ticker(s): {', '.join(unknown_earnings)} — excluded from the "
            f"fresh/stale assessment."
        )

    print(
        f"\nDone [{status}]. {len(stale)} stale, {len(fresh)} current, "
        f"{len(unknown_earnings)} unknown, {len(quarterly_actuals)} quarterly "
        f"actuals fetched; newest observed earnings {coverage_latest or 'n/a'}."
    )

    write_log_record(
        LOG_PATH,
        "refresh_capex_guidance.py",
        status=status,
        attempted=attempted,
        succeeded=attempted - len(unknown_earnings),
        observations=assessed,
        notes=(
            f"{len(stale)} stale, {len(fresh)} current, "
            f"{len(unknown_earnings)} unknown; newest observed earnings "
            f"{coverage_latest or 'n/a'}"
        ),
        count=assessed,
    )
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
