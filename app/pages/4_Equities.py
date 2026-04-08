"""Mag 7 & AI Infrastructure Equities — prices, fundamentals, P/E comparison, treemap."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Equities", layout="wide")

st.title("Mag 7 & AI Infrastructure")

# Lazy import to keep page load fast when navigating other pages
from app.lib.equities import fetch_equities_data

with st.spinner("Fetching equity data..."):
    stocks = fetch_equities_data()

if not stocks:
    st.warning("No equity data available. Check network connection.")
    st.stop()

# ──────────────────────────────────────────────
# 1. SHARE PRICE PERFORMANCE TABLE
# ──────────────────────────────────────────────
st.header("Share Price Performance")

perf_rows = []
for s in stocks:
    ret = s.get("returns", {})
    perf_rows.append({
        "Ticker": s["symbol"],
        "Name": s["name"],
        "Group": s["group"],
        "Price": s["price"],
        "Daily %": s["change_pct"],
        "1M %": ret.get("1M"),
        "3M %": ret.get("3M"),
        "6M %": ret.get("6M"),
        "1Y %": ret.get("1Y"),
        "5Y %": ret.get("5Y"),
        "10Y %": ret.get("10Y"),
    })

df_perf = pd.DataFrame(perf_rows)

# Color-code return columns
return_cols = ["Daily %", "1M %", "3M %", "6M %", "1Y %", "5Y %", "10Y %"]


def _color_returns(val):
    if val is None or pd.isna(val):
        return "color: gray"
    return "color: #22c55e" if val >= 0 else "color: #ef4444"


def _fmt_pct(val):
    if val is None or pd.isna(val):
        return "-"
    return f"{val:+.2f}%"


def _fmt_price(val):
    if val is None or pd.isna(val):
        return "-"
    return f"${val:,.2f}"


styled = (
    df_perf.style
    .format({col: _fmt_pct for col in return_cols})
    .format({"Price": _fmt_price})
    .map(_color_returns, subset=return_cols)
)

st.dataframe(styled, use_container_width=True, hide_index=True, height=440)

# ──────────────────────────────────────────────
# 2. FUNDAMENTALS TABLE
# ──────────────────────────────────────────────
st.header("Fundamentals")

fund_rows = []
for s in stocks:
    mcap = s.get("market_cap")
    mcap_fmt = round(mcap / 1e9, 1) if mcap else None
    fund_rows.append({
        "Ticker": s["symbol"],
        "Name": s["name"],
        "Mkt Cap ($B)": mcap_fmt,
        "PE (T)": s.get("pe_trailing"),
        "PE (F)": s.get("pe_forward"),
        "EPS (T)": s.get("eps_trailing"),
        "EPS (F)": s.get("eps_forward"),
        "% from 52W High": s.get("pct_from_high"),
        "Rev Growth YoY %": s.get("rev_growth_yoy"),
        "CAPEX Growth YoY %": s.get("capex_yoy"),
    })

df_fund = pd.DataFrame(fund_rows)


def _fmt_mcap(val):
    if val is None or pd.isna(val):
        return "-"
    if val >= 1000:
        return f"${val / 1000:.2f}T"
    return f"${val:.1f}B"


def _fmt_pe(val):
    if val is None or pd.isna(val):
        return "-"
    return f"{val:.1f}x"


def _fmt_eps(val):
    if val is None or pd.isna(val):
        return "-"
    return f"${val:.2f}"


styled_fund = (
    df_fund.style
    .format({
        "Mkt Cap ($B)": _fmt_mcap,
        "PE (T)": _fmt_pe,
        "PE (F)": _fmt_pe,
        "EPS (T)": _fmt_eps,
        "EPS (F)": _fmt_eps,
        "% from 52W High": _fmt_pct,
        "Rev Growth YoY %": _fmt_pct,
        "CAPEX Growth YoY %": _fmt_pct,
    })
    .map(_color_returns, subset=["% from 52W High", "Rev Growth YoY %", "CAPEX Growth YoY %"])
)

st.dataframe(styled_fund, use_container_width=True, hide_index=True, height=440)

# ──────────────────────────────────────────────
# 3. CHARTS
# ──────────────────────────────────────────────
col1, col2 = st.columns(2)

# --- P/E Comparison ---
with col1:
    st.subheader("P/E Comparison")
    pe_data = [s for s in stocks if s.get("pe_forward") is not None]
    if pe_data:
        pe_data.sort(key=lambda x: x.get("pe_forward") or 0)
        fig_pe = go.Figure()
        fig_pe.add_trace(go.Bar(
            y=[s["symbol"] for s in pe_data],
            x=[s.get("pe_trailing") for s in pe_data],
            name="Trailing PE",
            orientation="h",
            marker_color="rgba(156, 163, 175, 0.5)",
        ))
        fig_pe.add_trace(go.Bar(
            y=[s["symbol"] for s in pe_data],
            x=[s.get("pe_forward") for s in pe_data],
            name="Forward PE",
            orientation="h",
            marker_color="rgba(59, 130, 246, 0.85)",
        ))
        fig_pe.update_layout(
            barmode="group",
            height=450,
            xaxis_title="P/E Ratio",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_pe, use_container_width=True)
    else:
        st.info("P/E data not available.")

# --- Market Cap Treemap ---
with col2:
    st.subheader("Market Cap Treemap")
    tree_data = [s for s in stocks if s.get("market_cap") and s.get("returns", {}).get("1Y") is not None]
    if tree_data:
        df_tree = pd.DataFrame([{
            "symbol": s["symbol"],
            "name": s["name"],
            "group": s["group"],
            "market_cap": s["market_cap"],
            "ytd_pct": s["returns"].get("1Y", 0) or 0,
        } for s in tree_data])

        # Format labels
        df_tree["label"] = df_tree.apply(
            lambda r: f"{r['symbol']}<br>${r['market_cap'] / 1e12:.2f}T<br>{r['ytd_pct']:+.1f}%"
            if r["market_cap"] >= 1e12
            else f"{r['symbol']}<br>${r['market_cap'] / 1e9:.0f}B<br>{r['ytd_pct']:+.1f}%",
            axis=1,
        )

        fig_tree = px.treemap(
            df_tree,
            path=["group", "label"],
            values="market_cap",
            color="ytd_pct",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
        )
        fig_tree.update_layout(
            height=450,
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_colorbar=dict(title="1Y %"),
        )
        st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("Market cap data not available.")
