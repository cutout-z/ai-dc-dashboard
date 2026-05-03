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
from app.lib.news_scoring import (
    TIER_COLORS, TIER_LABELS,
    TIER_HIGH_THRESHOLD, TIER_MEDIUM_THRESHOLD,
    get_materiality_tier,
)

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
# 2. NEWS FEED — materiality-ranked
# ══════════════════════════════════════════════
st.header("News Feed")
st.caption(
    "Ranked by materiality — source trust, ticker relevance, and recency. "
    "Google News + curated DC feeds. Cached 30 min."
)

# Dot / label colour per bucket
_BUCKET_COLORS: dict[str, str] = {
    "Frontier Labs":           "#ef4444",  # red
    "Hyperscaler CAPEX":       "#3b82f6",  # blue
    "Supply Chain":            "#a855f7",  # purple
    "Model Releases":          "#22c55e",  # green
    "ANZ DC":                  "#14b8a6",  # teal
    "China / Export Controls": "#f59e0b",  # amber
}

col_refresh, col_filter, _ = st.columns([1, 1, 4])
with col_refresh:
    if st.button("Refresh", use_container_width=True):
        fetch_news_buckets.clear()
with col_filter:
    show_low = st.toggle("Show low-materiality", value=False)

with st.spinner("Fetching news..."):
    news_data = fetch_news_buckets()

if not any(news_data.values()):
    st.warning("No news items fetched. Check network connectivity.")
else:
    # Flatten all buckets → single feed (deduplicated by URL)
    all_items: list[dict] = []
    seen_urls: set[str] = set()
    for bucket_label, items in news_data.items():
        for it in items:
            if it["url"] not in seen_urls:
                seen_urls.add(it["url"])
                all_items.append({
                    **it,
                    "bucket": bucket_label,
                    "tier": get_materiality_tier(it.get("materiality_score", 0)),
                })

    # PRIMARY: materiality score desc — SECONDARY: published desc
    all_items.sort(
        key=lambda x: (x.get("materiality_score", 0), x.get("published") or ""),
        reverse=True,
    )

    # Group by tier
    tier_groups: dict[str, list[dict]] = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for it in all_items:
        tier_groups[it["tier"]].append(it)

    total = len(all_items)
    high_n = len(tier_groups["HIGH"])
    med_n = len(tier_groups["MEDIUM"])
    low_n = len(tier_groups["LOW"])

    # Summary metrics
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Total", total)
    col_m2.metric("High", high_n)
    col_m3.metric("Medium", med_n)
    col_m4.metric("Low", low_n)

    def _render_tier(tier: str, items: list[dict]) -> str:
        """Build HTML for a tier section."""
        if not items:
            return ""
        tier_color = TIER_COLORS[tier]
        tier_label = TIER_LABELS[tier]
        header = f"""
<div style="display:flex;align-items:center;gap:8px;padding:12px 0 6px;">
  <span style="font-size:14px;font-weight:600;color:{tier_color};">{tier_label}</span>
  <span style="font-size:11px;color:#6b7280;">({len(items)} items)</span>
</div>"""
        rows: list[str] = []
        for it in items:
            bucket = it["bucket"]
            bkt_color = _BUCKET_COLORS.get(bucket, "#6b7280")
            title = it["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            source = it["source"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            age = it["age_str"]
            url = it["url"]
            score = it.get("materiality_score", 0)
            bar_pct = max(int(score * 100), 2)

            rows.append(f"""
<div style="display:flex;align-items:flex-start;gap:10px;padding:7px 2px 5px;">
  <div style="margin-top:6px;width:40px;flex-shrink:0;">
    <div style="width:100%;height:4px;background:#1e293b;border-radius:2px;">
      <div style="width:{bar_pct}%;height:4px;background:{tier_color};border-radius:2px;"></div>
    </div>
    <div style="font-size:9px;color:#6b7280;text-align:center;margin-top:1px;">{score:.2f}</div>
  </div>
  <div style="min-width:0;">
    <a href="{url}" target="_blank" rel="noopener"
       style="color:#e2e8f0;text-decoration:none;font-size:13px;line-height:1.45;">
      {title}
    </a>
    <div style="margin-top:3px;font-size:11px;color:#6b7280;">
      {source}&nbsp;·&nbsp;{age}
      &nbsp;&nbsp;<span style="color:{bkt_color};font-weight:500;font-size:10px;">{bucket}</span>
    </div>
  </div>
</div>
<div style="border-top:1px solid #1e293b;margin:0 0 0 52px;"></div>""")
        return header + "\n".join(rows)

    html_parts: list[str] = []
    html_parts.append(_render_tier("HIGH", tier_groups["HIGH"]))
    html_parts.append(_render_tier("MEDIUM", tier_groups["MEDIUM"]))
    if show_low:
        html_parts.append(_render_tier("LOW", tier_groups["LOW"]))

    with st.container(border=True):
        st.markdown("\n".join(p for p in html_parts if p), unsafe_allow_html=True)
