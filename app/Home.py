"""AI & DC Dashboard — navigation entry point."""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="AI & DC Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"
st.session_state["db_path"] = str(DB_PATH)

st.sidebar.title("AI & DC Dashboard")

# Define pages
landing = st.Page("views/landing.py", title="Home", default=True)

# Fundamentals Tracking
model_performance = st.Page(
    "views/fundamentals/model_performance.py", title="LLM Analysis"
)
equity_analysis = st.Page(
    "views/fundamentals/equity_analysis.py", title="Equity Analysis (key players)"
)
financials = st.Page(
    "views/fundamentals/financials.py", title="Financial (key players)"
)
hyperscaler_capex = st.Page(
    "views/fundamentals/hyperscaler_capex.py", title="Hyperscaler CAPEX"
)
other_signals = st.Page(
    "views/fundamentals/other_signals.py", title="Other Signals"
)

# Supply Chain
value_chain = st.Page(
    "views/supply_chain/value_chain.py", title="AI Infra Value Chain"
)
dc_inputs = st.Page(
    "views/supply_chain/dc_inputs.py", title="DC & AI Inputs"
)
prospecting = st.Page(
    "views/supply_chain/prospecting.py", title="Prospecting"
)

# News
news = st.Page("views/news/news.py", title="News")

# System
source_health = st.Page(
    "views/system/source_health.py", title="Source Health"
)

pg = st.navigation(
    {
        "": [landing],
        "Fundamentals Tracking": [
            model_performance,
            equity_analysis,
            financials,
            hyperscaler_capex,
            other_signals,
        ],
        "Supply Chain": [value_chain, dc_inputs, prospecting],
        "News": [news],
        "System": [source_health],
    }
)

pg.run()
