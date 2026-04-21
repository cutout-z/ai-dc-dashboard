"""Investment Prospecting — Screen the mapping universe by AI exposure, materiality, pricing power."""

import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = st.session_state["db_path"]

st.title("Prospecting")

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql("SELECT * FROM mapping", conn)

# ──────────────────────────────────────────────
# FILTERS
# ──────────────────────────────────────────────
st.sidebar.header("Screening Filters")

regions = ["All"] + sorted(df["region"].dropna().unique().tolist())
sel_region = st.sidebar.multiselect("Region", regions, default=["All"])

exposures = sorted(df["exposure_latest"].dropna().unique().tolist())
sel_exposure = st.sidebar.multiselect("AI Exposure", exposures, default=["Adopter", "Enabler", "Enabler/Adopter"])

materialities = ["Core to Thesis", "Significant", "Moderate", "Insignificant", "Don't Know"]
sel_materiality = st.sidebar.multiselect("Materiality (min)", materialities, default=["Core to Thesis", "Significant"])

pricing = ["High", "Neutral", "Low"]
sel_pricing = st.sidebar.multiselect("Pricing Power", pricing, default=["High"])

min_trend = st.sidebar.slider("Min materiality trend (wave upgrades)", -3, 3, 0)

cap_range = st.sidebar.slider(
    "Market Cap ($M USD)",
    min_value=0,
    max_value=int(df["market_cap_usd_m"].max()) + 1000,
    value=(0, int(df["market_cap_usd_m"].max()) + 1000),
    step=1000,
)

sectors = ["All"] + sorted(df["gics_sector"].dropna().unique().tolist())
sel_sector = st.sidebar.multiselect("GICS Sector", sectors, default=["All"])

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

display_cols = [
    "ticker", "company", "region", "gics_sector", "gics_industry",
    "market_cap_usd_m",
]
display_cols = [c for c in display_cols if c in df_filtered.columns]

st.dataframe(
    df_filtered[display_cols].sort_values("market_cap_usd_m", ascending=False),
    use_container_width=True,
    hide_index=True,
    height=500,
)

conn.close()
