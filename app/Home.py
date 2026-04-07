"""
AI Research Dashboard
Two modes: Work (bubble risk, stakeholder-ready) / Personal (investment prospecting)
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="AI Research",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"

st.sidebar.title("AI Research")
mode = st.sidebar.radio("Mode", ["Work", "Personal"], index=0)
st.session_state["mode"] = mode
st.session_state["db_path"] = str(DB_PATH)

if mode == "Work":
    st.title("AI / Data Centre Research")
    st.caption("Bubble risk indicators, supply chain intelligence, capability tracking")
else:
    st.title("AI Investment Prospecting")
    st.caption("Screening, thesis development, opportunity identification")

# Quick stats
import sqlite3

conn = sqlite3.connect(DB_PATH)

col1, col2, col3, col4 = st.columns(4)

# Mapping universe size
mapping_count = conn.execute("SELECT COUNT(*) FROM mapping").fetchone()[0]
alpha_count = conn.execute("SELECT COUNT(*) FROM mapping WHERE alpha_flag = 1").fetchone()[0]
vc_count = conn.execute("SELECT COUNT(*) FROM value_chain_universe WHERE included = 1").fetchone()[0]

# Latest CAPEX
latest_capex = conn.execute("""
    SELECT SUM(capex_usd) / 1e9
    FROM v_hyperscaler_capex
    WHERE period = (SELECT MAX(period) FROM v_hyperscaler_capex)
""").fetchone()[0]

col1.metric("Mapping Universe", f"{mapping_count:,}")
col2.metric("Alpha Cohort", f"{alpha_count}")
col3.metric("Value Chain Stocks", f"{vc_count}")
col4.metric("Hyperscaler CAPEX (Q)", f"${latest_capex:.0f}B" if latest_capex else "N/A")

conn.close()

st.markdown("---")
st.markdown("""
### Pages
- **Bubble Tracker** — Hyperscaler CAPEX trends, LLM capability curves, key risk indicators
- **Supply Chain** — AI infrastructure value chain taxonomy with analyst positioning
- **Prospecting** — Screen 3,594 stocks by AI exposure, materiality, pricing power, wave evolution
""")
