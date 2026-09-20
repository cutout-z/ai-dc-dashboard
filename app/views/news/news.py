"""News — earnings calendars and curated AI/DC news feed.

S2-13 page-critical-path ordering: committed content renders FIRST — the
earnings snapshot (``data/reference/earnings_dates.csv``, no network) and the
durable news catalogue — and the live feed fetch runs LAST, bounded-concurrent
in :mod:`app.lib.news`. A stalled or failed feed therefore can never hide the
stored history, and partial feed failures stay visible next to the live items.
Live Yahoo earnings dates are an explicit opt-in toggle.

ONE feed, not two (2026-09-20): the durable catalogue and the live fetch are a
single "News Feed" section. The catalogue rows render into a placeholder
before the fetch runs — so the S2-13 guarantee still holds, committed rows are
on screen with no network — and the fetched items are merged into that same
table by :func:`app.lib.news.merge_catalog_and_live_feed` once the fetch
resolves. The filters that used to head the separate history section
(published range, buckets, search) sit above the one table, and the range
defaults to All so the whole catalogue is visible by default.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from app.lib.equities import (
    ANZ_EARNINGS_TICKERS,
    MAG7_AI_STOCKS,
    committed_earnings_newest_date,
    fetch_committed_earnings_dates,
    fetch_earnings_dates,
)
from app.lib.news import (
    BUCKETS,
    fetch_news_buckets_with_stats,
    fetch_stats_summary,
    flatten_news_buckets,
    merge_catalog_and_live_feed,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NEWS_CATALOG_PATH = PROJECT_ROOT / "data" / "reference" / "news_catalog.csv"

# Tier gate: "Show low-materiality" decides whether LOW rows reach the table.
# Everything else in the filter bar (range, buckets, search) applies to
# catalogue and live rows identically.
_ALWAYS_SHOWN_TIERS = ("HIGH", "MEDIUM")
_LOW_TIER = "LOW"

# Published-range presets — "All" is the default so nothing is windowed out of
# the durable event store; the catalogue's full span is the natural first load.
_RANGE_PRESETS: dict[str, int | None] = {
    "All": None,
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 90 days": 90,
    "Custom": -1,
}

st.title("News")
st.caption("Earnings calendars for key players + one curated AI/DC news feed.")


# ══════════════════════════════════════════════
# Helpers (no UI output)
# ══════════════════════════════════════════════

def _parse_date(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:
        return None


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


def _bucket_options(catalog_df: pd.DataFrame) -> list[str]:
    """Every bucket the live feed can produce, plus any bucket only the catalogue holds.

    Derived from the feed config (never the catalogue alone) so an empty or
    partial catalogue can never leave the filter with no options.
    """
    catalogued = set(catalog_df["last_bucket"].dropna()) if "last_bucket" in catalog_df.columns else set()
    return sorted(set(BUCKETS.keys()) | catalogued)


def _published_bounds(catalog_only: pd.DataFrame) -> tuple[date, date]:
    """Full span of the merged frame — the 'All' range and the Custom picker bounds."""
    today = pd.Timestamp.now().normalize().date()
    published = catalog_only["published"].dropna() if not catalog_only.empty else pd.Series(dtype="datetime64[ns, UTC]")
    dates = [d.date() for d in published]
    if not dates:
        return today - timedelta(days=90), today
    # Upper bound reaches one day past today so a live item stamped ahead of the
    # local clock is never windowed out by the Custom picker.
    return min(dates), max([today, *dates])


def _filter_feed(
    frame: pd.DataFrame,
    *,
    start: date | None,
    end: date | None,
    buckets: list[str],
    query: str,
) -> pd.DataFrame:
    """Apply the filter bar to the merged frame (the tier gate happens at render)."""
    if frame.empty:
        return frame

    out = frame
    if start is not None:
        out = out[out["published"] >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        # Inclusive end date.
        out = out[out["published"] < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]

    if buckets:
        out = out[out["bucket"].isin(buckets)]

    query = query.strip().lower()
    if query:
        searchable = (
            out["title"].fillna("")
            + " "
            + out["source"].fillna("")
            + " "
            + out["summary"].fillna("")
            + " "
            + out["bucket"].fillna("")
        ).str.lower()
        out = out[searchable.str.contains(query, regex=False, na=False)]

    return out


def _display_frame(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Published": df["published"].dt.strftime("%Y-%m-%d").fillna("—"),
        "Title": df["title"].fillna(""),
        "Source": df["source"].fillna(""),
        "Bucket": df["bucket"].fillna(""),
        "Tier": df["tier"].fillna(""),
        "Score": df["score"],
        "Seen": df["seen"],
        "Status": df["status"],
        "Link": df["url"].fillna(""),
    })


def _render_feed(slot, frame: pd.DataFrame, *, include_low: bool, catalog_n: int) -> None:
    """Render metrics + the one merged table into ``slot``.

    Called twice per run: once with the catalogue alone (before the live fetch,
    so committed rows are on screen with no network) and once with live items
    merged in. The second call replaces the first inside the same placeholder —
    the page keeps ONE feed, and a stalled fetch leaves the catalogue standing.
    """
    tiers = set(_ALWAYS_SHOWN_TIERS) | ({_LOW_TIER} if include_low else set())
    shown = frame[frame["tier"].isin(tiers)]
    low_hidden = int((~frame["tier"].isin(tiers)).sum())
    live_n = int((frame["status"] == "Live").sum()) if not frame.empty else 0

    with slot.container():
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total", len(frame))
        col_m2.metric("High", int((frame["tier"] == "HIGH").sum()))
        col_m3.metric("Medium", int((frame["tier"] == "MEDIUM").sum()))
        col_m4.metric("Low", int((frame["tier"] == _LOW_TIER).sum()))

        caption = (
            f"{catalog_n} catalogued rows + {live_n} live-fetch rows not in the catalogue "
            f"= {len(frame)} in range; showing {len(shown)}."
        )
        if low_hidden:
            caption += (
                f" {low_hidden} low-materiality row(s) hidden — enable "
                "\"Show low-materiality\" above to include them."
            )
        st.caption(caption)

        if shown.empty:
            st.info("No news items match the current filters.")
            return

        st.dataframe(
            _display_frame(shown),
            use_container_width=True,
            hide_index=True,
            height=min(760, 38 * (len(shown) + 1) + 3),
            column_config={
                "Published": st.column_config.TextColumn("Published", width="small"),
                "Title": st.column_config.TextColumn("Title", width="large"),
                "Source": st.column_config.TextColumn("Source", width="medium"),
                "Bucket": st.column_config.TextColumn("Bucket", width="medium"),
                "Tier": st.column_config.TextColumn("Tier", width="small"),
                "Score": st.column_config.NumberColumn("Score", format="%.3f", width="small"),
                "Seen": st.column_config.NumberColumn(
                    "Seen", format="%d", width="small",
                    help=(
                        "Times the catalogue lane observed this article. "
                        "Blank = live-fetch row that is not in the catalogue."
                    ),
                ),
                "Status": st.column_config.TextColumn(
                    "Status", width="small",
                    help=(
                        "Catalogued = durable committed catalogue row. Live = fetched now and "
                        "not in the catalogue — the lane stores HIGH/MEDIUM only, so "
                        "low-materiality rows stay uncatalogued by design."
                    ),
                ),
                "Link": st.column_config.LinkColumn("Link", display_text="Open", width="small"),
            },
        )


# ══════════════════════════════════════════════
# 1. EARNINGS CALENDAR — committed snapshot first (live opt-in)
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

live_earnings = st.toggle(
    "Check Yahoo for latest earnings dates",
    value=False,
    key="news_live_earnings",
    help=(
        "Off by default (S2-13): the calendar renders the committed "
        "data/reference/earnings_dates.csv snapshot instantly, with no network. "
        "Enable to run live Yahoo lookups instead (results cached 60 min)."
    ),
)

today = pd.Timestamp.now().normalize()
if live_earnings:
    with st.spinner("Fetching earnings dates from Yahoo..."):
        dates = fetch_earnings_dates(tuple(t["symbol"] for t in all_tickers))
    st.caption(
        "Dates from live Yahoo, falling back to the committed snapshot where Yahoo "
        "returns nothing or a past date (cached 60 min)."
    )
else:
    dates = fetch_committed_earnings_dates()
    newest = committed_earnings_newest_date(dates)
    asof = f"newest listed date {newest}" if newest else "no listed dates"
    hint = ""
    if newest is not None and newest < today.strftime("%Y-%m-%d"):
        hint = " This snapshot predates today — enable the live Yahoo check above for upcoming dates."
    st.caption(
        f"Committed snapshot data/reference/earnings_dates.csv ({asof}) — rendered "
        f"with no network; live Yahoo is an explicit opt-in above.{hint}"
    )


def _earnings_rows(dates: dict) -> list[dict]:
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
    return rows


df_earn = pd.DataFrame(_earnings_rows(dates)).sort_values("_sort").drop(columns=["_sort"])

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
            f"{row['Ticker']} last listed date {row['_provider_date']}"
            for _, row in stale_dates.iterrows()
        )
        st.caption(f"Awaiting next announced date for: {stale_txt}.")


# ══════════════════════════════════════════════
# 2. NEWS FEED — durable catalogue ∪ live fetch, ONE section
# ══════════════════════════════════════════════
st.header("News Feed")
st.caption(
    "Ranked for AI-bubble risk and mitigants: valuations, financing, material contracts, "
    "capex/power, supply-chain constraints, regulation, and industry economics. "
    "One table: the durable catalogue (scripts/catalog_news.py, committed) plus the live "
    "fetch merged in — catalogue rows render first, live rows join them when the fetch "
    "resolves (cached 30 min). The catalogue lane stores HIGH/MEDIUM, so low-materiality "
    "live rows are never catalogued (hence a blank \"Seen\")."
)

catalog_df = _load_news_catalog(str(NEWS_CATALOG_PATH))
# Catalogue-only frame: the first-pass render, built exactly as the merge builds it.
catalog_only = merge_catalog_and_live_feed(catalog_df, [])
catalog_n = len(catalog_only)
span_lo, span_hi = _published_bounds(catalog_only)

col_range, col_buckets, col_search = st.columns([1.2, 2.3, 2.5])
with col_range:
    range_label = st.selectbox(
        "Published range",
        list(_RANGE_PRESETS),
        index=0,
        key="news_range",
        help=(
            f"Defaults to All — the whole catalogue plus live items, no windowing. "
            f"The catalogue currently spans {span_lo} → {span_hi}."
        ),
    )
with col_buckets:
    bucket_options = _bucket_options(catalog_df)
    selected_buckets = st.multiselect(
        "Buckets", bucket_options, default=bucket_options, key="news_buckets"
    )
with col_search:
    query = st.text_input(
        "Search", placeholder="Company, source, contract, power...", key="news_query"
    )

col_refresh, col_low, _col_pad = st.columns([1, 1.7, 3.3])
with col_refresh:
    if st.button("Refresh", use_container_width=True):
        fetch_news_buckets_with_stats.clear()
with col_low:
    show_low = st.toggle("Show low-materiality", value=False, key="news_show_low")

start_date: date | None
end_date: date | None
preset_days = _RANGE_PRESETS[range_label]
if preset_days == -1:
    lo, hi = span_lo, span_hi
    picked = st.date_input(
        "Custom published range",
        value=(lo, hi),
        min_value=lo,
        max_value=hi,
        key="news_range_custom",
    )
    if isinstance(picked, tuple) and len(picked) == 2:
        start_date, end_date = picked
    elif isinstance(picked, date):
        start_date, end_date = picked, picked
    else:
        start_date, end_date = lo, hi
elif preset_days:
    start_date = pd.Timestamp.now().normalize().date() - timedelta(days=preset_days)
    end_date = None
else:
    start_date, end_date = None, None

filtered_catalog = _filter_feed(
    catalog_only,
    start=start_date,
    end=end_date,
    buckets=selected_buckets,
    query=query,
)

# Committed content first: the catalogue renders into the placeholder — and is
# on screen — before the live fetch runs, so a stalled feed can never hide it
# (S2-13). The merged render below replaces it in the same slot.
feed_slot = st.empty()
_render_feed(feed_slot, filtered_catalog, include_low=show_low, catalog_n=catalog_n)

with st.spinner("Fetching live news..."):
    news_data, feed_stats = fetch_news_buckets_with_stats()

live_items = flatten_news_buckets(news_data) if any(news_data.values()) else []
merged = merge_catalog_and_live_feed(catalog_df, live_items)
filtered_merged = _filter_feed(
    merged,
    start=start_date,
    end=end_date,
    buckets=selected_buckets,
    query=query,
)

# Second pass replaces the first in the same placeholder — one feed on screen.
_render_feed(feed_slot, filtered_merged, include_low=show_low, catalog_n=catalog_n)

st.caption(f"Live fetch — {fetch_stats_summary(feed_stats)}")


def _feed_status_line(stats: dict) -> str:
    attempted = stats.get("attempted", 0)
    succeeded = stats.get("succeeded", 0)
    if not attempted:
        return "no feed requests were made"
    if succeeded == attempted:
        return f"all {attempted} feed requests succeeded"
    return f"{succeeded}/{attempted} feed requests succeeded"


if not live_items:
    st.warning(
        f"No live news items fetched — {_feed_status_line(feed_stats)} "
        f"({fetch_stats_summary(feed_stats)}). "
        "The catalogued rows above remain available and unaffected."
    )
elif feed_stats.get("succeeded", 0) < feed_stats.get("attempted", 0):
    st.warning(
        f"Partial live-fetch failure — {_feed_status_line(feed_stats)} "
        f"({fetch_stats_summary(feed_stats)}). Catalogued rows above are unaffected."
    )
