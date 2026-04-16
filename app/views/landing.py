"""Landing page — dashboard overview."""

import streamlit as st

st.title("AI & DC Dashboard")
st.caption("Supply chain intelligence, investment prospecting")
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
