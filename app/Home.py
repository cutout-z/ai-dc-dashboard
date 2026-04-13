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

# Inject dashboard title at the very top of the sidebar (above st.navigation)
st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"]::before {
        content: "AI & DC Dashboard";
        display: block;
        font-size: 1.5rem;
        font-weight: 700;
        padding: 0.5rem 1rem 1rem 1rem;
    }
    /* Always show all nav items — disable View more/less collapse */
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavItems"] {
        max-height: none !important;
        overflow: visible !important;
    }
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavViewMoreButton"],
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavViewLessButton"],
    [data-testid="stSidebarNav"] button[kind="header"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Fundamentals Tracking
model_performance = st.Page(
    "views/fundamentals/model_performance.py", title="LLM Performance Analysis"
)
equity_analysis = st.Page(
    "views/fundamentals/equity_analysis.py", title="Equity Analysis (key players)"
)
financials = st.Page(
    "views/fundamentals/financials.py", title="Financial (key players)"
)
hyperscaler_capex = st.Page(
    "views/fundamentals/hyperscaler_capex.py", title="AI & DC CAPEX"
)
other_signals = st.Page(
    "views/fundamentals/other_signals.py", title="Other Signals"
)
power = st.Page(
    "views/fundamentals/power.py", title="Power"
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
news = st.Page("views/news/news.py", title="News", default=True)

# System
source_health = st.Page(
    "views/system/source_health.py", title="Source Health"
)

# Australian Market
au_landing = st.Page(
    "views/au_dc/landing.py", title="Overview"
)
au_market_overview = st.Page(
    "views/au_dc/market_overview.py", title="Market Overview"
)
au_regional = st.Page(
    "views/au_dc/regional_analysis.py", title="Regional Analysis"
)
au_company = st.Page(
    "views/au_dc/company_analysis.py", title="Company Analysis"
)
au_project = st.Page(
    "views/au_dc/project_analysis.py", title="Project Analysis"
)

pg = st.navigation(
    {
        "Fundamentals Tracking": [
            model_performance,
            equity_analysis,
            financials,
            hyperscaler_capex,
            other_signals,
            power,
        ],
        "Supply Chain": [value_chain, dc_inputs, prospecting],
        "Other": [news, source_health],
        "Australian Market - Alpha/WIP": [
            au_landing,
            au_market_overview,
            au_regional,
            au_company,
            au_project,
        ],
    }
)

pg.run()
