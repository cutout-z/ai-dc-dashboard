"""
Investment Prospecting — Screen 3,594 stocks by AI exposure, materiality,
pricing power, and wave evolution. Personal mode focus.
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="Prospecting", layout="wide")

DB_PATH = st.session_state.get("db_path", str(Path(__file__).parent.parent.parent / "data" / "db" / "ai_research.db"))
mode = st.session_state.get("mode", "Personal")

st.title("AI Investment Prospecting")

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql("SELECT * FROM mapping", conn)

# ──────────────────────────────────────────────
# FILTERS
# ──────────────────────────────────────────────
st.sidebar.header("Screening Filters")

# Region
regions = ["All"] + sorted(df["region"].dropna().unique().tolist())
sel_region = st.sidebar.multiselect("Region", regions, default=["All"])

# Exposure
exposures = sorted(df["exposure_latest"].dropna().unique().tolist())
sel_exposure = st.sidebar.multiselect("AI Exposure", exposures, default=["Adopter", "Enabler", "Enabler/Adopter"])

# Materiality
materialities = ["Core to Thesis", "Significant", "Moderate", "Insignificant", "Don't Know"]
sel_materiality = st.sidebar.multiselect("Materiality (min)", materialities, default=["Core to Thesis", "Significant"])

# Pricing Power
pricing = ["High", "Neutral", "Low"]
sel_pricing = st.sidebar.multiselect("Pricing Power", pricing, default=["High"])

# Materiality trend
min_trend = st.sidebar.slider("Min materiality trend (wave upgrades)", -3, 3, 0)

# Market cap
cap_range = st.sidebar.slider(
    "Market Cap ($M USD)",
    min_value=0,
    max_value=int(df["market_cap_usd_m"].max()) + 1000,
    value=(0, int(df["market_cap_usd_m"].max()) + 1000),
    step=1000,
)

# GICS Sector
sectors = ["All"] + sorted(df["gics_sector"].dropna().unique().tolist())
sel_sector = st.sidebar.multiselect("GICS Sector", sectors, default=["All"])

# Apply filters
mask = pd.Series(True, index=df.index)

if "All" not in sel_region:
    mask &= df["region"].isin(sel_region)
if sel_exposure:
    mask &= df["exposure_latest"].isin(sel_exposure)
if sel_materiality:
    mask &= df["materiality_latest"].isin(sel_materiality)
if sel_pricing:
    mask &= df["pricing_power_latest"].isin(sel_pricing)
if min_trend > -3:
    mask &= df["materiality_trend"].fillna(-99) >= min_trend
mask &= df["market_cap_usd_m"].fillna(0).between(cap_range[0], cap_range[1])
if "All" not in sel_sector:
    mask &= df["gics_sector"].isin(sel_sector)

df_filtered = df[mask].copy()

# ──────────────────────────────────────────────
# RESULTS
# ──────────────────────────────────────────────
st.subheader(f"Screener Results — {len(df_filtered)} stocks")

# Display table
display_cols = [
    "ticker", "company", "region", "gics_sector", "gics_industry",
    "market_cap_usd_m", "exposure_latest", "materiality_latest",
    "pricing_power_latest", "materiality_trend", "alpha_flag",
]
display_cols = [c for c in display_cols if c in df_filtered.columns]

st.dataframe(
    df_filtered[display_cols].sort_values("market_cap_usd_m", ascending=False),
    use_container_width=True,
    hide_index=True,
    height=500,
)

# ──────────────────────────────────────────────
# WAVE EVOLUTION
# ──────────────────────────────────────────────
st.header("Wave Evolution")

col1, col2 = st.columns(2)

with col1:
    # Materiality distribution across waves
    wave_data = []
    for w in range(1, 6):
        col_name = f"materiality_w{w}"
        if col_name in df_filtered.columns:
            counts = df_filtered[col_name].value_counts()
            for cat, count in counts.items():
                if cat and str(cat) not in ("None", "nan"):
                    wave_data.append({"wave": f"Wave {w}", "materiality": str(cat), "count": count})

    if wave_data:
        df_wave = pd.DataFrame(wave_data)
        # Order materiality categories
        mat_order = ["Core to Thesis", "Significant", "Moderate", "Insignificant", "Don't Know"]
        df_wave["materiality"] = pd.Categorical(df_wave["materiality"], categories=mat_order, ordered=True)

        fig_wave = px.bar(
            df_wave.sort_values("materiality"),
            x="wave", y="count", color="materiality",
            title="Materiality Distribution Across Waves (Filtered)",
            barmode="stack",
            color_discrete_map={
                "Core to Thesis": "#1a472a",
                "Significant": "#2d8659",
                "Moderate": "#ffc107",
                "Insignificant": "#e0e0e0",
                "Don't Know": "#999999",
            },
        )
        fig_wave.update_layout(height=400)
        st.plotly_chart(fig_wave, use_container_width=True)

with col2:
    # Pricing power distribution across waves
    pp_data = []
    for w in range(1, 6):
        col_name = f"pricing_power_w{w}"
        if col_name in df_filtered.columns:
            counts = df_filtered[col_name].value_counts()
            for cat, count in counts.items():
                if cat and str(cat) not in ("None", "nan"):
                    pp_data.append({"wave": f"Wave {w}", "pricing_power": str(cat), "count": count})

    if pp_data:
        df_pp = pd.DataFrame(pp_data)
        pp_order = ["High", "Neutral", "Low"]
        df_pp["pricing_power"] = pd.Categorical(df_pp["pricing_power"], categories=pp_order, ordered=True)

        fig_pp = px.bar(
            df_pp.sort_values("pricing_power"),
            x="wave", y="count", color="pricing_power",
            title="Pricing Power Distribution Across Waves (Filtered)",
            barmode="stack",
            color_discrete_map={
                "High": "#1a472a",
                "Neutral": "#ffc107",
                "Low": "#dc3545",
            },
        )
        fig_pp.update_layout(height=400)
        st.plotly_chart(fig_pp, use_container_width=True)

# ──────────────────────────────────────────────
# MATERIALITY UPGRADERS
# ──────────────────────────────────────────────
st.header("Materiality Upgraders")
st.caption("Stocks where analysts have progressively upgraded AI's materiality to the thesis")

df_upgraders = df_filtered[df_filtered["materiality_trend"] > 0].sort_values(
    ["materiality_trend", "market_cap_usd_m"], ascending=[False, False]
)

if not df_upgraders.empty:
    upgrade_cols = [
        "ticker", "company", "region", "gics_sector",
        "materiality_w1", "materiality_w2", "materiality_w3",
        "materiality_w4", "materiality_w5", "materiality_trend",
        "pricing_power_latest", "market_cap_usd_m",
    ]
    upgrade_cols = [c for c in upgrade_cols if c in df_upgraders.columns]
    st.dataframe(df_upgraders[upgrade_cols], use_container_width=True, hide_index=True, height=400)
else:
    st.info("No materiality upgraders in filtered set.")

# ──────────────────────────────────────────────
# SCATTER: MARKET CAP vs MATERIALITY
# ──────────────────────────────────────────────
st.header("Universe Map")

df_plot = df_filtered.dropna(subset=["market_cap_usd_m", "materiality_score"]).copy()
if not df_plot.empty:
    df_plot["log_mcap"] = df_plot["market_cap_usd_m"].apply(lambda x: max(x, 1))

    fig_map = px.scatter(
        df_plot,
        x="materiality_score",
        y="log_mcap",
        color="exposure_latest",
        hover_name="company",
        hover_data=["ticker", "region", "pricing_power_latest"],
        title="Universe Map — Materiality vs Market Cap",
        labels={
            "materiality_score": "Materiality Score (1=Insignificant, 4=Core)",
            "log_mcap": "Market Cap ($M USD)",
        },
        log_y=True,
    )
    fig_map.update_layout(height=500)
    st.plotly_chart(fig_map, use_container_width=True)

conn.close()
