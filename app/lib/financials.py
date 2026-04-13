"""
financials.py — yfinance financial statements for the Financial (key players) page.

All companies fetched via yfinance annual income_stmt / cashflow / balance_sheet.
Last 4 fiscal years. Values in $M USD.
"""
from __future__ import annotations
import logging
from pathlib import Path

import pandas as pd
import streamlit as st
import yfinance as yf
import openpyxl

logger = logging.getLogger("ai_research")

_EXCEL_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "AI Bubble Project"
    / "Hyperscalers_3Statement_Model.xlsx"
)

# ── Company registry ─────────────────────────────────────────────────────────

COMPANY_META: dict[str, dict] = {
    "AAPL":  {"name": "Apple",           "group": "Mag 7",        "ccy_scale": 1.0},
    "MSFT":  {"name": "Microsoft",       "group": "Mag 7",        "ccy_scale": 1.0},
    "GOOGL": {"name": "Alphabet",        "group": "Mag 7",        "ccy_scale": 1.0},
    "AMZN":  {"name": "Amazon",          "group": "Mag 7",        "ccy_scale": 1.0},
    "NVDA":  {"name": "NVIDIA",          "group": "Mag 7",        "ccy_scale": 1.0},
    "META":  {"name": "Meta",            "group": "Mag 7",        "ccy_scale": 1.0},
    "TSLA":  {"name": "Tesla",           "group": "Mag 7",        "ccy_scale": 1.0},
    "ORCL":  {"name": "Oracle",          "group": "AI Infra",     "ccy_scale": 1.0},
    "AMD":   {"name": "AMD",             "group": "AI Infra",     "ccy_scale": 1.0},
    "TSM":   {"name": "TSMC",            "group": "AI Infra",     "ccy_scale": 1 / 32.0},
    "PLTR":  {"name": "Palantir",        "group": "AI Infra",     "ccy_scale": 1.0},
    "EQIX":  {"name": "Equinix",         "group": "DC Operators", "ccy_scale": 1.0},
    "DLR":   {"name": "Digital Realty",  "group": "DC Operators", "ccy_scale": 1.0},
    "AMT":   {"name": "American Tower",  "group": "DC Operators", "ccy_scale": 1.0},
}

COMPANY_ORDER = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "ORCL", "AMD", "TSM", "PLTR",
    "EQIX", "DLR", "AMT",
]


# ════════════════════════════════════════════════════════════════════════════
# AI Supplement — disclosure quality table (reads Excel if available)
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def load_ai_supplement() -> list[dict]:
    """Extract AI revenue proxy / disclosure-quality table from AI_Supplement sheet."""
    if not _EXCEL_PATH.exists():
        return []
    wb = openpyxl.load_workbook(str(_EXCEL_PATH), data_only=True)
    ws = wb["AI_Supplement"]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]

    hdr_idx = next(
        (i for i, r in enumerate(rows) if r[0] == "Company" and r[6] == "Disclosure Quality"),
        None,
    )
    if hdr_idx is None:
        return []

    records = []
    current_company = None
    for row in rows[hdr_idx + 1:]:
        if all(v is None for v in row):
            break
        if row[0] is not None:
            current_company = row[0]
        records.append({
            "Company":            current_company,
            "Metric":             row[1],
            "FY2024A":            row[2],
            "FY2025E":            row[3],
            "FY2026E":            row[4],
            "FY2027E":            row[5],
            "Disclosure Quality": row[6],
            "Source / Notes":     row[7],
        })
    return records


# ════════════════════════════════════════════════════════════════════════════
# yfinance helpers
# ════════════════════════════════════════════════════════════════════════════

def _yf_val(df: pd.DataFrame | None, *labels, n: int = 4, scale: float = 1.0) -> tuple[list, list]:
    """Return (values, year_labels) for the first matching label in df.

    df columns are Timestamps; sorted oldest-first, last n taken.
    scale converts raw units → $M.
    """
    if df is None or df.empty:
        return [None] * n, []
    df_s = df.sort_index(axis=1).iloc[:, -n:]
    yrs = [c.strftime("FY%Y") for c in df_s.columns]
    for label in labels:
        if label in df_s.index:
            return [
                round(float(v) * scale, 1) if pd.notna(v) else None
                for v in df_s.loc[label]
            ], yrs
    return [None] * len(yrs), yrs


