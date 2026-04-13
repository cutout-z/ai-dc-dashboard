"""Market Overview — Headline KPIs, capacity trends, market breakdown."""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from app.lib.au_dc_charts import (
    capacity_by_region_bar,
    capacity_by_operator_bar,
    market_breakdown_pie,
    dc_demand_scenarios_line,
    capacity_trajectory_line,
    COLOUR_PALETTE,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc" / "processed"

st.title("Market Overview")

# Load data
projects_path = DATA_DIR / "projects.parquet"
dc_demand_path = DATA_DIR / "dc_demand.parquet"

if not projects_path.exists():
    st.error("Project database not found. Run `python etl/build_project_db.py` in au-dc-analysis first.")
    st.stop()

projects = pd.read_parquet(projects_path)
dc_demand = pd.read_parquet(dc_demand_path) if dc_demand_path.exists() else None

# --- Controls ---
st.sidebar.header("Controls")
risk_view = st.sidebar.radio("Capacity View", ["Unrisked", "Risked"], index=0, key="au_mkt_risk")
mw_col = "risked_mw" if risk_view == "Risked" else "facility_mw"

# --- KPI Row ---
st.markdown("### Key Metrics")
k1, k2, k3, k4, k5 = st.columns(5)

total_projects = len(projects)
operating = projects[projects["status"] == "Operating"]

with k1:
    st.metric("Total Projects", total_projects)
with k2:
    st.metric("Operating DCs", len(operating))
with k3:
    st.metric("Operating Capacity", f"{operating['facility_mw'].sum():,.0f} MW")
with k4:
    total_cap = projects[mw_col].sum()
    st.metric(f"Total Capacity ({risk_view})", f"{total_cap:,.0f} MW")
with k5:
    if dc_demand is not None:
        baseline = dc_demand[dc_demand["scenario"] == "Baseline"]
        if not baseline.empty:
            latest = baseline.iloc[-1]
            st.metric("DC Consumption (FY25)", f"{latest['dc_consumption_twh']:.1f} TWh",
                      delta=f"{latest['dc_share_pct']:.1f}% of NEM")
        else:
            st.metric("DC Consumption", "No baseline data")
    else:
        st.metric("DC Consumption", "No data")

st.markdown("---")

# --- Capacity Trends ---
st.markdown("### Installed Capacity")
col1, col2 = st.columns(2)

with col1:
    fig = capacity_by_region_bar(projects, title=f"Capacity by Region ({risk_view})")
    if risk_view == "Risked":
        agg = projects.groupby(["nem_region", "status"])["risked_mw"].sum().reset_index()
        fig = px.bar(agg, x="nem_region", y="risked_mw", color="status",
                     color_discrete_map=COLOUR_PALETTE, title="Capacity by Region (Risked)",
                     labels={"risked_mw": "Capacity (MW)", "nem_region": "NEM Region"},
                     barmode="stack")
        fig.update_layout(template="plotly_white", margin=dict(l=40, r=20, t=40, b=40))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig = capacity_by_operator_bar(projects, risked=(risk_view == "Risked"))
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# --- Market Breakdown ---
st.markdown("### Market Breakdown")
b1, b2, b3 = st.columns(3)

with b1:
    fig = market_breakdown_pie(projects, "operator_type", mw_col, "By Operator Type")
    st.plotly_chart(fig, use_container_width=True)
with b2:
    fig = market_breakdown_pie(projects, "size_class", mw_col, "By Project Size")
    st.plotly_chart(fig, use_container_width=True)
with b3:
    fig = market_breakdown_pie(projects, "status", mw_col, "By Development Status")
    st.plotly_chart(fig, use_container_width=True)

b4, b5 = st.columns(2)
with b4:
    fig = market_breakdown_pie(projects, "workload_type", mw_col, "By Workload Type")
    st.plotly_chart(fig, use_container_width=True)
with b5:
    fig = market_breakdown_pie(projects, "power_strategy", mw_col, "By Power Strategy")
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# --- DC Demand Scenarios ---
if dc_demand is not None:
    st.markdown("### DC Energy Consumption Forecast")
    fig = dc_demand_scenarios_line(dc_demand)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Sources: Oxford Economics/AEMO (Baseline), AEMO IASR (Step Change, Progressive Change), CEFC/Baringa (High)")

    st.markdown("### Supply vs Demand Trajectory")
    fig = capacity_trajectory_line(projects, dc_demand)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("DC capacity is cumulative facility MW by startup year. Demand scenarios converted from TWh to average MW for comparison.")
