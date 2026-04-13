"""Refresh analyst consensus data and save as JSON for Streamlit Cloud.

Run locally before pushing to update consensus estimates. Uses yfinance
which handles Yahoo auth automatically.

Usage:
    python etl/refresh_consensus.py
"""

from __future__ import annotations

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OUT_PATH = Path(__file__).parent.parent / "data" / "reference" / "consensus.json"

COMPANIES = {
    "AAPL":  {"name": "Apple",           "ccy_scale": 1.0},
    "MSFT":  {"name": "Microsoft",       "ccy_scale": 1.0},
    "GOOGL": {"name": "Alphabet",        "ccy_scale": 1.0},
    "AMZN":  {"name": "Amazon",          "ccy_scale": 1.0},
    "NVDA":  {"name": "NVIDIA",          "ccy_scale": 1.0},
    "META":  {"name": "Meta",            "ccy_scale": 1.0},
    "TSLA":  {"name": "Tesla",           "ccy_scale": 1.0},
    "ORCL":  {"name": "Oracle",          "ccy_scale": 1.0},
    "AMD":   {"name": "AMD",             "ccy_scale": 1.0},
    "TSM":   {"name": "TSMC",            "ccy_scale": 1 / 32.0},
    "PLTR":  {"name": "Palantir",        "ccy_scale": 1.0},
    "EQIX":  {"name": "Equinix",        "ccy_scale": 1.0},
    "DLR":   {"name": "Digital Realty",  "ccy_scale": 1.0},
    "AMT":   {"name": "American Tower",  "ccy_scale": 1.0},
}


def _fetch_one(ticker: str, ccy_scale: float) -> tuple[str, dict]:
    scale = ccy_scale / 1e6
    try:
        t = yf.Ticker(ticker)

        rev_est = t.revenue_estimate
        eps_est = t.earnings_estimate
        ptgt = t.analyst_price_targets or {}

        def _get(df, period, col):
            try:
                if df is None or df.empty:
                    return None
                v = df.loc[period, col]
                return float(v) if pd.notna(v) else None
            except (KeyError, TypeError):
                return None

        def _s(v):
            return round(v * scale, 1) if v is not None else None

        def _p(key):
            v = ptgt.get(key)
            try:
                return round(float(v), 2) if v is not None and pd.notna(v) else None
            except (TypeError, ValueError):
                return None

        result = {
            "rev_0y_avg":  _s(_get(rev_est, "0y", "avg")),
            "rev_0y_low":  _s(_get(rev_est, "0y", "low")),
            "rev_0y_high": _s(_get(rev_est, "0y", "high")),
            "rev_1y_avg":  _s(_get(rev_est, "+1y", "avg")),
            "rev_1y_low":  _s(_get(rev_est, "+1y", "low")),
            "rev_1y_high": _s(_get(rev_est, "+1y", "high")),
            "rev_n":       int(_get(rev_est, "0y", "numberOfAnalysts") or 0) or None,
            "rev_growth":  _get(rev_est, "+1y", "growth"),
            "eps_0y_avg":  _get(eps_est, "0y", "avg"),
            "eps_1y_avg":  _get(eps_est, "+1y", "avg"),
            "eps_n":       int(_get(eps_est, "0y", "numberOfAnalysts") or 0) or None,
            "pt_current": _p("current"),
            "pt_mean":    _p("mean"),
            "pt_low":     _p("low"),
            "pt_high":    _p("high"),
        }

        has_data = any(v is not None for k, v in result.items() if k not in ("rev_n", "eps_n"))
        if has_data:
            logger.info(f"  {ticker}: OK (pt_mean={result.get('pt_mean')})")
            return ticker, result
        else:
            logger.warning(f"  {ticker}: no data returned")
            return ticker, {}

    except Exception as e:
        logger.warning(f"  {ticker}: error — {e}")
        return ticker, {}


def main():
    logger.info("Fetching analyst consensus for %d companies...", len(COMPANIES))

    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_fetch_one, ticker, meta["ccy_scale"]): ticker
            for ticker, meta in COMPANIES.items()
        }
        for future in as_completed(futures):
            ticker, data = future.result()
            if data:
                results[ticker] = data

    output = {
        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": results,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2))
    logger.info("Wrote %d companies to %s", len(results), OUT_PATH)


if __name__ == "__main__":
    main()
