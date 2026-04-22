"""Investment Prospecting — Screen the AI/tech universe by ETF overlap and sector.

Universe is derived from CHAT, AIQ, BOTZ, ROBT ETF top holdings — no private data.
Refresh via: python etl/fetch_etf_holdings.py
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

UNIVERSE_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "processed" / "etf_universe.json"
)

st.title("Prospecting")
st.caption(
    "Universe derived from ETF holdings: **CHAT · AIQ · BOTZ · ROBT**. "
    "AI Tier = ETF overlap count (Core = 3+, High = 2, Moderate = 1)."
)

# ──────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────
if not UNIVERSE_PATH.exists():
    st.warning(
        "ETF universe not yet built. Run from the repo root:\n\n"
        "```bash\npython etl/fetch_etf_holdings.py\n```\n\n"
        "This fetches ~100–200 tickers from the 4 ETFs and saves them to "
        "`data/processed/etf_universe.json`."
    )
    st.stop()

with open(UNIVERSE_PATH) as f:
    data = json.load(f)

df = pd.DataFrame(data.get("universe", []))

if df.empty:
    st.error("Universe file is empty. Re-run `python etl/fetch_etf_holdings.py`.")
    st.stop()

updated = data.get("updated", "unknown")
st.caption(
    f"Last refreshed: **{updated[:10]}** · "
    f"{data.get('ticker_count', len(df))} tickers · "
    f"ETFs: {', '.join(data.get('etfs', []))} · "
    "⚠ Market cap for foreign-listed tickers (KS, T suffix) may be in local currency — use for tier/sector filtering, not cap comparison"
)

# ──────────────────────────────────────────────
# FILTERS
# ──────────────────────────────────────────────
st.sidebar.header("Screening Filters")

tier_order = ["Core", "High", "Moderate"]
sel_tier = st.sidebar.multiselect(
    "AI Tier",
    tier_order,
    default=["Core", "High"],
    help="Core = in 3+ ETFs · High = 2 ETFs · Moderate = 1 ETF",
)

regions = sorted(df["region"].dropna().unique().tolist())
sel_region = st.sidebar.multiselect("Region", ["All"] + regions, default=["All"])

sectors = sorted(df["gics_sector"].dropna().replace("", pd.NA).dropna().unique().tolist())
sel_sector = st.sidebar.multiselect("GICS Sector", ["All"] + sectors, default=["All"])

etf_opts = sorted(
    {e for row in df["etfs_in"] for e in (row if isinstance(row, list) else [])}
)
sel_etf = st.sidebar.multiselect(
    "Must include ETF",
    etf_opts,
    default=[],
    help="Filter to tickers that appear in ALL selected ETFs",
)

max_cap = max(int(df["market_cap_usd_m"].max() or 3_000_000), 1)
cap_range = st.sidebar.slider(
    "Market Cap ($M USD)", min_value=0, max_value=max_cap,
    value=(0, max_cap), step=max(max_cap // 100, 1_000),
)

# ──────────────────────────────────────────────
# FILTER
# ──────────────────────────────────────────────
mask = pd.Series(True, index=df.index)

if sel_tier:
    mask &= df["ai_tier"].isin(sel_tier)
if "All" not in sel_region and sel_region:
    mask &= df["region"].isin(sel_region)
if "All" not in sel_sector and sel_sector:
    mask &= df["gics_sector"].isin(sel_sector)
if sel_etf:
    mask &= df["etfs_in"].apply(
        lambda lst: all(e in (lst or []) for e in sel_etf)
    )
mask &= df["market_cap_usd_m"].fillna(0).between(cap_range[0], cap_range[1])

df_filtered = df[mask].sort_values("market_cap_usd_m", ascending=False).copy()

# ──────────────────────────────────────────────
# SUMMARY METRICS
# ──────────────────────────────────────────────
col_a, col_b, col_c = st.columns(3)
col_a.metric("Stocks", len(df_filtered))
col_b.metric("Core (3+ ETFs)", int((df_filtered["ai_tier"] == "Core").sum()))
col_c.metric(
    "Median Mkt Cap",
    f"${df_filtered['market_cap_usd_m'].median():,.0f}M"
    if not df_filtered.empty else "—",
)

# ──────────────────────────────────────────────
# RESULTS TABLE
# ──────────────────────────────────────────────
st.subheader(f"Screener Results — {len(df_filtered)} stocks")

display_cols = [
    "ticker", "company", "region", "gics_sector", "gics_industry",
    "market_cap_usd_m", "ai_tier", "etf_count", "etfs_in",
]
display_cols = [c for c in display_cols if c in df_filtered.columns]

st.dataframe(
    df_filtered[display_cols],
    use_container_width=True,
    hide_index=True,
    height=550,
    column_config={
        "ticker":           st.column_config.TextColumn("Ticker"),
        "company":          st.column_config.TextColumn("Company"),
        "region":           st.column_config.TextColumn("Region"),
        "gics_sector":      st.column_config.TextColumn("Sector"),
        "gics_industry":    st.column_config.TextColumn("Industry"),
        "market_cap_usd_m": st.column_config.NumberColumn("Mkt Cap ($M)", format="%.0f"),
        "ai_tier":          st.column_config.TextColumn("AI Tier"),
        "etf_count":        st.column_config.NumberColumn("ETF Count"),
        "etfs_in":          st.column_config.ListColumn("ETFs"),
    },
)

st.caption(
    "Refresh universe: `python etl/fetch_etf_holdings.py` "
    "(fetches live ETF holdings from Yahoo Finance, ~5–10 min)"
)
