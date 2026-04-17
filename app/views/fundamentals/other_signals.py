"""Other Signals — semi demand bellwethers (TSMC, ASML, NVIDIA revenue)."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

from app.lib.fx import convert_to_usd

DB_PATH = st.session_state["db_path"]
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"

st.title("Other Signals")
st.caption("Semi demand bellwethers — TSMC, ASML, and NVIDIA revenue as leading indicators for AI hardware demand.")

conn = sqlite3.connect(DB_PATH)

# ══════════════════════════════════════════════
# SEMI DEMAND BELLWETHERS
# ══════════════════════════════════════════════
st.header("Semi Demand Bellwethers")
st.caption(
    "TSMC monthly revenue is the highest-frequency public signal for AI hardware demand across the full value chain. "
    "ASML orders are a 6–12 month leading indicator of new node capacity. "
    "NVDA captures direct AI accelerator demand."
)

df_semi = pd.read_sql(
    """
    SELECT ticker, company, period, revenue_usd
    FROM v_semi_revenue
    ORDER BY period
    """,
    conn,
)

if not df_semi.empty:
    df_semi["period"] = pd.to_datetime(df_semi["period"])

    # The ETL stamps every row 'USD' but TSMC reports in TWD and ASML in EUR.
    # Convert each ticker's native currency to USD using historical Yahoo rates
    # so the chart compares like-for-like.
    df_semi["revenue_native"] = df_semi["revenue_usd"]
    for ticker, pair in [("TSM", "USDTWD=X"), ("ASML", "USDEUR=X")]:
        mask = df_semi["ticker"] == ticker
        if mask.any():
            df_semi.loc[mask, "revenue_native"] = convert_to_usd(
                df_semi.loc[mask, "revenue_usd"],
                df_semi.loc[mask, "period"],
                pair,
            )
    df_semi["revenue_bn"] = df_semi["revenue_native"] / 1e9

    st.caption(
        "TSMC and ASML converted to USD using historical Yahoo FX rates "
        "(USDTWD, USDEUR) at each reporting date."
    )

    fig_semi = px.line(
        df_semi, x="period", y="revenue_bn", color="company",
        title="Quarterly Revenue ($B USD)",
        labels={"revenue_bn": "Revenue ($B)"},
        color_discrete_map={"TSMC": "#CC0000", "ASML": "#00529B", "NVIDIA": "#76B900"},
    )
    fig_semi.update_layout(height=400)
    st.plotly_chart(fig_semi, use_container_width=True)

# --- TSMC Monthly Revenue ---
st.subheader("TSMC Monthly Revenue")
st.caption("Higher frequency signal than quarterly earnings. Converted to USD using historical Yahoo USDTWD rates.")

tsmc_path = DATA_DIR / "tsmc_monthly_revenue.csv"
if tsmc_path.exists():
    df_tsmc = pd.read_csv(tsmc_path)
    df_tsmc["date"] = pd.to_datetime(df_tsmc[["year", "month"]].assign(day=1))
    # Convert TWD billions → USD billions using historical FX
    df_tsmc["revenue_usd_b"] = convert_to_usd(
        df_tsmc["revenue_twd_b"], df_tsmc["date"], "USDTWD=X"
    )

    col1, col2 = st.columns(2)
    with col1:
        fig_rev = go.Figure()
        fig_rev.add_trace(go.Bar(
            x=df_tsmc["date"],
            y=df_tsmc["revenue_usd_b"],
            marker_color="#CC0000",
            customdata=df_tsmc["revenue_twd_b"],
            hovertemplate="%{x|%b %Y}<br>$%{y:.2f}B USD<br>%{customdata:.1f}B TWD<extra></extra>",
        ))
        fig_rev.update_layout(
            title="Monthly Revenue ($B USD)",
            yaxis_title="$B USD",
            height=350,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_rev, use_container_width=True)
    with col2:
        fig_yoy = go.Figure()
        fig_yoy.add_trace(go.Scatter(x=df_tsmc["date"], y=df_tsmc["yoy_pct"], mode="lines+markers",
                                      line=dict(color="#76B900", width=2), fill="tozeroy", fillcolor="rgba(118,185,0,0.1)"))
        fig_yoy.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_yoy.update_layout(title="YoY Growth %", yaxis_title="YoY %", height=350, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_yoy, use_container_width=True)

conn.close()
