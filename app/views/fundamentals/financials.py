"""Financial (key players) — 3-statement summary + AI revenue disclosure.

Per-company transposed financial tables covering:
  Revenue, EBITDA, CAPEX, OCF, FCF, Cash, Gross Debt, Net Debt,
  Off-Balance-Sheet Leases, Net D/EBITDA, Post-Lease D/EBITDA, CAPEX/Sales

Excel model companies (MSFT, AMZN, GOOGL, META, ORCL): FY2022A–FY2027E
Remaining companies (AAPL, NVDA, TSLA, AMD, TSM, PLTR, EQIX, DLR, AMT): last 4 fiscal years via yfinance
"""

import streamlit as st
import pandas as pd

st.title("Financial Statements (key players)")

from app.lib.financials import (
    get_all_financials,
    load_ai_supplement,
    COMPANY_ORDER,
    EXCEL_COMPANY_META,
)

CAPEX_SALES_FLAG = 0.34   # >34% = elevated capital intensity
ND_EBITDA_FLAG   = 3.0    # >3x = elevated leverage


# ── Formatters ───────────────────────────────────────────────────────────────

def _fmt_b(v):
    """Format $M value as $B string."""
    if v is None or pd.isna(v):
        return "—"
    b = v / 1000
    return f"${b:,.1f}B"


def _fmt_x(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.1f}x"


