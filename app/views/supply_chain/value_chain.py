"""AI Infrastructure Value Chain — taxonomy + per-segment stock tiles."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

# Feature toggles — keeping code for later but hidden per request.
# Re-enable once the underlying bull:bear skew data is refreshed.
SHOW_SKEW_SCATTER = False
SHOW_CROSS_SEGMENT = False

TOP_N_PER_SEGMENT = 10
TILE_ROW_HEIGHT = 35

DB_PATH = st.session_state["db_path"]

st.title("AI Infra Value Chain")

conn = sqlite3.connect(DB_PATH)

df_universe = pd.read_sql("SELECT * FROM v_full_universe WHERE included = 1", conn)

# ──────────────────────────────────────────────
# 1. TAXONOMY OVERVIEW
# ──────────────────────────────────────────────
st.header("Supply Chain Taxonomy")

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
# 2. PER-SEGMENT TILES
# ──────────────────────────────────────────────
st.header("Segments")
st.caption(
    f"Top {TOP_N_PER_SEGMENT} per segment by analyst upside. "
    "Click a column header to sort. Scroll tile for more rows."
)

# Prepare display columns
df_display = df_universe.copy()
if "upside_to_pt" in df_display.columns:
    df_display["upside_pct"] = (df_display["upside_to_pt"] * 100).round(1)

segments = [s for s in sorted(df_display["segment"].dropna().unique())]

for segment in segments:
    df_seg = df_display[df_display["segment"] == segment].copy()
    if df_seg.empty:
        continue

    display_cols = ["company", "ticker", "sub_bucket", "region"]
    if "upside_pct" in df_seg.columns:
        display_cols.append("upside_pct")
    if "bull_bear_skew" in df_seg.columns:
        display_cols.append("bull_bear_skew")
    if "materiality_latest" in df_seg.columns:
        display_cols.append("materiality_latest")
    if "pricing_power_latest" in df_seg.columns:
        display_cols.append("pricing_power_latest")

    display_cols = [c for c in display_cols if c in df_seg.columns]

    sort_col = "upside_pct" if "upside_pct" in display_cols else "company"
    df_seg_sorted = df_seg.sort_values(sort_col, ascending=False)

    # Visible rows = top N; full dataset is still in the frame (scrollable)
    visible_rows = min(TOP_N_PER_SEGMENT, len(df_seg_sorted))
    tile_height = TILE_ROW_HEIGHT * (visible_rows + 1) + 3

    with st.container(border=True):
        st.subheader(f"{segment} ({len(df_seg_sorted)})")
        st.dataframe(
            df_seg_sorted[display_cols].rename(
                columns={
                    "company": "Company",
                    "ticker": "Ticker",
                    "sub_bucket": "Sub-bucket",
                    "region": "Region",
                    "upside_pct": "Upside %",
                    "bull_bear_skew": "Bull:Bear",
                    "materiality_latest": "Materiality",
                    "pricing_power_latest": "Pricing Power",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=tile_height,
        )

# ──────────────────────────────────────────────
# 3. BULL:BEAR SKEW SCATTER  (hidden by feature toggle)
# ──────────────────────────────────────────────
if SHOW_SKEW_SCATTER:
    st.header("Bull:Bear Skew")
    segments = sorted(df_universe["segment"].dropna().unique())
    selected_segment = st.selectbox("Segment", segments)
    df_seg = df_universe[df_universe["segment"] == selected_segment].copy()
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
        fig_skew.add_hline(y=1, line_dash="dash", line_color="gray", annotation_text="Skew = 1")
        fig_skew.add_vline(x=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_skew, use_container_width=True)

# ──────────────────────────────────────────────
# 4. CROSS-SEGMENT POSITIONING  (hidden by feature toggle)
# ──────────────────────────────────────────────
if SHOW_CROSS_SEGMENT:
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
