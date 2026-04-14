"""News — earnings calendars and curated AI/DC news feed."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from app.lib.equities import (
    ANZ_EARNINGS_TICKERS,
    MAG7_AI_STOCKS,
    fetch_earnings_dates,
)
from app.lib.news import BUCKETS, fetch_news_buckets

st.title("News")
st.caption("Earnings calendars for key players + curated AI/DC news feed.")

# ══════════════════════════════════════════════
# 1. EARNINGS CALENDARS
# ══════════════════════════════════════════════
st.header("Earnings Calendar")

# Build ticker → metadata lookup
global_tickers = [
    {"symbol": s["symbol"], "name": s["name"], "group": s["group"], "region": "US"}
    for s in MAG7_AI_STOCKS
]
anz_tickers = [
    {"symbol": s["symbol"], "name": s["name"], "group": "ANZ DC / Infra", "region": s["region"]}
    for s in ANZ_EARNINGS_TICKERS
]
all_tickers = global_tickers + anz_tickers

with st.spinner("Fetching earnings dates..."):
    dates = fetch_earnings_dates(tuple(t["symbol"] for t in all_tickers))


def _parse_date(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return None


rows = []
now = pd.Timestamp.now()
for t in all_tickers:
    ed = _parse_date(dates.get(t["symbol"]))
    days_away = (ed - now).days if ed is not None else None
    rows.append({
        "Ticker": t["symbol"],
        "Name": t["name"],
        "Group": t["group"],
        "Region": t["region"],
        "Earnings Date": ed.strftime("%Y-%m-%d") if ed is not None else "—",
        "Days Away": days_away,
        "_sort": ed if ed is not None else pd.Timestamp.max,
    })

df_earn = pd.DataFrame(rows).sort_values("_sort").drop(columns=["_sort"])
# Drop past earnings (negative days) — yfinance sometimes returns the last reported date
df_earn = df_earn[df_earn["Days Away"].isna() | (df_earn["Days Away"] >= 0)]

# Split into two tiles: Global and ANZ
col_global, col_anz = st.columns(2)

with col_global:
    with st.container(border=True):
        st.subheader("Global (Mag 7 + AI Infra + DC Operators)")
        df_g = df_earn[df_earn["Region"] == "US"].drop(columns=["Region"])
        st.dataframe(df_g, use_container_width=True, hide_index=True, height=35 * (len(df_g) + 1) + 3)

with col_anz:
    with st.container(border=True):
        st.subheader("ANZ")
        df_a = df_earn[df_earn["Region"] == "ANZ"].drop(columns=["Region"])
        st.dataframe(df_a, use_container_width=True, hide_index=True, height=35 * (len(df_a) + 1) + 3)

# ══════════════════════════════════════════════
# 2. NEWS FEED
# ══════════════════════════════════════════════
st.header("News Feed")
st.caption("Google News + curated DC feeds. Cached 30 minutes. All topics merged.")

# Dot / label colour per bucket
_BUCKET_COLORS: dict[str, str] = {
    "Frontier Labs":           "#ef4444",  # red
    "Hyperscaler CAPEX":       "#3b82f6",  # blue
    "Supply Chain":            "#a855f7",  # purple
    "Model Releases":          "#22c55e",  # green
    "ANZ DC":                  "#14b8a6",  # teal
    "China / Export Controls": "#f59e0b",  # amber
}

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("Refresh", use_container_width=True):
        fetch_news_buckets.clear()

with st.spinner("Fetching news..."):
    news_data = fetch_news_buckets()

if not any(news_data.values()):
    st.warning("No news items fetched. Check network connectivity.")
else:
    # Flatten all buckets → single chronological feed (deduplicated by URL)
    all_items: list[dict] = []
    seen_urls: set[str] = set()
    for bucket_label, items in news_data.items():
        for it in items:
            if it["url"] not in seen_urls:
                seen_urls.add(it["url"])
                all_items.append({**it, "bucket": bucket_label})

    all_items.sort(key=lambda x: x["published"] or "", reverse=True)

    # Build one HTML block for the entire feed
    rows_html: list[str] = []
    for it in all_items:
        bucket = it["bucket"]
        color  = _BUCKET_COLORS.get(bucket, "#6b7280")
        title  = it["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        source = it["source"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        age    = it["age_str"]
        url    = it["url"]

        rows_html.append(f"""
<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 2px 6px;">
  <span style="margin-top:5px;width:7px;height:7px;border-radius:50%;
               background:{color};flex-shrink:0;display:inline-block;"></span>
  <div style="min-width:0;">
    <a href="{url}" target="_blank" rel="noopener"
       style="color:#e2e8f0;text-decoration:none;font-size:13px;line-height:1.45;">
      {title}
    </a>
    <div style="margin-top:3px;font-size:11px;color:#6b7280;">
      {source}&nbsp;·&nbsp;{age}
      &nbsp;&nbsp;<span style="color:{color};font-weight:500;font-size:10px;">{bucket}</span>
    </div>
  </div>
</div>
<div style="border-top:1px solid #1e293b;margin:0 0 0 17px;"></div>""")

    with st.container(border=True):
        st.markdown("\n".join(rows_html), unsafe_allow_html=True)
