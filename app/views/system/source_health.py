"""Source Health — freshness audit across all data sources.

Tracks:
- Reference CSV files (mtime, row count, latest date column)
- SQLite tables and views (row count, latest period where applicable)
- Live fetchers (configured TTL — shows cache staleness intent)
- News buckets (item counts + latest article per bucket)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from app.lib.news import fetch_news_source_health

DB_PATH = Path(st.session_state["db_path"])
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "reference"

st.title("Source Health")
st.caption("Freshness audit across CSVs, DB tables, live fetchers, and news feeds.")


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    return (datetime.now().timestamp() - path.stat().st_mtime)


def _fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h"
    days = hours / 24
    if days < 365:
        return f"{int(days)}d"
    return f"{int(days / 365)}y"


def _classify(age_seconds: float | None, fresh_max: float, stale_max: float) -> str:
    """fresh / stale / very-stale / no-data based on age thresholds (seconds)."""
    if age_seconds is None:
        return "no-data"
    if age_seconds < fresh_max:
        return "fresh"
    if age_seconds < stale_max:
        return "stale"
    return "very-stale"


STATUS_ORDER = {"error": 0, "no-data": 1, "very-stale": 2, "stale": 3, "fresh": 4}
STATUS_ICONS = {
    "fresh": "OK",
    "stale": "STALE",
    "very-stale": "OLD",
    "no-data": "--",
    "error": "ERR",
}


def _status_cell(status: str) -> str:
    return f"{STATUS_ICONS.get(status, '')} {status}"


# ──────────────────────────────────────────────
# 1. REFERENCE CSVs
# ──────────────────────────────────────────────
st.header("Reference CSVs")
st.caption("Thresholds: fresh < 30d, stale < 90d, very-stale ≥ 90d")

# Per-file freshness thresholds (in days). Some data is inherently slow-moving.
CSV_FRESH_DAYS = {
    "capex_guidance.csv": 30,         # earnings-season cadence
    "tsmc_monthly_revenue.csv": 15,   # monthly
    "token_consumption.csv": 60,
    "frontier_lab_valuations.csv": 60,
    "gpu_lease_prices.csv": 60,
    "model_releases.csv": 30,
    "dc_power_forecasts.csv": 180,    # annual reports
}

# Date columns to scan for "latest observed" per file
CSV_DATE_COLS = {
    "capex_guidance.csv": "guidance_date",
    "tsmc_monthly_revenue.csv": None,  # composed from year+month
    "token_consumption.csv": "date",
    "frontier_lab_valuations.csv": "date",
    "gpu_lease_prices.csv": "date",
    "model_releases.csv": "release_date",
    "dc_power_forecasts.csv": None,    # contains years, not a date col
}

csv_rows = []
for csv_path in sorted(DATA_DIR.glob("*.csv")):
    name = csv_path.name
    age_s = _age_seconds(csv_path)
    fresh_days = CSV_FRESH_DAYS.get(name, 30)
    status = _classify(age_s, fresh_days * 86400, fresh_days * 3 * 86400)

    row_count = None
    latest = None
    try:
        df = pd.read_csv(csv_path)
        row_count = len(df)
        date_col = CSV_DATE_COLS.get(name)
        if date_col and date_col in df.columns:
            latest_val = pd.to_datetime(df[date_col], errors="coerce").max()
            if pd.notna(latest_val):
                latest = latest_val.strftime("%Y-%m-%d")
        elif name == "tsmc_monthly_revenue.csv" and {"year", "month"}.issubset(df.columns):
            latest = f"{int(df['year'].max())}-{int(df[df['year']==df['year'].max()]['month'].max()):02d}"
    except Exception as e:
        status = "error"
        latest = f"parse error: {e}"

    csv_rows.append({
        "Source": name,
        "Status": _status_cell(status),
        "File Age": _fmt_age(age_s),
        "Rows": row_count,
        "Latest Entry": latest or "—",
        "_status": status,
        "_age": age_s or 0,
    })

csv_rows.sort(key=lambda r: (STATUS_ORDER.get(r["_status"], 5), -r["_age"]))
df_csv = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in csv_rows])
st.dataframe(df_csv, use_container_width=True, hide_index=True, height=35 * (len(df_csv) + 1) + 3)


# ──────────────────────────────────────────────
# 2. SQLITE TABLES / VIEWS
# ──────────────────────────────────────────────
st.header("SQLite Tables & Views")

db_age = _age_seconds(DB_PATH)
st.caption(f"Database: `{DB_PATH.name}` · file age {_fmt_age(db_age)}")

TABLE_SPECS = [
    # (name, period_col or None, fresh_days, is_view)
    ("mapping", None, None, False),
    ("value_chain_universe", None, None, False),
    ("value_chain_taxonomy", None, None, False),
    ("quarterly_financials", "period", 90, False),
    ("llm_arena_elo", None, 30, False),
    ("llm_model_specs", None, 30, False),
    ("v_hyperscaler_capex", "period", 120, True),
    ("v_semi_revenue", "period", 120, True),
    ("v_full_universe", None, None, True),
]

db_rows = []
conn = sqlite3.connect(DB_PATH)
for name, period_col, fresh_days, is_view in TABLE_SPECS:
    status = "fresh"  # default for static reference tables
    row_count = None
    latest = None
    try:
        row_count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        if period_col:
            latest_raw = conn.execute(f"SELECT MAX({period_col}) FROM {name}").fetchone()[0]
            if latest_raw:
                latest = str(latest_raw)
                # Classify against period freshness
                try:
                    latest_dt = pd.to_datetime(latest_raw)
                    age_from_latest = (datetime.now() - latest_dt.to_pydatetime()).total_seconds()
                    if fresh_days:
                        status = _classify(age_from_latest, fresh_days * 86400, fresh_days * 2 * 86400)
                except Exception:
                    pass
        elif fresh_days:
            # Use db file mtime as proxy
            status = _classify(db_age, fresh_days * 86400, fresh_days * 2 * 86400)
    except Exception as e:
        status = "error"
        latest = f"error: {e}"

    db_rows.append({
        "Source": f"{'view:' if is_view else 'table:'} {name}",
        "Status": _status_cell(status),
        "Rows": row_count,
        "Latest Period": latest or "—",
        "_status": status,
    })
conn.close()

db_rows.sort(key=lambda r: STATUS_ORDER.get(r["_status"], 5))
df_db = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in db_rows])
st.dataframe(df_db, use_container_width=True, hide_index=True, height=35 * (len(df_db) + 1) + 3)


# ──────────────────────────────────────────────
# 3. LIVE FETCHERS (cache TTLs)
# ──────────────────────────────────────────────
st.header("Live Fetchers")
st.caption(
    "Streamlit caches these functions with the configured TTL. Source Health reports "
    "the TTL contract — actual freshness depends on when each page was last viewed."
)

live_rows = [
    {"Source": "fetch_equities_data() — yfinance + Yahoo spark", "TTL": "5m"},
    {"Source": "fetch_commodity_overview() — Yahoo spark", "TTL": "5m"},
    {"Source": "fetch_earnings_dates() — yfinance", "TTL": "1h"},
    {"Source": "fetch_news_buckets() — feedparser (Google News + direct)", "TTL": "30m"},
]
st.dataframe(pd.DataFrame(live_rows), use_container_width=True, hide_index=True,
             height=35 * (len(live_rows) + 1) + 3)


# ──────────────────────────────────────────────
# 4. NEWS BUCKETS
# ──────────────────────────────────────────────
st.header("News Buckets")
st.caption("Item counts and latest article per bucket (from cached fetch).")

try:
    news_rows = fetch_news_source_health()
    for r in news_rows:
        if r["item_count"] == 0:
            r["_status"] = "no-data"
        else:
            r["_status"] = "fresh"
        r["Status"] = _status_cell(r["_status"])
        r["Bucket"] = r.pop("bucket")
        r["Items"] = r.pop("item_count")
        r["Latest"] = r.pop("latest") or "—"

    df_news = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in news_rows])
    df_news = df_news[["Bucket", "Status", "Items", "Latest"]]
    st.dataframe(df_news, use_container_width=True, hide_index=True,
                 height=35 * (len(df_news) + 1) + 3)
except Exception as e:
    st.error(f"Failed to query news sources: {e}")
