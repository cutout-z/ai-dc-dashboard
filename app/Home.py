"""AI & DC Dashboard — navigation entry point."""

import sys
from pathlib import Path

# Ensure repo root is on sys.path so `from app.lib.xxx` imports work on Streamlit Cloud
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import streamlit as st

st.set_page_config(
    page_title="AI & DC Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"
st.session_state["db_path"] = str(DB_PATH)

# Theme-aware colors — adapts Plotly charts to active Streamlit theme
_dark = (st.get_option("theme.base") or "dark") == "dark"
st.session_state["plotly_template"] = "plotly_dark" if _dark else "plotly_white"
st.session_state["annotation_color"] = "white" if _dark else "#333"
st.session_state["hoverlabel_bg"] = "#333" if _dark else "white"
st.session_state["marker_line_color"] = "white" if _dark else "#333"
st.session_state["error_bar_color"] = "white" if _dark else "#333"

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
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavViewLessButton"] {
        display: none !important;
    }
    /* Make section headings non-collapsible (plain labels) */
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavSeparator"] details {
        pointer-events: none;
    }
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavSeparator"] details summary::marker,
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavSeparator"] details summary::-webkit-details-marker {
        display: none !important;
    }
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavSeparator"] details[open] > summary ~ * {
        display: block !important;
    }
    /* Indent page links under headings */
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"] {
        padding-left: 2rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Overview
landing = st.Page("views/landing.py", title="Overview", default=True, url_path="home")

# Fundamentals Tracking
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

# LLM Performance (sub-section under Fundamentals Tracking)
llm_leaderboard = st.Page(
    "views/fundamentals/llm_performance/leaderboard.py", title="LLM Leaderboard"
)
llm_benchmark = st.Page(
    "views/fundamentals/llm_performance/benchmark_performance.py", title="Benchmark Performance"
)
llm_labs = st.Page(
    "views/fundamentals/llm_performance/labs_and_countries.py", title="Labs and Countries"
)
llm_open = st.Page(
    "views/fundamentals/llm_performance/open_models.py", title="Open Models"
)
llm_capabilities = st.Page(
    "views/fundamentals/llm_performance/model_capabilities.py", title="Model Capabilities"
)
llm_prices = st.Page(
    "views/fundamentals/llm_performance/prices_and_value.py", title="Prices and Value"
)
llm_efficiency = st.Page(
    "views/fundamentals/llm_performance/efficiency_and_scale.py", title="Efficiency and Scale"
)
llm_speed = st.Page(
    "views/fundamentals/llm_performance/speed_and_context.py", title="Speed and Context"
)
llm_preference = st.Page(
    "views/fundamentals/llm_performance/human_preference.py", title="Human Preference"
)
llm_ai_demand = st.Page(
    "views/fundamentals/llm_performance/ai_demand_indicators.py", title="AI Demand Indicators"
)
llm_lab_revenue = st.Page(
    "views/fundamentals/llm_performance/frontier_lab_revenue.py", title="Frontier Lab Revenue & Valuations"
)
llm_gpu_hardware = st.Page(
    "views/fundamentals/llm_performance/gpu_hardware.py", title="GPU Hardware & Pricing"
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

# Other
guidance_revisions = st.Page(
    "views/fundamentals/guidance_revisions.py", title="Historical Guidance Revisions"
)

# News
news = st.Page("views/news/news.py", title="News")

# System
source_health = st.Page(
    "views/system/source_health.py", title="Source Health"
)
acronyms = st.Page(
    "views/system/acronyms.py", title="Acronyms & Glossary"
)

# Australian Market
au_landing = st.Page(
    "views/au_dc/landing.py", title="Overview", url_path="au-overview"
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
        "Dashboard": [landing],
        "Financial Analysis": [
            equity_analysis,
            financials,
            hyperscaler_capex,
            guidance_revisions,
            other_signals,
        ],
        "LLM & GPU Performance": [
            llm_leaderboard,
            llm_benchmark,
            llm_labs,
            llm_open,
            llm_capabilities,
            llm_prices,
            llm_efficiency,
            llm_speed,
            llm_preference,
            llm_ai_demand,
            llm_lab_revenue,
            llm_gpu_hardware,
        ],
        "Supply Chain": [value_chain, dc_inputs, prospecting],
        "Australian Market": [
            au_landing,
            au_market_overview,
            au_regional,
            au_company,
            au_project,
        ],
        "Other": [news, source_health, acronyms],
    }
)

pg.run()