def _fetch_consensus(t: yf.Ticker, scale: float, ticker: str) -> dict:
    """Fetch broker consensus estimates (revenue, EPS, price targets).

    scale should be ccy_scale/1e6 to convert revenue estimates → $M.
    EPS and price targets are not scaled (per-share / per-unit).
    """
    try:
        rev_est  = t.revenue_estimate   # DataFrame: index=period, cols=avg/low/high/...
        eps_est  = t.earnings_estimate
        ptgt     = t.analyst_price_targets or {}   # dict: current/mean/low/high/median

        def _get(df, period, col):
            try:
                if df is None or df.empty:
                    return None
                v = df.loc[period, col]
                return float(v) if pd.notna(v) else None
            except (KeyError, TypeError):
                return None

        def _s(v):
            """Scale a revenue value to $M."""
            return round(v * scale, 1) if v is not None else None

        def _p(key):
            v = ptgt.get(key)
            try:
                return round(float(v), 2) if v is not None and pd.notna(v) else None
            except (TypeError, ValueError):
                return None

        return {
            # Revenue consensus ($M after scale)
            "rev_0y_avg":  _s(_get(rev_est, "0y", "avg")),
            "rev_0y_low":  _s(_get(rev_est, "0y", "low")),
            "rev_0y_high": _s(_get(rev_est, "0y", "high")),
            "rev_1y_avg":  _s(_get(rev_est, "+1y", "avg")),
            "rev_1y_low":  _s(_get(rev_est, "+1y", "low")),
            "rev_1y_high": _s(_get(rev_est, "+1y", "high")),
            "rev_n":       int(_get(rev_est, "0y", "numberOfAnalysts") or 0) or None,
            "rev_growth":  _get(rev_est, "+1y", "growth"),
            # EPS consensus (per share, no scale)
            "eps_0y_avg":  _get(eps_est, "0y", "avg"),
            "eps_1y_avg":  _get(eps_est, "+1y", "avg"),
            "eps_n":       int(_get(eps_est, "0y", "numberOfAnalysts") or 0) or None,
            # Price targets (USD)
            "pt_current": _p("current"),
            "pt_mean":    _p("mean"),
            "pt_low":     _p("low"),
            "pt_high":    _p("high"),
        }
    except Exception as e:
        logger.warning("consensus %s: %s", ticker, e)
        return {}


# ════════════════════════════════════════════════════════════════════════════
# Main loader
# ════════════════════════════════════════════════════════════════════════════

