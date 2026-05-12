"""News — earnings calendars and curated AI/DC news feed."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from app.lib.equities import (
    ANZ_EARNINGS_TICKERS,
    MAG7_AI_STOCKS,
    fetch_earnings_dates,
)
from app.lib.news import fetch_news_buckets, flatten_news_buckets
from app.lib.news_scoring import (
    TIER_COLORS,
    TIER_LABELS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NEWS_CATALOG_PATH = PROJECT_ROOT / "data" / "reference" / "news_catalog.csv"

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
    stale = days_away is not None and days_away < 0
    rows.append({
        "Ticker": t["symbol"],
        "Name": t["name"],
        "Group": t["group"],
        "Region": t["region"],
        "Earnings Date": "—" if stale or ed is None else ed.strftime("%Y-%m-%d"),
        "Days Away": str(days_away) if not stale and days_away is not None else "—",
        "Status": "Awaiting next date" if stale else ("Unavailable" if ed is None else "Upcoming"),
        "_provider_date": ed.strftime("%Y-%m-%d") if stale and ed is not None else "",
        "_sort": ed if ed is not None and not stale else pd.Timestamp.max,
    })

df_earn = pd.DataFrame(rows).sort_values("_sort").drop(columns=["_sort"])

with st.container(border=True):
    st.subheader("Global (Mag 7 + AI Infra + DC Operators)")
    df_g = df_earn[df_earn["Region"] == "US"].drop(columns=["Region", "_provider_date"])
    df_g = df_g[df_g["Status"] == "Upcoming"].drop(columns=["Status"])
    st.dataframe(df_g, use_container_width=True, hide_index=True, height=35 * (len(df_g) + 1) + 3)

with st.container(border=True):
    st.subheader("ANZ")
    df_a = df_earn[df_earn["Region"] == "ANZ"].drop(columns=["Region", "_provider_date"])
    st.dataframe(df_a, use_container_width=True, hide_index=True, height=35 * (len(df_a) + 1) + 3)
    stale_dates = df_earn[(df_earn["Region"] == "ANZ") & (df_earn["_provider_date"] != "")]
    if not stale_dates.empty:
        stale_txt = ", ".join(
            f"{row['Ticker']} last provider date {row['_provider_date']}"
            for _, row in stale_dates.iterrows()
        )
        st.caption(f"Awaiting next announced date from Yahoo/FMP for: {stale_txt}.")

# ══════════════════════════════════════════════
# 2. NEWS FEED — materiality-ranked
# ══════════════════════════════════════════════
st.header("News Feed")
st.caption(
    "Ranked for AI-bubble risk and mitigants: valuations, financing, material contracts, "
    "capex/power, supply-chain constraints, regulation, and industry economics. "
    "Cached 30 min."
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


@st.cache_data(ttl=300, show_spinner=False)
def _load_news_catalog(path: str) -> pd.DataFrame:
    catalog_path = Path(path)
    if not catalog_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(catalog_path)
    if df.empty:
        return df

    for col in ("published", "first_seen_at", "last_seen_at"):
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    df["max_materiality_score"] = pd.to_numeric(
        df.get("max_materiality_score"),
        errors="coerce",
    ).fillna(0.0)
    df["seen_count"] = pd.to_numeric(df.get("seen_count"), errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["published"])
    return df.sort_values("published", ascending=False)


def _history_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=["Published", "Title", "Source", "Bucket", "Score", "Seen", "Link"]
        )

    return pd.DataFrame({
        "Published": df["published"].dt.strftime("%Y-%m-%d"),
        "Title": df["title"].fillna(""),
        "Source": df["source"].fillna(""),
        "Bucket": df["last_bucket"].fillna(""),
        "Score": df["max_materiality_score"],
        "Seen": df["seen_count"],
        "Link": df["url"].fillna(""),
    })


def _render_history_table(label: str, df: pd.DataFrame) -> None:
    if df.empty:
        st.info(f"No {label.lower()} items in the selected range.")
        return

    st.dataframe(
        _history_display_df(df),
        use_container_width=True,
        hide_index=True,
        height=min(540, 38 * (len(df) + 1) + 3),
        column_config={
            "Published": st.column_config.TextColumn("Published", width="small"),
            "Title": st.column_config.TextColumn("Title", width="large"),
            "Source": st.column_config.TextColumn("Source", width="medium"),
            "Bucket": st.column_config.TextColumn("Bucket", width="medium"),
            "Score": st.column_config.NumberColumn("Score", format="%.3f", width="small"),
            "Seen": st.column_config.NumberColumn("Seen", format="%d", width="small"),
            "Link": st.column_config.LinkColumn("Link", display_text="Open", width="small"),
        },
    )


col_refresh, col_filter, _ = st.columns([1, 1.8, 3.2])
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
    all_items = flatten_news_buckets(news_data)

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

    with st.container(border=True, height=680):
        st.markdown("\n".join(p for p in html_parts if p), unsafe_allow_html=True)


# ══════════════════════════════════════════════
# 3. NEWS HISTORY — durable catalog
# ══════════════════════════════════════════════
st.header("News History")
catalog_df = _load_news_catalog(str(NEWS_CATALOG_PATH))

if catalog_df.empty:
    st.warning("No catalogued news history found.")
else:
    min_published = catalog_df["published"].min().date()
    max_published = catalog_df["published"].max().date()
    default_start = max(min_published, max_published - timedelta(days=60))

    hist_col_1, hist_col_2, hist_col_3 = st.columns([1.25, 2.25, 2.5])
    with hist_col_1:
        selected_range = st.date_input(
            "Published range",
            value=(default_start, max_published),
            min_value=min_published,
            max_value=max_published,
        )
    with hist_col_2:
        bucket_options = sorted(catalog_df["last_bucket"].dropna().unique().tolist())
        selected_buckets = st.multiselect("Buckets", bucket_options, default=bucket_options)
    with hist_col_3:
        query = st.text_input("Search", placeholder="Company, source, contract, power...")

    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
    elif isinstance(selected_range, date):
        start_date, end_date = selected_range, selected_range
    else:
        start_date, end_date = default_start, max_published

    history = catalog_df.copy()
    history_date = history["published"].dt.date
    history = history[(history_date >= start_date) & (history_date <= end_date)]

    if selected_buckets:
        history = history[history["last_bucket"].isin(selected_buckets)]

    query = query.strip().lower()
    if query:
        searchable = (
            history["title"].fillna("")
            + " "
            + history["source"].fillna("")
            + " "
            + history["summary"].fillna("")
            + " "
            + history["last_bucket"].fillna("")
        ).str.lower()
        history = history[searchable.str.contains(query, regex=False, na=False)]

    high_history = history[history["last_tier"] == "HIGH"].sort_values("published", ascending=False)
    medium_history = history[history["last_tier"] == "MEDIUM"].sort_values("published", ascending=False)

    hist_m1, hist_m2, hist_m3 = st.columns(3)
    hist_m1.metric("Catalogued", len(history))
    hist_m2.metric("High", len(high_history))
    hist_m3.metric("Medium", len(medium_history))

    high_tab, medium_tab = st.tabs(["High", "Medium"])
    with high_tab:
        _render_history_table("High", high_history)
    with medium_tab:
        _render_history_table("Medium", medium_history)
