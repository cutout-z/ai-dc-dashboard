"""DC / AI Input Commodities — key input costs for data centre buildout."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="DC Commodities", layout="wide")

st.title("DC / AI Input Costs")

from app.lib.commodities import fetch_commodity_overview, DC_COMMODITIES, KEY_METRICS

with st.spinner("Fetching commodity data..."):
    data = fetch_commodity_overview()

if not data:
    st.warning("No commodity data available. Check network connection.")
    st.stop()

# ──────────────────────────────────────────────
# 1. KEY METRICS ROW
# ──────────────────────────────────────────────
# Find key metrics from the data
key_items = {}
for cat_data in data.values():
    for item in cat_data:
        if item["symbol"] in KEY_METRICS:
            key_items[item["symbol"]] = item

cols = st.columns(len(KEY_METRICS))
for i, sym in enumerate(KEY_METRICS):
    item = key_items.get(sym)
    if item:
        price_str = f"${item['price']:,.2f}" if item["price"] else "N/A"
        delta = f"{item['change_pct']:+.2f}%" if item["change_pct"] is not None else None
        cols[i].metric(
            label=item["name"],
            value=price_str,
            delta=delta,
            delta_color="normal",
        )

st.markdown("---")

# ──────────────────────────────────────────────
# 2. GROUPED PRICE TABLES (Tabs)
# ──────────────────────────────────────────────
tabs = st.tabs(list(data.keys()))

return_periods = ["1D", "1M", "3M", "6M", "1Y"]


def _color_val(val):
    if val is None or pd.isna(val):
        return "color: gray"
    return "color: #22c55e" if val >= 0 else "color: #ef4444"


def _fmt_pct(val):
    if val is None or pd.isna(val):
        return "-"
    return f"{val:+.2f}%"


def _fmt_price(val):
    if val is None or pd.isna(val):
        return "-"
    if val < 10:
        return f"${val:,.3f}"
    return f"${val:,.2f}"


for tab, (category, items) in zip(tabs, data.items()):
    with tab:
        rows = []
        for item in items:
            ret = item.get("returns", {})
            rows.append({
                "Name": item["name"],
                "Symbol": item["symbol"],
                "Price": item["price"],
                "Daily %": item.get("change_pct"),
                "1M %": ret.get("1M"),
                "3M %": ret.get("3M"),
                "6M %": ret.get("6M"),
                "1Y %": ret.get("1Y"),
                "DC/AI Relevance": item["relevance"],
            })

        df = pd.DataFrame(rows)
        pct_cols = ["Daily %", "1M %", "3M %", "6M %", "1Y %"]

        styled = (
            df.style
            .format({col: _fmt_pct for col in pct_cols})
            .format({"Price": _fmt_price})
            .map(_color_val, subset=pct_cols)
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────
# 3. HISTORICAL PRICE CHART
# ──────────────────────────────────────────────
st.header("Historical Prices")

# Build flat list of all commodities for selector
all_items = []
for cat_data in data.values():
    all_items.extend(cat_data)

col_sel, col_range = st.columns([3, 1])
with col_sel:
    options = {f"{item['name']} ({item['symbol']})": item for item in all_items}
    selected = st.selectbox("Commodity", list(options.keys()))

with col_range:
    time_range = st.radio("Range", ["1Y", "5Y"], horizontal=True)

if selected:
    item = options[selected]
    closes = item.get("closes", [])
    timestamps = item.get("timestamps", [])

    if closes and timestamps:
        # Filter by selected time range
        trading_days = 252 if time_range == "1Y" else 1260
        if len(closes) > trading_days:
            closes = closes[-trading_days:]
            timestamps = timestamps[-trading_days:]

        dates = [datetime.fromtimestamp(ts) for ts in timestamps]

        fig_hist = go.Figure()
        fig_hist.add_trace(go.Scatter(
            x=dates,
            y=closes,
            mode="lines",
            line=dict(color="#3b82f6", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(59, 130, 246, 0.1)",
        ))
        fig_hist.update_layout(
            height=400,
            xaxis_title="Date",
            yaxis_title="Price ($)",
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_hist, use_container_width=True)
        st.caption(f"**DC/AI relevance**: {item['relevance']}")
    else:
        st.info("No historical data available for this commodity.")

# ──────────────────────────────────────────────
# 4. PERFORMANCE HEATMAP
# ──────────────────────────────────────────────
st.header("Performance Heatmap")

heatmap_rows = []
heatmap_labels = []
for category, items in data.items():
    for item in items:
        ret = item.get("returns", {})
        heatmap_rows.append([
            ret.get("1M"),
            ret.get("3M"),
            ret.get("6M"),
            ret.get("1Y"),
        ])
        heatmap_labels.append(item["name"])

if heatmap_rows:
    fig_heat = go.Figure(data=go.Heatmap(
        z=heatmap_rows,
        x=["1M", "3M", "6M", "1Y"],
        y=heatmap_labels,
        colorscale="RdYlGn",
        zmid=0,
        text=[[f"{v:+.1f}%" if v is not None else "-" for v in row] for row in heatmap_rows],
        texttemplate="%{text}",
        textfont={"size": 11},
        hovertemplate="<b>%{y}</b><br>%{x}: %{text}<extra></extra>",
        colorbar=dict(title="Return %"),
    ))
    fig_heat.update_layout(
        height=max(350, len(heatmap_labels) * 35),
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)
