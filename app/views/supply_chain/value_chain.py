"""AI Infrastructure Value Chain — taxonomy + per-segment stock tiles."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import yfinance as yf

logger = logging.getLogger("ai_research")

TOP_N_PER_SEGMENT = 10
TILE_ROW_HEIGHT = 35

def _yf_ticker(sym: str) -> str:
    """Convert Reuters RIC suffix to yfinance format.

    Reuters uses .N (NYSE) and .O (NASDAQ) — yfinance uses no suffix for US stocks.
    """
    if sym.endswith(".N") or sym.endswith(".O"):
        return sym.rsplit(".", 1)[0]
    return sym


@st.cache_data(ttl=3600)
def _fetch_market_caps(tickers: tuple[str, ...]) -> dict[str, float | None]:
    """Fetch market caps for a batch of tickers via yfinance fast_info."""
    results: dict[str, float | None] = {}

    def _get(sym: str) -> tuple[str, float | None]:
        try:
            fi = yf.Ticker(_yf_ticker(sym)).fast_info
            return sym, getattr(fi, "market_cap", None)
        except Exception as e:
            logger.debug("Market cap %s error: %s", sym, e)
            return sym, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        for sym, cap in pool.map(lambda s: _get(s), tickers):
            results[sym] = cap
    return results


def _fmt_mcap(v) -> str:
    if pd.isna(v) or v is None:
        return "—"
    v = float(v)
    if v >= 1e12:
        return f"${v / 1e12:.1f}T"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:,.0f}"


DB_PATH = st.session_state["db_path"]

st.title("AI Infra Value Chain")

conn = sqlite3.connect(DB_PATH)

df_universe = pd.read_sql("SELECT * FROM v_full_universe WHERE included = 1", conn)

# ──────────────────────────────────────────────
# 1. TAXONOMY OVERVIEW
# ──────────────────────────────────────────────
st.header("Supply Chain Taxonomy")
st.caption("Click any segment or sub-bucket to drill down. Click the centre to zoom back out.")

if not df_universe.empty:
    df_sun = df_universe.dropna(subset=["segment", "sub_bucket"])
    if not df_sun.empty:
        fig_sun = px.sunburst(
            df_sun,
            path=["segment", "sub_bucket", "company"],
            title="AI Infrastructure — Stock Taxonomy",
            height=1200,
        )
        fig_sun.update_traces(textinfo="label", insidetextorientation="radial")
        st.plotly_chart(fig_sun, use_container_width=True)

# ──────────────────────────────────────────────
# 2. PER-SEGMENT TILES
# ──────────────────────────────────────────────
st.header("Segments")
st.caption(
    f"Top {TOP_N_PER_SEGMENT} per segment. "
    "Click a column header to sort. Scroll tile for more rows."
)

# Prepare display columns
df_display = df_universe.copy()

# Fetch market caps for all tickers
all_tickers = tuple(df_display["ticker"].dropna().unique())
with st.spinner("Fetching market caps..."):
    mcap_map = _fetch_market_caps(all_tickers)
df_display["market_cap_raw"] = df_display["ticker"].map(mcap_map)
df_display["market_cap"] = df_display["market_cap_raw"].apply(_fmt_mcap)

segments = [s for s in sorted(df_display["segment"].dropna().unique())]

for segment in segments:
    df_seg = df_display[df_display["segment"] == segment].copy()
    if df_seg.empty:
        continue

    display_cols = ["company", "ticker", "sub_bucket", "region", "market_cap"]

    display_cols = [c for c in display_cols if c in df_seg.columns]

    df_seg_sorted = df_seg.sort_values("market_cap_raw", ascending=False, na_position="last")

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
                    "market_cap": "Market Cap",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=tile_height,
            column_config={
                "Company": st.column_config.TextColumn(width=220),
                "Ticker": st.column_config.TextColumn(width=120),
                "Sub-bucket": st.column_config.TextColumn(width=220),
                "Region": st.column_config.TextColumn(width=150),
                "Market Cap": st.column_config.TextColumn(width=100),
            },
        )

conn.close()
