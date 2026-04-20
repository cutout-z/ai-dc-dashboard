"""Live financial data for ASX-listed AU DC operators.

Cached with a 5-minute TTL so the Company Analysis page always shows
current data without needing a manual ETL run.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
import yfinance as yf

logger = logging.getLogger("ai_research")

# "ASX:NXT" format (used as primary key) → yfinance ticker
AU_DC_TICKERS = [
    {"ticker": "ASX:NXT", "yf": "NXT.AX"},
    {"ticker": "ASX:GMG", "yf": "GMG.AX"},
    {"ticker": "ASX:MAQ", "yf": "MAQ.AX"},
]


@st.cache_data(ttl=300)
def fetch_asx_dc_quotes() -> pd.DataFrame:
    """Fetch current quotes + fundamentals for AU DC operators. TTL 5 min."""
    rows = []
    for entry in AU_DC_TICKERS:
        try:
            info = yf.Ticker(entry["yf"]).info
            rows.append({
                "ticker": entry["ticker"],
                "name": info.get("shortName", entry["ticker"]),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "revenue_growth": info.get("revenueGrowth"),
                "profit_margin": info.get("profitMargins"),
                "debt_to_equity": info.get("debtToEquity"),
                "beta": info.get("beta"),
                "dividend_yield": info.get("dividendYield"),
            })
        except Exception as e:
            logger.warning("fetch_asx_dc_quotes %s: %s", entry["yf"], e)
            rows.append({"ticker": entry["ticker"], "name": entry["ticker"]})
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def fetch_asx_dc_history(period: str = "1y", interval: str = "1wk") -> pd.DataFrame:
    """Fetch weekly price history for AU DC operators. TTL 5 min."""
    frames = []
    for entry in AU_DC_TICKERS:
        try:
            hist = yf.Ticker(entry["yf"]).history(period=period, interval=interval)
            if hist.empty:
                continue
            hist = hist.reset_index()[["Date", "Close"]]
            hist["ticker"] = entry["ticker"]
            hist = hist.rename(columns={"Date": "date", "Close": "close"})
            frames.append(hist)
        except Exception as e:
            logger.warning("fetch_asx_dc_history %s: %s", entry["yf"], e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