def _fetch_one_company(ticker: str, meta: dict) -> tuple[str, dict | None]:
    """Fetch financials + consensus for a single company (thread-safe)."""
    try:
        t     = yf.Ticker(ticker)
        scale = meta["ccy_scale"] / 1e6   # native currency → $M

        inc = t.income_stmt
        cf  = t.cashflow
        bs  = t.balance_sheet

        # ── Income Statement ──────────────────────────────────────────
        revenue,   yrs = _yf_val(inc, "Total Revenue",                                scale=scale)
        gross_pft, _   = _yf_val(inc, "Gross Profit",                                 scale=scale)
        ebitda,    _   = _yf_val(inc, "EBITDA", "Normalized EBITDA",                  scale=scale)
        op_inc,    _   = _yf_val(inc, "Operating Income", "EBIT",                     scale=scale)
        net_inc,   _   = _yf_val(inc, "Net Income", "Net Income Common Stockholders", scale=scale)

        # ── Balance Sheet ─────────────────────────────────────────────
        cash,       _  = _yf_val(bs,
            "Cash And Cash Equivalents",
            "Cash Cash Equivalents And Short Term Investments",
            scale=scale,
        )
        tot_assets, _  = _yf_val(bs, "Total Assets",  scale=scale)
        tot_debt,   _  = _yf_val(bs,
            "Total Debt",
            "Long Term Debt And Capital Lease Obligation",
            "Long Term Debt",
            scale=scale,
        )
        tot_equity, _  = _yf_val(bs,
            "Stockholders Equity",
            "Common Stock Equity",
            "Total Equity Gross Minority Interest",
            scale=scale,
        )
        # Lease obligations (GAAP reported — capital / operating leases)
        lease_lt,  _   = _yf_val(bs,
            "Long Term Capital Lease Obligation",
            "Long Term Lease Obligation",
            scale=scale,
        )
        lease_cur, _   = _yf_val(bs,
            "Current Capital Lease Obligation",
            "Current Lease Obligation",
            scale=scale,
        )
        # Prefer total if reported; otherwise sum current + non-current
        lease_tot, _   = _yf_val(bs, "Capital Lease Obligations", "Leases", scale=scale)
        n = len(yrs)
        if not any(v is not None for v in lease_tot):
            lease_tot = [
                round((a or 0) + (b or 0), 1) if (a is not None or b is not None) else None
                for a, b in zip(lease_cur, lease_lt)
            ]

        net_debt = [
            round(d - c, 1) if d is not None and c is not None else None
            for d, c in zip(tot_debt, cash)
        ]

        # ── Cash Flow Statement ───────────────────────────────────────
        ocf,    _   = _yf_val(cf, "Operating Cash Flow", scale=scale)
        capex_r, _  = _yf_val(cf, "Capital Expenditure",  scale=scale)
        capex       = [abs(v) if v is not None else None for v in capex_r]
        fcf_r,  _   = _yf_val(cf, "Free Cash Flow",       scale=scale)
        fcf = [
            fcf_r[i] if fcf_r[i] is not None
            else (
                round(ocf[i] - capex[i], 1)
                if ocf[i] is not None and capex[i] is not None
                else None
            )
            for i in range(n)
        ]

        # ── Forward estimates (extend income statement) ────────────
        income = {
            "Revenue":          revenue,
            "Gross Profit":     gross_pft,
            "EBITDA":           ebitda,
            "Operating Income": op_inc,
            "Net Income":       net_inc,
        }
        balance = {
            "Cash & Equiv.":  cash,
            "Total Assets":   tot_assets,
            "Total Debt":     tot_debt,
            "Lease Oblig.":   lease_tot,
            "Net Debt":       net_debt,
            "Total Equity":   tot_equity,
        }
        cashflow = {
            "Operating CF": ocf,
            "CapEx":        capex,
            "Free CF":      fcf,
        }

        try:
            rev_est = t.revenue_estimate
            eps_est = t.earnings_estimate
            if rev_est is not None and not rev_est.empty and yrs:
                last_fy = int(yrs[-1].replace("FY", ""))

                def _est(df, period):
                    try:
                        v = df.loc[period, "avg"]
                        return round(float(v) * scale, 1) if pd.notna(v) else None
                    except (KeyError, TypeError):
                        return None

                rev_0y = _est(rev_est, "0y")
                rev_1y = _est(rev_est, "+1y")
                # EPS × shares ≈ net income estimate
                ni_0y, ni_1y = None, None
                if eps_est is not None and not eps_est.empty:
                    try:
                        shares = getattr(t.fast_info, "shares", None)
                        if shares is None:
                            shares = (t.info or {}).get("sharesOutstanding")
                        if shares:
                            def _eps_raw(period):
                                try:
                                    v = eps_est.loc[period, "avg"]
                                    return float(v) if pd.notna(v) else None
                                except (KeyError, TypeError):
                                    return None
                            e0 = _eps_raw("0y")
                            e1 = _eps_raw("+1y")
                            if e0 is not None:
                                ni_0y = round(e0 * shares * scale, 1)
                            if e1 is not None:
                                ni_1y = round(e1 * shares * scale, 1)
                    except Exception:
                        pass

                est_years = [f"FY{last_fy + 1}E", f"FY{last_fy + 2}E"]
                yrs = yrs + est_years

                income["Revenue"]    = revenue + [rev_0y, rev_1y]
                income["Net Income"] = net_inc + [ni_0y, ni_1y]
                for key in income:
                    if len(income[key]) < len(yrs):
                        income[key] = income[key] + [None] * (len(yrs) - len(income[key]))
                for d in (balance, cashflow):
                    for key in d:
                        d[key] = d[key] + [None, None]
        except Exception as e:
            logger.debug("Estimates %s: %s", ticker, e)

        return ticker, {
            "name":  meta["name"],
            "group": meta["group"],
            "years": yrs,
            "income":   income,
            "balance":  balance,
            "cashflow": cashflow,
            "consensus": _fetch_consensus(t, scale, ticker),
        }
    except Exception as e:
        logger.warning("yfinance financials %s: %s", ticker, e)
        return ticker, None


@st.cache_data(ttl=3600)
def fetch_financials() -> dict:
    """Fetch last 4 fiscal years of financials + consensus for all companies."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_fetch_one_company, ticker, meta): ticker
            for ticker, meta in COMPANY_META.items()
        }
        for future in as_completed(futures):
            ticker, data = future.result()
            if data is not None:
                out[ticker] = data
    return out


def get_all_financials() -> dict:
    """Return financial data + derived ratios for all companies."""
    data = fetch_financials()

    for d in data.values():
        rev    = d["income"]["Revenue"]
        gp     = d["income"]["Gross Profit"]
        op     = d["income"]["Operating Income"]
        ni     = d["income"]["Net Income"]
        ebitda = d["income"]["EBITDA"]
        nd     = d["balance"]["Net Debt"]
        fcf    = d["cashflow"]["Free CF"]
        capex  = d["cashflow"]["CapEx"]

        def _pct(num, den):
            return [
                round(a / b * 100, 1) if a is not None and b is not None and b != 0 else None
                for a, b in zip(num, den)
            ]

        def _mult(num, den):
            return [
                round(a / b, 2) if a is not None and b is not None and b != 0 else None
                for a, b in zip(num, den)
            ]

        d["ratios"] = {
            "Gross Margin %":    _pct(gp, rev),
            "Operating Margin %": _pct(op, rev),
            "Net Margin %":      _pct(ni, rev),
            "FCF Margin %":      _pct(fcf, rev),
            "CapEx / Revenue %": _pct(capex, rev),
            "Net Debt / EBITDA": _mult(nd, ebitda),
        }

    return data
