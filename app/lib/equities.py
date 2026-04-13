"""Mag 7 + AI infrastructure equities — prices via Yahoo spark, fundamentals via yfinance."""

from __future__ import annotations

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


def _fetch_one_fundamental(sym: str) -> tuple[str, dict]:
    try:
        t = yf.Ticker(sym)

        # fast_info is more reliable on Streamlit Cloud than t.info
        fi = t.fast_info
        price = getattr(fi, "last_price", None)
        market_cap = getattr(fi, "market_cap", None)
        w52h = getattr(fi, "year_high", None)
        w52l = getattr(fi, "year_low", None)

        # Try t.info as fallback for fields fast_info doesn't have
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass

        pe_t = info.get("trailingPE")
        pe_f = info.get("forwardPE")
        eps_t = info.get("trailingEps")
        eps_f = info.get("forwardEps")
        target_1y = info.get("targetMeanPrice")

        # Prefer fast_info values, fall back to info
        if market_cap is None:
            market_cap = info.get("marketCap")
        if price is None:
            price = info.get("currentPrice") or info.get("regularMarketPrice")
        if w52h is None:
            w52h = info.get("fiftyTwoWeekHigh")
        if w52l is None:
            w52l = info.get("fiftyTwoWeekLow")

        # Compute PE from price + EPS in financial statements if info failed
        if pe_t is None or eps_t is None:
            try:
                inc = t.income_stmt
                bs = t.balance_sheet
                if inc is not None and not inc.empty and bs is not None and not bs.empty:
                    ni_row = None
                    for label in ("Net Income", "Net Income Common Stockholders"):
                        if label in inc.index:
                            ni_row = label
                            break
                    shares_row = None
                    for label in ("Ordinary Shares Number", "Share Issued"):
                        if label in bs.index:
                            shares_row = label
                            break
                    if ni_row and shares_row:
                        ni = float(inc.loc[ni_row].iloc[0])
                        shares = float(bs.loc[shares_row].iloc[0])
                        if shares and shares > 0:
                            computed_eps = ni / shares
                            if eps_t is None:
                                eps_t = round(computed_eps, 2)
                            if pe_t is None and price and computed_eps and computed_eps != 0:
                                pe_t = round(price / computed_eps, 2)
            except Exception:
                pass

        # Try analyst_price_targets if target_1y is still None
        if target_1y is None:
            try:
                ptgt = t.analyst_price_targets or {}
                target_1y = ptgt.get("mean") or ptgt.get("median")
            except Exception:
                pass

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

        return sym, {
            "market_cap": market_cap,
            "pe_trailing": round(pe_t, 2) if pe_t else None,
            "pe_forward": round(pe_f, 2) if pe_f else None,
            "eps_trailing": round(eps_t, 2) if eps_t else None,
            "eps_forward": round(eps_f, 2) if eps_f else None,
            "week52_low": w52l,
            "week52_high": w52h,
            "target_mean_1y": target_1y,
            "pct_from_high": pct_from_high,
            "rev_growth_yoy": rev_growth,
            "capex_yoy": capex_yoy,
        }
    except Exception as e:
        logger.debug("Fundamentals %s error: %s", sym, e)
        return sym, {}


def _fetch_fundamentals(symbols: list[str]) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_one_fundamental, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym, data = future.result()
            results[sym] = data
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
            "week52_low": fund.get("week52_low"),
            "week52_high": fund.get("week52_high"),
            "target_mean_1y": fund.get("target_mean_1y"),
            "pct_from_high": fund.get("pct_from_high"),
            "rev_growth_yoy": fund.get("rev_growth_yoy"),
            "capex_yoy": fund.get("capex_yoy"),
        })

    return stocks
