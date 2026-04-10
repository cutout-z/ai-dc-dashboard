"""
financials.py — Financial statements data for the Financial (key players) page.

Sources
-------
Excel companies (MSFT, AMZN, GOOGL, META, ORCL):
    Reads IS / BS / CFS sheets from Hyperscalers_3Statement_Model.xlsx
    (sibling AI Bubble Project folder). Values cached at file-save time;
    all IS values are hardcoded, WC / CapEx / debt hardcoded in CFS / BS.
    OCF is computed as NI + D&A + SBC + ΔWC from those hardcoded components.

Remaining companies (AAPL, NVDA, TSLA, AMD, TSM, PLTR, EQIX, DLR, AMT):
    Fetched via yfinance annual income_stmt / cashflow / balance_sheet.
    Last 4 fiscal years. Values converted to $M USD.

All stored values are in USD millions ($M).
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

# ── Excel companies ──────────────────────────────────────────────────────────

EXCEL_COMPANY_META: dict[str, dict] = {
    "MSFT":  {"name": "Microsoft",  "group": "Mag 7",        "sheet": "MSFT"},
    "AMZN":  {"name": "Amazon",     "group": "Mag 7",        "sheet": "AMZN"},
    "GOOGL": {"name": "Alphabet",   "group": "Mag 7",        "sheet": "GOOGL"},
    "META":  {"name": "Meta",       "group": "Mag 7",        "sheet": "META"},
    "ORCL":  {"name": "Oracle",     "group": "AI Infra",     "sheet": "ORCL"},
}

# Off-balance-sheet uncommenced DC leases ($B, Moody's $662B × share)
_OBS_LEASE_B: dict[str, float] = {
    "MSFT":  662 * 0.25,   # 165.5 $B
    "AMZN":  662 * 0.30,   # 198.6 $B
    "GOOGL": 662 * 0.22,   # 145.6 $B
    "META":  662 * 0.15,   #  99.3 $B
    "ORCL":  662 * 0.08,   #  53.0 $B
}

EXCEL_YEARS = ["FY2022A", "FY2023A", "FY2024A", "FY2025E", "FY2026E", "FY2027E"]
_HIST_COUNT = 3   # first 3 columns are actuals

# ── yfinance-only companies ──────────────────────────────────────────────────

YFINANCE_COMPANY_META: dict[str, dict] = {
    "AAPL": {"name": "Apple",          "group": "Mag 7",        "ccy_scale": 1.0},
    "NVDA": {"name": "NVIDIA",         "group": "Mag 7",        "ccy_scale": 1.0},
    "TSLA": {"name": "Tesla",          "group": "Mag 7",        "ccy_scale": 1.0},
    "AMD":  {"name": "AMD",            "group": "AI Infra",     "ccy_scale": 1.0},
    "TSM":  {"name": "TSMC",           "group": "AI Infra",     "ccy_scale": 1/32.0},  # TWD→USD
    "PLTR": {"name": "Palantir",       "group": "AI Infra",     "ccy_scale": 1.0},
    "EQIX": {"name": "Equinix",        "group": "DC Operators", "ccy_scale": 1.0},
    "DLR":  {"name": "Digital Realty", "group": "DC Operators", "ccy_scale": 1.0},
    "AMT":  {"name": "American Tower", "group": "DC Operators", "ccy_scale": 1.0},
}

# Display order by group
COMPANY_ORDER = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "ORCL", "AMD", "TSM", "PLTR",
    "EQIX", "DLR", "AMT",
]


# ════════════════════════════════════════════════════════════════════════════
# Excel loader
# ════════════════════════════════════════════════════════════════════════════

def _row(ws, label: str, n: int = 6) -> list:
    """Return values from the first worksheet row whose col-A cell matches label."""
    for row in ws.iter_rows():
        if row[0].value == label:
            return [row[i].value for i in range(1, n + 1)]
    return [None] * n


def _load_excel_company(wb, sheet_code: str, ticker: str) -> dict:
    is_ws  = wb[f"{sheet_code}_IS"]
    bs_ws  = wb[f"{sheet_code}_BS"]
    cfs_ws = wb[f"{sheet_code}_CFS"]

    # Income statement — all hardcoded, cleanly cached
    revenue    = _row(is_ws, "Revenue")
    ebitda     = _row(is_ws, "EBITDA")
    dna        = _row(is_ws, "Depreciation & Amortization")
    sbc        = _row(is_ws, "Stock-Based Compensation")
    net_income = _row(is_ws, "Net Income")

    # Cash flow — CapEx and WC are hardcoded; NI/D&A/SBC link to IS (None)
    capex_raw = _row(cfs_ws, "Capital Expenditures")
    capex     = [abs(v) if v is not None else None for v in capex_raw]
    wc_ar     = _row(cfs_ws, "Change in Accounts Receivable")
    wc_inv    = _row(cfs_ws, "Change in Inventory")
    wc_ap     = _row(cfs_ws, "Change in Accounts Payable")
    wc_oth    = _row(cfs_ws, "Other Working Capital Changes")
    cfi       = _row(cfs_ws, "Cash from Investing (CFI)")
    cff       = _row(cfs_ws, "Cash from Financing (CFF)")
    beg_cash  = _row(cfs_ws, "Beginning Cash")

    # Balance sheet
    lt_debt = _row(bs_ws, "Long-term Debt")

    # OCF = NI + D&A + SBC + ΔWC  (computed because CFS NI/D&A/SBC not cached)
    ocf = []
    for i in range(6):
        ni, d, s = net_income[i], dna[i], sbc[i]
        wc = sum(x or 0 for x in [wc_ar[i], wc_inv[i], wc_ap[i], wc_oth[i]])
        ocf.append(ni + d + s + wc if None not in (ni, d, s) else None)

    fcf = [
        round(o - c, 1) if o is not None and c is not None else None
        for o, c in zip(ocf, capex)
    ]

    # Ending cash = beginning of *next* period (shift beg_cash forward by 1)
    # FY2027 ending: beginning[5] + OCF[5] + CFI[5] + CFF[5]
    cash = []
    for i in range(5):
        cash.append(beg_cash[i + 1])
    fy27 = None
    if all(x is not None for x in [beg_cash[5], ocf[5], cfi[5], cff[5]]):
        fy27 = beg_cash[5] + ocf[5] + cfi[5] + cff[5]
    cash.append(fy27)

    gross_debt = lt_debt

    net_debt = [
        round(g - c, 1) if g is not None and c is not None else None
        for g, c in zip(gross_debt, cash)
    ]

    # OBS leases: None for 2022-2025, then phase in 50% FY2026E, 100% FY2027E
    obs_b = _OBS_LEASE_B.get(ticker, 0)
    obs_leases: list = [
        None, None, None, None,
        round(obs_b * 0.5 * 1000),   # $M
        round(obs_b * 1000),          # $M
    ]

    return {
        "years":      EXCEL_YEARS,
        "hist_count": _HIST_COUNT,
        "source":     "excel",
        "revenue":    revenue,
        "ebitda":     ebitda,
        "capex":      capex,
        "ocf":        ocf,
        "fcf":        fcf,
        "cash":       cash,
        "gross_debt": gross_debt,
        "net_debt":   net_debt,
        "obs_leases": obs_leases,
    }


@st.cache_data(ttl=86400)
def load_excel_financials() -> dict:
    """Load MSFT / AMZN / GOOGL / META / ORCL from the 3-statement Excel model."""
    if not _EXCEL_PATH.exists():
        logger.warning("3-statement model not found: %s", _EXCEL_PATH)
        return {}
    wb = openpyxl.load_workbook(str(_EXCEL_PATH), data_only=True)
    out = {}
    for ticker, meta in EXCEL_COMPANY_META.items():
        try:
            d = _load_excel_company(wb, meta["sheet"], ticker)
            d["name"]  = meta["name"]
            d["group"] = meta["group"]
            out[ticker] = d
        except Exception as e:
            logger.warning("Excel load failed %s: %s", ticker, e)
    return out


# ════════════════════════════════════════════════════════════════════════════
# AI Supplement — disclosure quality table
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def load_ai_supplement() -> list[dict]:
    """Extract the AI revenue proxy / disclosure-quality table from AI_Supplement."""
    if not _EXCEL_PATH.exists():
        return []
    wb = openpyxl.load_workbook(str(_EXCEL_PATH), data_only=True)
    ws = wb["AI_Supplement"]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]

    # Locate the column-header row for the disclosure table
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
            "Company":             current_company,
            "Metric":              row[1],
            "FY2024A":             row[2],
            "FY2025E":             row[3],
            "FY2026E":             row[4],
            "FY2027E":             row[5],
            "Disclosure Quality":  row[6],
            "Source / Notes":      row[7],
        })
    return records


# ════════════════════════════════════════════════════════════════════════════
# yfinance loader
# ════════════════════════════════════════════════════════════════════════════

def _yf_series(df: pd.DataFrame | None, *labels, n: int = 4, scale: float = 1.0):
    """Return (values, year_labels) for the first matching label in df.

    df columns are assumed to be Timestamps; sorted oldest-first then last n taken.
    scale converts raw units → $M  (e.g. 1/1e6 for raw USD → $M).
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