def _fmt_pct(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{v * 100:.1f}%"


# ── Colour helpers (applied to the raw numeric DataFrame before formatting) ──

def _color_nd(val):
    """Green if net cash (negative), red if net debt."""
    try:
        v = float(val)
        return "color: #22c55e" if v < 0 else "color: #ef4444"
    except Exception:
        return ""


def _color_fcf(val):
    try:
        v = float(val)
        return "color: #22c55e" if v >= 0 else "color: #ef4444"
    except Exception:
        return ""


def _color_capex_sales(val):
    try:
        v = float(val)
        return "color: #ef4444" if v > CAPEX_SALES_FLAG else ""
    except Exception:
        return ""


def _color_leverage(val):
    try:
        v = float(val)
        return "color: #ef4444" if v > ND_EBITDA_FLAG else ""
    except Exception:
        return ""


# ── Build display table for one company ──────────────────────────────────────

_METRIC_ROWS = [
    # (display_label, key, fmt_fn, color_fn)
    ("Revenue",           "revenue",      _fmt_b,   None),
    ("EBITDA",            "ebitda",       _fmt_b,   None),
    ("CAPEX",             "capex",        _fmt_b,   None),
    ("OCF",               "ocf",          _fmt_b,   None),
    ("FCF",               "fcf",          _fmt_b,   _color_fcf),
    ("Cash",              "cash",         _fmt_b,   None),
    ("Gross Debt",        "gross_debt",   _fmt_b,   None),
    ("Net Debt",          "net_debt",     _fmt_b,   _color_nd),
    ("OBS Leases",        "obs_leases",   _fmt_b,   None),
    ("Net D/EBITDA",      "nd_ebitda",    _fmt_x,   _color_leverage),
    ("Post-Lease D/EBITDA","pl_nd_ebitda",_fmt_x,   _color_leverage),
    ("CAPEX / Sales",     "capex_sales",  _fmt_pct, _color_capex_sales),
]


def _build_table(d: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (numeric_df, display_df, color_map) for Styler.

    numeric_df  — raw numbers (for colour computation)
    display_df  — pre-formatted strings
    color_map   — {row_label: color_fn} for rows that need colouring
    """
    years = d["years"]
    num_rows = {}
    disp_rows = {}
    color_map = {}

    for label, key, fmt, cfn in _METRIC_ROWS:
        vals = d.get(key, [None] * len(years))
        num_rows[label]  = vals
        disp_rows[label] = [fmt(v) for v in vals]
        if cfn:
            color_map[label] = cfn

    num_df  = pd.DataFrame(num_rows, index=years).T
    disp_df = pd.DataFrame(disp_rows, index=years).T
    return num_df, disp_df, color_map


def _style_table(num_df: pd.DataFrame, disp_df: pd.DataFrame,
                 color_map: dict, hist_count: int) -> object:
    """Apply formatting strings + per-cell colour to the display DataFrame."""

    def cell_style(val, row_label, col_pos, color_fn):
        raw = num_df.loc[row_label].iloc[col_pos]
        try:
            raw = float(raw) if raw is not None else None
        except Exception:
            raw = None
        return color_fn(raw) if raw is not None else ""

    styled = disp_df.style

    for row_label, cfn in color_map.items():
        if row_label not in disp_df.index:
            continue
        for j, col in enumerate(disp_df.columns):
            styled = styled.map(
                lambda v, r=row_label, j=j, c=cfn: cell_style(v, r, j, c),
                subset=pd.IndexSlice[[row_label], [col]],
            )

    # Dim estimate columns (lighter text)
    if hist_count < len(disp_df.columns):
        est_cols = list(disp_df.columns[hist_count:])
        styled = styled.map(
            lambda _: "color: #9ca3af",
            subset=pd.IndexSlice[:, est_cols],
        )

    return styled


# ── Load data ────────────────────────────────────────────────────────────────

with st.spinner("Loading financial data…"):
    all_fin = get_all_financials()
    ai_supp = load_ai_supplement()

if not all_fin:
    st.warning("No financial data available.")
    st.stop()


# ── Group header display ─────────────────────────────────────────────────────

_GROUPS = ["Mag 7", "AI Infra", "DC Operators"]

for group in _GROUPS:
    tickers = [t for t in COMPANY_ORDER if t in all_fin and all_fin[t]["group"] == group]
    if not tickers:
        continue

    st.header(group)

    for ticker in tickers:
        d = all_fin[ticker]
        name    = d["name"]
        source  = d["source"]
        years   = d["years"]
        hc      = d.get("hist_count", len(years))
        n_years = len(years)

        source_note = (
            "Excel model (FY2022A–FY2027E, $M USD)"
            if source == "excel"
            else f"yfinance annual ({years[0]}–{years[-1]}, $M USD)"
        )

        num_df, disp_df, cmap = _build_table(d)

        # Auto height: 35px × rows + 40px header
        tbl_h = 35 * len(disp_df) + 40

        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.subheader(f"{name} ({ticker})")
            with col_b:
                st.caption(source_note)

            # Column-header styling: bold historical, dimmed estimate
            styled = _style_table(num_df, disp_df, cmap, hc)

            st.dataframe(
                styled,
                use_container_width=True,
                height=tbl_h,
            )

            if source == "excel":
                st.caption(
                    "OBS Leases = uncommenced data-centre lease commitments (Moody's $662B aggregate, "
                    "phased 50% FY2026E / 100% FY2027E per company share). "
                    "Estimate columns (E) in grey. Net Debt negative = net cash position."
                )


# ── AI Revenue Proxy & Disclosure Quality ───────────────────────────────────

st.divider()
st.header("AI Revenue Proxy & Disclosure Quality")
st.caption(
    "AI revenue is not a GAAP line item. Figures represent management disclosures, "
    "analyst estimates, or the closest revenue proxy available. Not directly comparable across companies."
)

if ai_supp:
    df_supp = pd.DataFrame(ai_supp)

    # Disclosure quality colour
    def _dq_color(val):
        if not isinstance(val, str):
            return ""
        if val.startswith("A"):
            return "color: #22c55e"
        if val.startswith("B"):
            return "color: #f59e0b"
        return "color: #ef4444"

    styled_supp = (
        df_supp.style
        .map(_dq_color, subset=["Disclosure Quality"])
        .set_properties(subset=["Source / Notes"], **{"white-space": "pre-wrap", "max-width": "420px"})
    )
    h_supp = 35 * (len(df_supp) + 1) + 10
    st.dataframe(
        styled_supp,
        use_container_width=True,
        hide_index=True,
        height=h_supp,
    )
else:
    st.info("AI Supplement data not available — check Excel model path.")
