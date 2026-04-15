"""Landing page — dashboard overview, bubble risk gauges, and KPIs."""

import sqlite3
import streamlit as st

from app.lib.bubble_gauges import (
    DIRECTION_ARROWS,
    ZONE_COLORS,
    all_gauges,
    overall_assessment,
)

DB_PATH = st.session_state["db_path"]

st.title("AI & DC Dashboard")
st.caption("Bubble risk indicators, supply chain intelligence, investment prospecting")

# ══════════════════════════════════════════════
# BUBBLE RISK GAUGES (boomorbubble.ai framework)
# ══════════════════════════════════════════════

with st.spinner("Computing bubble risk gauges..."):
    gauges = all_gauges(DB_PATH)
assessment = overall_assessment(gauges)

# Overall verdict
st.markdown(
    f'<div style="text-align:center; padding:0.5rem 0 0.25rem 0;">'
    f'<span style="font-size:1.6rem; font-weight:700; color:{assessment["color"]}">'
    f'{assessment["label"]}</span>'
    f'<span style="font-size:0.9rem; color:#9ca3af; margin-left:0.75rem;">'
    f'{assessment["detail"]}</span></div>',
    unsafe_allow_html=True,
)
st.caption(
    "Framework: 0–1 red = Boom · 2 red = Caution · 3+ red = Bubble | "
    "Inspired by [boomorbubble.ai](https://boomorbubble.ai/) (Azeem Azhar, Exponential View)"
)

# 5 gauge cards
cols = st.columns(5)
for col, g in zip(cols, gauges):
    zone_color = ZONE_COLORS.get(g["zone"], "#6b7280")
    arrow = DIRECTION_ARROWS.get(g["direction"], "→")
    with col:
        st.markdown(
            f'<div style="border:2px solid {zone_color}; border-radius:8px; '
            f'padding:0.6rem; text-align:center; min-height:120px;">'
            f'<div style="font-size:0.75rem; color:#9ca3af; margin-bottom:0.3rem;">'
            f'{g["name"]}</div>'
            f'<div style="font-size:1.5rem; font-weight:700; color:{zone_color};">'
            f'{g["value_fmt"]}</div>'
            f'<div style="font-size:0.8rem; color:{zone_color};">'
            f'{g["zone"].upper()} {arrow}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# Gauge details expander
with st.expander("Gauge methodology & detail"):
    for g in gauges:
        zone_color = ZONE_COLORS.get(g["zone"], "#6b7280")
        arrow = DIRECTION_ARROWS.get(g["direction"], "→")
        st.markdown(
            f'**{g["name"]}** — '
            f'<span style="color:{zone_color}; font-weight:600;">'
            f'{g["value_fmt"]} {g["zone"].upper()} {arrow}</span>',
            unsafe_allow_html=True,
        )
        st.caption(f'{g["detail"]}  \nBenchmark: {g["benchmark"]}')

# Research pass staleness indicator
def _last_research_run(db_path: str):
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT run_date FROM research_log ORDER BY run_date DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


from datetime import datetime as _dt

_last_run = _last_research_run(DB_PATH)
if _last_run:
    _days = (_dt.now() - _dt.fromisoformat(_last_run)).days
    _badge_color = "#22c55e" if _days < 7 else ("#f59e0b" if _days < 14 else "#ef4444")
    _run_label = f"{_days}d ago ({_dt.fromisoformat(_last_run).strftime('%d %b %Y')})"
else:
    _days = 999
    _badge_color = "#ef4444"
    _run_label = "never"

st.markdown(
    f'<div style="text-align:right; font-size:0.75rem; color:#9ca3af; margin-top:-0.5rem;">'
    f'Last research pass: <span style="color:{_badge_color}; font-weight:600;">{_run_label}</span>'
    + (" · Run <code>/ai-research</code> to update" if _days >= 7 else "")
    + "</div>",
    unsafe_allow_html=True,
)

st.markdown("---")

# ══════════════════════════════════════════════
# EXISTING KPIs
# ══════════════════════════════════════════════

conn = sqlite3.connect(DB_PATH)

col1, col2, col3, col4 = st.columns(4)

mapping_count = conn.execute("SELECT COUNT(*) FROM mapping").fetchone()[0]
alpha_count = conn.execute("SELECT COUNT(*) FROM mapping WHERE alpha_flag = 1").fetchone()[0]
vc_count = conn.execute("SELECT COUNT(*) FROM value_chain_universe WHERE included = 1").fetchone()[0]

latest_capex = conn.execute(
    """
    SELECT SUM(capex_usd) / 1e9
    FROM v_hyperscaler_capex
    WHERE period = (SELECT MAX(period) FROM v_hyperscaler_capex)
    """
).fetchone()[0]

col1.metric("Mapping Universe", f"{mapping_count:,}")
col2.metric("Alpha Cohort", f"{alpha_count}")
col3.metric("Value Chain Stocks", f"{vc_count}")
col4.metric("Hyperscaler CAPEX (Q)", f"${latest_capex:.0f}B" if latest_capex else "N/A")

conn.close()

st.markdown("---")
st.markdown(
    """
### Sections

**Fundamentals Tracking**
- **Model Performance** — AI model benchmarks, context windows, capability milestones
- **Equity Analysis (key players)** — Mag 7, AI Infra, DC Operators — prices, fundamentals, P/E, treemap
- **Hyperscaler CAPEX** — Annual + quarterly CAPEX with forward guidance overlay
- **Other Signals** — Semi demand, frontier lab valuations, GPU leases, LLM capability, DC power
- **Power** — DC power demand forecasts, grid capacity, interconnection queue

**Supply Chain**
- **AI Infra Value Chain** — Taxonomy + per-segment stock tiles
- **DC & AI Inputs** — Key commodity inputs (energy, metals, semis, power)
- **Prospecting** — Screen 3,594-stock mapping universe by AI exposure, materiality, pricing power

**News**
- **News** — Earnings calendars (key players + ANZ) and curated AI/DC news feed

**System**
- **Source Health** — Freshness audit across all data sources
"""
)