@st.cache_data(ttl=3600)
def fetch_yfinance_financials() -> dict:
    """Fetch last 4 fiscal years of financials for non-Excel companies."""
    out = {}
    for ticker, meta in YFINANCE_COMPANY_META.items():
        try:
            t     = yf.Ticker(ticker)
            # yfinance raw values are in native-currency dollars; /1e6 → $M
            scale = meta.get("ccy_scale", 1.0) / 1e6

            inc = t.income_stmt
            cf  = t.cashflow
            bs  = t.balance_sheet

            revenue, yrs = _yf_series(inc, "Total Revenue",                scale=scale)
            ebitda,  _   = _yf_series(inc, "EBITDA", "Normalized EBITDA",  scale=scale)
            dna,     _   = _yf_series(
                inc,
                "Reconciled Depreciation",
                "Depreciation And Amortization In Income Statement",
                "Depreciation",
                scale=scale,
            )
            ni,      _   = _yf_series(inc, "Net Income",
                                      "Net Income Common Stockholders",      scale=scale)

            capex_r, _   = _yf_series(cf, "Capital Expenditure",            scale=scale)
            capex        = [abs(v) if v is not None else None for v in capex_r]
            ocf,     _   = _yf_series(cf, "Operating Cash Flow",            scale=scale)
            fcf_r,   _   = _yf_series(cf, "Free Cash Flow",                 scale=scale)

            cash,    _   = _yf_series(
                bs,
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
                scale=scale,
            )
            total_debt, _ = _yf_series(
                bs, "Total Debt",
                "Long Term Debt And Capital Lease Obligation",
                "Long Term Debt",
                scale=scale,
            )

            # Prefer yfinance FCF; fall back to OCF - CapEx
            n = len(yrs)
            fcf = [
                fcf_r[i]
                if fcf_r[i] is not None
                else (round(ocf[i] - capex[i], 1) if ocf[i] is not None and capex[i] is not None else None)
                for i in range(n)
            ]

            # EBITDA: if missing, compute from EBIT + D&A via NI back-fill
            # (leave as-is; yfinance usually has it)

            net_debt = [
                round(d - c, 1) if d is not None and c is not None else None
                for d, c in zip(total_debt, cash)
            ]

            out[ticker] = {
                "name":       meta["name"],
                "group":      meta["group"],
                "years":      yrs,
                "hist_count": len(yrs),   # all actuals for yfinance
                "source":     "yfinance",
                "revenue":    revenue,
                "ebitda":     ebitda,
                "capex":      capex,
                "ocf":        ocf,
                "fcf":        fcf,
                "cash":       cash,
                "gross_debt": total_debt,
                "net_debt":   net_debt,
                "obs_leases": [None] * n,
            }
        except Exception as e:
            logger.warning("yfinance financials %s: %s", ticker, e)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Combined — derive ratios and merge
# ════════════════════════════════════════════════════════════════════════════

def get_all_financials() -> dict:
    """Return merged, ratio-augmented financial data for all companies."""
    data = {**load_excel_financials(), **fetch_yfinance_financials()}

    for d in data.values():
        n = len(d["years"])

        # Net Debt / EBITDA
        nd_eb = []
        for i in range(n):
            nd, eb = d["net_debt"][i], d["ebitda"][i]
            nd_eb.append(round(nd / eb, 2) if nd is not None and eb else None)
        d["nd_ebitda"] = nd_eb

        # Post-lease Net Debt / EBITDA
        pl_nd_eb = []
        for i in range(n):
            nd, eb = d["net_debt"][i], d["ebitda"][i]
            obs    = d["obs_leases"][i] or 0
            pl_nd_eb.append(round((nd + obs) / eb, 2) if nd is not None and eb else None)
        d["pl_nd_ebitda"] = pl_nd_eb

        # CAPEX / Sales
        cx_sales = []
        for i in range(n):
            cx, rev = d["capex"][i], d["revenue"][i]
            cx_sales.append(round(cx / rev, 4) if cx is not None and rev else None)
        d["capex_sales"] = cx_sales

    return data
