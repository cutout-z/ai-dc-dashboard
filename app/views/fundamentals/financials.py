"""Financial (key players) — 3-statement summary from yfinance.

P&L, Balance Sheet, Cash Flow Statement, Key Ratios, and Analyst Consensus
per company (dropdown selector). All statement values in $M USD; last 4 fiscal years.
"""

from typing import Optional

import streamlit as st
import pandas as pd

st.title("Financial Statements (key players)")

from app.lib.financials import (
    get_all_financials,
    load_ai_supplement,
    COMPANY_ORDER,
)


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_b(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"${v / 1000:,.1f}B"

def _fmt_pct(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.1f}%"

def _fmt_x(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.1f}x"


# ── Colour rules ──────────────────────────────────────────────────────────────
# Sign-based: True = green ≥ 0 / red < 0 | False = green < 0 / red ≥ 0

_COLOR_ROWS: dict[str, bool] = {
    "Net Income":        True,
    "Net Debt":          False,   # net cash = green
    "Operating CF":      True,
    "Free CF":           True,
    "Net Margin %":      True,
    "FCF Margin %":      True,
    "Operating Margin %": True,
}

_RATIO_FORMATTERS = {
    "Gross Margin %":    _fmt_pct,
    "Operating Margin %": _fmt_pct,
    "Net Margin %":      _fmt_pct,
    "FCF Margin %":      _fmt_pct,
    "CapEx / Revenue %": _fmt_pct,
    "Net Debt / EBITDA": _fmt_x,
}


# ── Table renderer ────────────────────────────────────────────────────────────

def _render_table(title: str, rows: dict, years: list, formatters: Optional[dict] = None) -> None:
    with st.container(border=True):
        st.subheader(title)
        if not rows or not years:
            st.caption("No data.")
            return

        num_df  = pd.DataFrame(rows, index=years).T
        disp    = {
            k: [(formatters or {}).get(k, _fmt_b)(v) for v in vals]
            for k, vals in rows.items()
        }
        disp_df = pd.DataFrame(disp, index=years).T

        styled = disp_df.style
        for label, pos_green in _COLOR_ROWS.items():
            if label not in num_df.index:
                continue
            for j, col in enumerate(disp_df.columns):
                raw = num_df.loc[label].iloc[j]
                if raw is None or pd.isna(raw):
                    continue
                r = float(raw)
                color = (
                    "color: #22c55e"
                    if (pos_green and r >= 0) or (not pos_green and r < 0)
                    else "color: #ef4444"
                )
                styled = styled.map(lambda _, c=color: c, subset=pd.IndexSlice[[label], [col]])

        st.dataframe(styled, use_container_width=True, height=35 * len(disp_df) + 40)


# ── Consensus renderer ────────────────────────────────────────────────────────

def _render_consensus(c: dict) -> None:
    with st.container(border=True):
        st.subheader("Analyst Consensus")
        if not c:
            st.caption("No consensus data available.")
            return

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Revenue Estimates**")
            if c.get("rev_0y_avg") is not None:
                low, avg, high = c.get("rev_0y_low"), c["rev_0y_avg"], c.get("rev_0y_high")
                st.metric("Current FY", _fmt_b(avg))
                if low is not None and high is not None:
                    st.caption(f"Range: {_fmt_b(low)} – {_fmt_b(high)}")
            if c.get("rev_1y_avg") is not None:
                growth = c.get("rev_growth")
                delta  = f"{growth * 100:+.1f}% YoY" if growth is not None else None
                st.metric("Next FY", _fmt_b(c["rev_1y_avg"]), delta=delta)
                low1, high1 = c.get("rev_1y_low"), c.get("rev_1y_high")
                if low1 is not None and high1 is not None:
                    st.caption(f"Range: {_fmt_b(low1)} – {_fmt_b(high1)}")
            if c.get("rev_n"):
                st.caption(f"{c['rev_n']} analysts")

        with col2:
            st.markdown("**EPS Estimates**")
            if c.get("eps_0y_avg") is not None:
                st.metric("Current FY", f"${c['eps_0y_avg']:.2f}")
            if c.get("eps_1y_avg") is not None:
                st.metric("Next FY", f"${c['eps_1y_avg']:.2f}")
            if c.get("eps_n"):
                st.caption(f"{c['eps_n']} analysts")

        with col3:
            st.markdown("**Price Target**")
            if c.get("pt_mean") is not None:
                current = c.get("pt_current")
                upside  = (
                    f"{(c['pt_mean'] / current - 1) * 100:+.1f}% vs current"
                    if current else None
                )
                st.metric("Mean", f"${c['pt_mean']:.2f}", delta=upside)
            if c.get("pt_low") is not None and c.get("pt_high") is not None:
                st.caption(f"Range: ${c['pt_low']:.2f} – ${c['pt_high']:.2f}")
            if c.get("pt_current") is not None:
                st.caption(f"Current price: ${c['pt_current']:.2f}")


# ── Load data ─────────────────────────────────────────────────────────────────

with st.spinner("Loading financial data…"):
    all_fin = get_all_financials()
    ai_supp = load_ai_supplement()

if not all_fin:
    st.warning("No financial data available.")
    st.stop()


# ── AI Revenue Proxy & Disclosure Quality ────────────────────────────────────

st.header("AI Revenue Proxy & Disclosure Quality")
st.caption(
    "AI revenue is not a GAAP line item. Figures represent management disclosures, "
    "analyst estimates, or the closest revenue proxy available. Not directly comparable across companies."
)

if ai_supp:
    df_supp = pd.DataFrame(ai_supp)

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
    st.dataframe(
        styled_supp,
        use_container_width=True,
        hide_index=True,
        height=35 * (len(df_supp) + 1) + 10,
    )
else:
    st.info("AI Supplement data not available — check data/reference/ai_supplement.csv exists.")

st.divider()


# ── Company selector ──────────────────────────────────────────────────────────

available = [t for t in COMPANY_ORDER if t in all_fin]
selected = st.selectbox(
    "Company",
    options=available,
    format_func=lambda t: f"{all_fin[t]['name']} ({t})  —  {all_fin[t]['group']}",
)

if not selected:
    st.stop()

d     = all_fin[selected]
years = d["years"]

has_estimates = any(y.endswith("E") for y in years)
if has_estimates:
    actual_end = [y for y in years if not y.endswith("E")][-1]
    st.caption(f"yfinance annual  ·  {years[0]}–{actual_end} actuals + consensus estimates  ·  $M USD")
else:
    st.caption(f"yfinance annual  ·  {years[0]}–{years[-1]}  ·  $M USD  ·  all actuals")


# ── Three-statement display ───────────────────────────────────────────────────

_render_table("Income Statement",    d["income"],   years)
_render_table("Balance Sheet",       d["balance"],  years)
_render_table("Cash Flow Statement", d["cashflow"], years)


# ── Key Ratios ────────────────────────────────────────────────────────────────

_render_table("Key Ratios", d.get("ratios", {}), years, formatters=_RATIO_FORMATTERS)
st.caption(
    "Lease Oblig. = GAAP-reported capital/operating lease liabilities (ASC 842 / IFRS 16). "
    "Net Debt / EBITDA: negative = net cash. CapEx / Revenue flags capital intensity."
)


# ── Analyst Consensus ─────────────────────────────────────────────────────────

consensus = d.get("consensus", {})

# Debug: show consensus source status (remove after confirming it works)
from app.lib.financials import _CONSENSUS_PATH
_consensus_debug = f"consensus keys: {list(consensus.keys())[:5]}..." if consensus else "empty"
st.caption(f"_debug: JSON={_CONSENSUS_PATH.exists()}, ticker={selected}, {_consensus_debug}")

_render_consensus(consensus)
