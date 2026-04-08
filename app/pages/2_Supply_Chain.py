"""
AI Infrastructure Supply Chain — taxonomy explorer with analyst positioning.
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="Supply Chain", layout="wide")

DB_PATH = st.session_state.get("db_path", str(Path(__file__).parent.parent.parent / "data" / "db" / "ai_research.db"))

st.title("AI Infrastructure Value Chain")

conn = sqlite3.connect(DB_PATH)

# Load taxonomy and universe
df_tax = pd.read_sql("SELECT * FROM value_chain_taxonomy", conn)
df_universe = pd.read_sql("SELECT * FROM v_full_universe WHERE included = 1", conn)

# ──────────────────────────────────────────────
# 1. TAXONOMY OVERVIEW
# ──────────────────────────────────────────────
st.header("Supply Chain Taxonomy")

# Sunburst chart of the taxonomy
if not df_universe.empty:
    df_sun = df_universe.dropna(subset=["segment", "sub_bucket"])
    if not df_sun.empty:
        fig_sun = px.sunburst(
            df_sun,
            path=["segment", "sub_bucket", "company"],
            title="AI Infrastructure — Stock Taxonomy",
            height=600,
        )
        fig_sun.update_traces(textinfo="label")
        st.plotly_chart(fig_sun, use_container_width=True)

# ──────────────────────────────────────────────
# 2. SEGMENT DRILL-DOWN
# ──────────────────────────────────────────────
st.header("Segment Analysis")

segments = sorted(df_universe["segment"].dropna().unique())
selected_segment = st.selectbox("Select segment", segments)

df_seg = df_universe[df_universe["segment"] == selected_segment].copy()

if not df_seg.empty:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"{selected_segment} — Stocks")
        # Show key fields
        display_cols = ["company", "ticker", "sub_bucket", "region"]
        if "upside_to_pt" in df_seg.columns:
            df_seg["upside_pct"] = (df_seg["upside_to_pt"] * 100).round(1)
            display_cols.append("upside_pct")
        if "bull_bear_skew" in df_seg.columns:
            display_cols.append("bull_bear_skew")
        if "materiality_latest" in df_seg.columns:
            display_cols.append("materiality_latest")
        if "pricing_power_latest" in df_seg.columns:
            display_cols.append("pricing_power_latest")

        st.dataframe(
            df_seg[display_cols].sort_values("upside_pct" if "upside_pct" in display_cols else "company", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

    with col2:
        # Bull/bear skew scatter
        df_plot = df_seg.dropna(subset=["upside_to_pt", "bull_bear_skew"])
        if not df_plot.empty:
            fig_skew = px.scatter(
                df_plot,
                x="upside_to_pt",
                y="bull_bear_skew",
                text="company",
                color="sub_bucket",
                title=f"{selected_segment} — Upside vs Bull:Bear Skew",
                labels={
                    "upside_to_pt": "Upside to Price Target",
                    "bull_bear_skew": "Bull:Bear Skew",
                },
            )
            fig_skew.update_traces(textposition="top center", textfont_size=9)
            fig_skew.update_layout(height=400)
            # Reference lines
            fig_skew.add_hline(y=1, line_dash="dash", line_color="gray", annotation_text="Skew = 1")
            fig_skew.add_vline(x=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig_skew, use_container_width=True)

# ──────────────────────────────────────────────
# 3. CROSS-SEGMENT COMPARISON
# ──────────────────────────────────────────────
st.header("Cross-Segment Positioning")

df_seg_stats = df_universe.dropna(subset=["segment", "upside_to_pt"]).groupby("segment").agg(
    stocks=("ticker", "count"),
    avg_upside=("upside_to_pt", "mean"),
    avg_skew=("bull_bear_skew", "mean"),
).reset_index()

if not df_seg_stats.empty:
    df_seg_stats["avg_upside_pct"] = (df_seg_stats["avg_upside"] * 100).round(1)

    fig_seg = px.scatter(
        df_seg_stats,
        x="avg_upside_pct",
        y="avg_skew",
        size="stocks",
        text="segment",
        title="Segment Positioning — Avg Upside vs Avg Bull:Bear Skew",
        labels={
            "avg_upside_pct": "Avg Upside to PT (%)",
            "avg_skew": "Avg Bull:Bear Skew",
        },
    )
    fig_seg.update_traces(textposition="top center")
    fig_seg.update_layout(height=450)
    fig_seg.add_hline(y=1, line_dash="dash", line_color="gray")
    fig_seg.add_vline(x=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_seg, use_container_width=True)

conn.close()
