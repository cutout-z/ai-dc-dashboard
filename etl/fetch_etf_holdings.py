"""Build ETF universe for the Prospecting page.

Fetches top holdings from CHAT, AIQ, BOTZ, ROBT via yfinance,
enriches each ticker with sector/market cap from yfinance info,
and scores by ETF overlap count (AI Tier: Core ≥3, High = 2, Moderate = 1).

Output: data/processed/etf_universe.json
Usage:
    python etl/fetch_etf_holdings.py
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ETF_TICKERS = ["AIQ", "BOTZ", "ROBT", "CHAT"]

OUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "etf_universe.json"
LOG_PATH = Path(__file__).parent.parent / "data" / "fetcher_log.json"

COUNTRY_TO_REGION: dict[str, str] = {
    "United States": "North America",
    "Canada": "North America",
    "Japan": "Asia-Pacific",
    "South Korea": "Asia-Pacific",
    "Taiwan": "Asia-Pacific",
    "China": "Asia-Pacific",
    "Australia": "Asia-Pacific",
    "India": "Asia-Pacific",
    "Hong Kong": "Asia-Pacific",
    "Singapore": "Asia-Pacific",
    "United Kingdom": "Europe",
    "Germany": "Europe",
    "Netherlands": "Europe",
    "France": "Europe",
    "Switzerland": "Europe",
    "Sweden": "Europe",
    "Finland": "Europe",
    "Denmark": "Europe",
    "Israel": "Other",
    "Brazil": "Other",
}


def _write_log(status: str, count: int, notes: str = "") -> None:
    try:
        log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {}
    except Exception:
        log = {}
    log["fetch_etf_holdings.py"] = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "count": count,
        "notes": notes,
    }
    LOG_PATH.write_text(json.dumps(log, indent=2))


def fetch_etf_top_holdings(etf: str) -> list[str]:
    """Return ticker symbols from an ETF's top holdings via yfinance."""
    t = yf.Ticker(etf)

    # Primary: funds_data (yfinance ≥ 0.2.36)
    try:
        fd = t.funds_data
        holdings = fd.top_holdings
        if holdings is not None and not holdings.empty:
            tickers = [str(s).strip() for s in holdings.index.tolist() if s]
            logger.info("  %s: %d holdings via funds_data", etf, len(tickers))
            return tickers
    except Exception as e:
        logger.warning("  %s: funds_data failed (%s), trying info...", etf, e)

    # Fallback: info['holdings']
    try:
        holdings_list = t.info.get("holdings", [])
        if holdings_list:
            tickers = [h.get("symbol", "").strip() for h in holdings_list if h.get("symbol")]
            logger.info("  %s: %d holdings via info fallback", etf, len(tickers))
            return tickers
    except Exception as e:
        logger.warning("  %s: info fallback failed: %s", etf, e)

    return []


def enrich_ticker(ticker: str) -> dict | None:
    """Fetch sector, market cap, name for one ticker."""
    try:
        info = yf.Ticker(ticker).info
        country = info.get("country", "")
        region = COUNTRY_TO_REGION.get(country, "Other" if country else "Unknown")
        mkt_cap = (info.get("marketCap") or 0) / 1e6
        return {
            "ticker": ticker,
            "company": info.get("longName") or info.get("shortName", ticker),
            "country": country,
            "region": region,
            "gics_sector": info.get("sector", ""),
            "gics_industry": info.get("industry", ""),
            "market_cap_usd_m": round(mkt_cap, 1),
        }
    except Exception as e:
        logger.warning("  enrich %s: %s", ticker, e)
        return None


def main() -> None:
    logger.info("Fetching ETF holdings for: %s", ", ".join(ETF_TICKERS))

    # Step 1: collect holdings per ETF
    ticker_etfs: dict[str, list[str]] = defaultdict(list)
    for etf in ETF_TICKERS:
        holdings = fetch_etf_top_holdings(etf)
        for h in holdings:
            if h:
                ticker_etfs[h].append(etf)
        time.sleep(0.5)

    if not ticker_etfs:
        logger.error("No holdings found across any ETF. Aborting.")
        _write_log("error", 0, "No holdings returned from any ETF")
        return

    all_tickers = sorted(ticker_etfs.keys())
    logger.info("\nEnriching %d unique tickers...", len(all_tickers))

    # Step 2: enrich each ticker
    records = []
    for i, ticker in enumerate(all_tickers):
        enriched = enrich_ticker(ticker)
        if enriched:
            etf_list = sorted(ticker_etfs[ticker])
            etf_count = len(etf_list)
            ai_tier = "Core" if etf_count >= 3 else "High" if etf_count == 2 else "Moderate"
            enriched.update({"etf_count": etf_count, "etfs_in": etf_list, "ai_tier": ai_tier})
            records.append(enriched)

        if (i + 1) % 10 == 0:
            logger.info("  ... %d / %d done", i + 1, len(all_tickers))
            time.sleep(1)

    records.sort(key=lambda r: r["market_cap_usd_m"], reverse=True)

    output = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "etfs": ETF_TICKERS,
        "ticker_count": len(records),
        "universe": records,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2))
    logger.info("\nSaved %d tickers → %s", len(records), OUT_PATH)
    _write_log("ok", len(records), f"Holdings from {len(ETF_TICKERS)} ETFs: {', '.join(ETF_TICKERS)}")


if __name__ == "__main__":
    main()
