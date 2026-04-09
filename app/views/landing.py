"""Landing page — dashboard overview and KPIs."""

import sqlite3
import streamlit as st

DB_PATH = st.session_state["db_path"]

st.title("AI & DC Dashboard")
st.caption("Bubble risk indicators, supply chain intelligence, investment prospecting")

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
