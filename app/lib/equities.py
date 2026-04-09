"""Mag 7 + AI infrastructure equities — prices via Yahoo spark, fundamentals via yfinance."""

import logging

import pandas as pd
import streamlit as st
import yfinance as yf

from app.lib.yahoo_spark import run_spark, compute_returns_from_closes, _format_price

logger = logging.getLogger("ai_research")

MAG7_AI_STOCKS = [
    {"symbol": "AAPL",  "name": "Apple",         "group": "Mag 7"},
    {"symbol": "MSFT",  "name": "Microsoft",      "group": "Mag 7"},
    {"symbol": "GOOGL", "name": "Alphabet",       "group": "Mag 7"},
    {"symbol": "AMZN",  "name": "Amazon",         "group": "Mag 7"},
    {"symbol": "NVDA",  "name": "NVIDIA",         "group": "Mag 7"},
    {"symbol": "META",  "name": "Meta",           "group": "Mag 7"},
    {"symbol": "TSLA",  "name": "Tesla",          "group": "Mag 7"},
    {"symbol": "ORCL",  "name": "Oracle",         "group": "AI Infra"},
    {"symbol": "AMD",   "name": "AMD",            "group": "AI Infra"},
    {"symbol": "TSM",   "name": "TSMC",           "group": "AI Infra"},
    {"symbol": "PLTR",  "name": "Palantir",       "group": "AI Infra"},
    {"symbol": "EQIX",  "name": "Equinix",        "group": "DC Operators"},
    {"symbol": "DLR",   "name": "Digital Realty",  "group": "DC Operators"},
    {"symbol": "AMT",   "name": "American Tower",  "group": "DC Operators"},
]

# Tickers to fetch earnings calendar for
EARNINGS_TICKERS = ["MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSM", "EQIX", "DLR"]


# ANZ region tickers for earnings calendar
ANZ_EARNINGS_TICKERS = [
    {"symbol": "NXT.AX", "name": "NextDC", "region": "ANZ"},
    {"symbol": "IFT.NZ", "name": "Infratil (CDC)", "region": "ANZ"},
    {"symbol": "MQG.AX", "name": "Macquarie Group", "region": "ANZ"},
    {"symbol": "GMG.AX", "name": "Goodman Group", "region": "ANZ"},
]


def _extract_earnings_date(cal) -> str | None:
    """Extract earnings date from yfinance calendar response (DataFrame or dict)."""
    if cal is None:
        return None
    if isinstance(cal, pd.DataFrame) and not cal.empty:
        return str(cal.iloc[0, 0]) if cal.shape[1] > 0 else None
    if isinstance(cal, dict):
        ed = cal.get("Earnings Date")
        if isinstance(ed, list) and ed:
            return str(ed[0])
        if ed:
            return str(ed)
    return None


@st.cache_data(ttl=3600)
def fetch_earnings_dates(tickers: tuple[str, ...]) -> dict[str, str | None]:
    """Fetch next earnings date for an arbitrary list of tickers.

    Tuple argument so the Streamlit cache key is hashable.
    """
    results: dict[str, str | None] = {}
    for sym in tickers:
        try:
            t = yf.Ticker(sym)
            results[sym] = _extract_earnings_date(t.calendar)
        except Exception as e:
            logger.debug("Earnings %s error: %s", sym, e)
            results[sym] = None
    return results


@st.cache_data(ttl=3600)
def fetch_earnings_calendar() -> list[dict]:
    """Fetch next earnings dates for key hyperscalers and DC operators."""
    dates = fetch_earnings_dates(tuple(EARNINGS_TICKERS))
    return [{"ticker": sym, "earnings_date": dates.get(sym)} for sym in EARNINGS_TICKERS]


def _fetch_fundamentals(symbols: list[str]) -> dict:
    results = {}
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            pe_t = info.get("trailingPE")
            pe_f = info.get("forwardPE")
            eps_t = info.get("trailingEps")
            eps_f = info.get("forwardEps")
            w52h = info.get("fiftyTwoWeekHigh")
            pct_from_high = None
            if price and w52h and w52h != 0:
                pct_from_high = round((price / w52h - 1) * 100, 2)

            rev_growth = None
            capex_yoy = None
            try:
                inc = t.income_stmt
                if inc is not None and not inc.empty and "Total Revenue" in inc.index and inc.shape[1] >= 2:
                    rev_curr = inc.loc["Total Revenue"].iloc[0]
                    rev_prev = inc.loc["Total Revenue"].iloc[1]
                    if rev_prev and rev_prev != 0:
                        rev_growth = round((rev_curr / rev_prev - 1) * 100, 1)

                cf = t.cashflow
                if cf is not None and not cf.empty and "Capital Expenditure" in cf.index and cf.shape[1] >= 2:
                    capex_curr = abs(cf.loc["Capital Expenditure"].iloc[0])
                    capex_prev = abs(cf.loc["Capital Expenditure"].iloc[1])
                    if capex_prev and capex_prev != 0:
                        capex_yoy = round((capex_curr / capex_prev - 1) * 100, 1)
            except Exception:
                pass

            results[sym] = {
                "market_cap": info.get("marketCap"),
                "pe_trailing": round(pe_t, 2) if pe_t else None,
                "pe_forward": round(pe_f, 2) if pe_f else None,
                "eps_trailing": round(eps_t, 2) if eps_t else None,
                "eps_forward": round(eps_f, 2) if eps_f else None,
                "pct_from_high": pct_from_high,
                "rev_growth_yoy": rev_growth,
                "capex_yoy": capex_yoy,
            }
        except Exception as e:
            logger.debug("Fundamentals %s error: %s", sym, e)
            results[sym] = {}
    return results


@st.cache_data(ttl=300)
def fetch_equities_data() -> list[dict]:
    symbols = [s["symbol"] for s in MAG7_AI_STOCKS]

    spark_data = run_spark(symbols, time_range="10y")
    fundamentals = _fetch_fundamentals(symbols)

    stocks = []
    for entry in MAG7_AI_STOCKS:
        sym = entry["symbol"]
        sd = spark_data.get(sym)
        fund = fundamentals.get(sym, {})

        if sd and sd["closes"] and len(sd["closes"]) >= 2:
            price = sd["closes"][-1]
            prev = sd["closes"][-2]
            change_pct = round((price / prev - 1) * 100, 2) if prev else None
            returns = compute_returns_from_closes(sd["closes"])
        else:
            price = None
            change_pct = None
            returns = {}

        stocks.append({
            **entry,
            "price": _format_price(price),
            "change_pct": change_pct,
            "returns": returns,
            "market_cap": fund.get("market_cap"),
            "pe_trailing": fund.get("pe_trailing"),
            "pe_forward": fund.get("pe_forward"),
            "eps_trailing": fund.get("eps_trailing"),
            "eps_forward": fund.get("eps_forward"),
            "pct_from_high": fund.get("pct_from_high"),
            "rev_growth_yoy": fund.get("rev_growth_yoy"),
            "capex_yoy": fund.get("capex_yoy"),
        })

    return stocks
