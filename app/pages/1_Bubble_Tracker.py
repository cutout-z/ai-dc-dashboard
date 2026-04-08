"""Bubble Tracker — Key indicators for AI bubble risk assessment."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

st.set_page_config(page_title="Bubble Tracker", layout="wide")

DB_PATH = st.session_state.get("db_path", str(Path(__file__).parent.parent.parent / "data" / "db" / "ai_research.db"))

st.title("Bubble Tracker")

conn = sqlite3.connect(DB_PATH)

# ──────────────────────────────────────────────
# 1. HYPERSCALER CAPEX
# ──────────────────────────────────────────────
st.header("Hyperscaler CAPEX")

df_capex = pd.read_sql("""
    SELECT ticker, company, period, capex_usd
    FROM v_hyperscaler_capex
    ORDER BY period
""", conn)

if not df_capex.empty:
    df_capex["capex_bn"] = df_capex["capex_usd"] / 1e9
    df_capex["period"] = pd.to_datetime(df_capex["period"])

    # Stacked bar chart
    fig_capex = px.bar(
        df_capex,
        x="period",
        y="capex_bn",
        color="company",
        title="Quarterly CAPEX ($B)",
        labels={"capex_bn": "CAPEX ($B)", "period": "Quarter"},
        barmode="stack",
        color_discrete_map={
            "Microsoft": "#00A4EF",
            "Alphabet": "#EA4335",
            "Amazon": "#FF9900",
            "Meta": "#1877F2",
        },
    )
    fig_capex.update_layout(height=450, legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig_capex, use_container_width=True)

    # QoQ growth
    col1, col2 = st.columns(2)
    with col1:
        # Total CAPEX per quarter
        df_total = df_capex.groupby("period")["capex_bn"].sum().reset_index()
        df_total = df_total.sort_values("period")
        df_total["qoq_pct"] = df_total["capex_bn"].pct_change() * 100

        fig_total = go.Figure()
        fig_total.add_trace(go.Bar(
            x=df_total["period"], y=df_total["capex_bn"],
            name="Total CAPEX", marker_color="#4A90D9"
        ))
        fig_total.add_trace(go.Scatter(
            x=df_total["period"], y=df_total["qoq_pct"],
            name="QoQ %", yaxis="y2", line=dict(color="red", width=2),
            mode="lines+markers"
        ))
        fig_total.update_layout(
            title="Aggregate CAPEX + QoQ Growth",
            yaxis=dict(title="CAPEX ($B)"),
            yaxis2=dict(title="QoQ %", overlaying="y", side="right"),
            height=350,
            showlegend=False,
        )
        st.plotly_chart(fig_total, use_container_width=True)

    with col2:
        # Individual company trends
        fig_ind = px.line(
            df_capex,
            x="period", y="capex_bn", color="company",
            title="Individual CAPEX Trends",
            labels={"capex_bn": "$B"},
            color_discrete_map={
                "Microsoft": "#00A4EF",
                "Alphabet": "#EA4335",
                "Amazon": "#FF9900",
                "Meta": "#1877F2",
            },
        )
        fig_ind.update_layout(height=350)
        st.plotly_chart(fig_ind, use_container_width=True)
else:
    st.warning("No CAPEX data available. Run fetch_financials.py first.")

# ──────────────────────────────────────────────
# 2. SEMI DEMAND BELLWETHERS
# ──────────────────────────────────────────────
st.header("Semi Demand Bellwethers")

df_semi = pd.read_sql("""
    SELECT ticker, company, period, revenue_usd
    FROM v_semi_revenue
    ORDER BY period
""", conn)

if not df_semi.empty:
    df_semi["revenue_bn"] = df_semi["revenue_usd"] / 1e9
    df_semi["period"] = pd.to_datetime(df_semi["period"])

    # TSM reports in TWD — flag this
    tsm_mask = df_semi["ticker"] == "TSM"
    if tsm_mask.any():
        st.caption("Note: TSMC revenue is reported in TWD (not USD). Divide by ~32 for approximate USD.")

    fig_semi = px.line(
        df_semi,
        x="period", y="revenue_bn", color="company",
        title="Quarterly Revenue ($B / TWD for TSMC)",
        labels={"revenue_bn": "Revenue ($B)"},
        color_discrete_map={
            "TSMC": "#CC0000",
            "ASML": "#00529B",
            "NVIDIA": "#76B900",
        },
    )
    fig_semi.update_layout(height=400)
    st.plotly_chart(fig_semi, use_container_width=True)

# ──────────────────────────────────────────────
# 3. LLM CAPABILITY TRACKING
# ──────────────────────────────────────────────
st.header("LLM Capability Frontier")

df_elo = pd.read_sql("SELECT * FROM llm_arena_elo ORDER BY elo DESC", conn)
df_specs = pd.read_sql("SELECT * FROM llm_model_specs ORDER BY intelligence_score DESC NULLS LAST", conn)

col1, col2 = st.columns(2)

with col1:
    if not df_elo.empty:
        fig_elo = px.bar(
            df_elo.head(15),
            x="elo", y="model", color="provider",
            orientation="h",
            title="Arena Elo Ratings (Top 15)",
            labels={"elo": "Elo Score"},
        )
        fig_elo.update_layout(height=450, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_elo, use_container_width=True)

with col2:
    if not df_specs.empty:
        df_plot = df_specs.dropna(subset=["intelligence_score", "input_price_per_m_tokens"])
        if not df_plot.empty:
            fig_frontier = px.scatter(
                df_plot,
                x="input_price_per_m_tokens",
                y="intelligence_score",
                text="model",
                color="provider",
                title="Intelligence vs Cost Frontier",
                labels={
                    "input_price_per_m_tokens": "Price per 1M Input Tokens ($)",
                    "intelligence_score": "Intelligence Index",
                },
                size_max=12,
            )
            fig_frontier.update_traces(textposition="top center", textfont_size=9)
            fig_frontier.update_layout(height=450)
            st.plotly_chart(fig_frontier, use_container_width=True)

# Context window progression
if not df_specs.empty:
    df_ctx = df_specs.dropna(subset=["context_window"]).sort_values("context_window", ascending=False)
    if not df_ctx.empty:
        df_ctx["ctx_k"] = df_ctx["context_window"] / 1000
        fig_ctx = px.bar(
            df_ctx.head(10),
            x="ctx_k", y="model",
            orientation="h",
            title="Context Window Leaders (K tokens)",
            labels={"ctx_k": "Context Window (K tokens)"},
            color="provider",
        )
        fig_ctx.update_layout(height=350, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_ctx, use_container_width=True)

# ──────────────────────────────────────────────
# 4. BUBBLE RISK SUMMARY (Work mode only)
# ──────────────────────────────────────────────
st.header("Risk Summary")
st.markdown("""
    | Indicator | Signal | Direction | Notes |
    |-----------|--------|-----------|-------|
    | Hyperscaler CAPEX | Accelerating | Higher risk | Combined quarterly spend at record levels |
    | Semi demand | Strong | Supports thesis | NVDA, TSMC revenue growth sustained |
    | LLM capability | Advancing | Lower risk | Continued Elo gains justify CAPEX |
    | Model cost deflation | Rapid | Mixed | Enables adoption, compresses enabler margins |
    | Open source gap | Narrowing | Higher risk | Reduces moat for paid frontier models |

    *This table should be updated with each data refresh. Indicators flagged manually via research pass.*
    """)

conn.close()
