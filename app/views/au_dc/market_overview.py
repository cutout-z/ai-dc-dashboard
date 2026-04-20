"""Market Overview — Headline KPIs, capacity trends, market breakdown."""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from app.lib.au_dc_charts import (
    capacity_by_region_bar,
    capacity_by_operator_bar,
    market_breakdown_pie,
    capacity_forecast_chart,
    COLOUR_PALETTE,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc" / "processed"

st.title("Market Overview")

# Load data
projects_path = DATA_DIR / "projects.parquet"

if not projects_path.exists():
    st.error("Project database not found. Run `python etl/build_project_db.py` in au-dc-analysis first.")
    st.stop()

projects = pd.read_parquet(projects_path)

# --- Controls ---
st.sidebar.header("Controls")
risk_view = st.sidebar.radio("Capacity View", ["Unrisked", "Risked"], index=0, key="au_mkt_risk")
mw_col = "risked_mw" if risk_view == "Risked" else "facility_mw"

# --- KPI Row ---
st.markdown("### Key Metrics")
k1, k2, k3, k4 = st.columns(4)

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

with st.expander("Data sources & methodology", icon=":material/info:"):
    st.markdown(
        """
**Coverage note:** This dataset tracks publicly announced and verifiable projects. It will not capture
every data centre — undisclosed hyperscaler on-premises deployments, small enterprise facilities (<10 MW),
and government classified infrastructure are not included. Figures reflect publicly available information
at the time of last update.

**Project database**
Manually curated from named public sources: ASX/NZX announcements, company IR pages, NSW/VIC/QLD State
Significant Development (SSD) portals, Data Center Dynamics, datacentermap.com, datacenterhawk.com, and
press releases. Each project is traced to a specific source — no estimated or synthesised entries.
Updated periodically as announcements are made; there is no automated refresh.

**Capacity methodology**
- *Unrisked*: total stated facility MW at full build-out (as disclosed by operator)
- *Risked*: probability-weighted MW based on development status and power/grid connection certainty —

  | Status | Weight | Rationale |
  |---|---|---|
  | Operating | 100% | Built and running |
  | Under Construction | 100% | Power and site secured; build in progress |
  | Approved — power secured | 75% | Planning approved and grid connection confirmed |
  | Approved — grid connection pending | 25% | Planning approved; grid connection not yet secured |
  | Proposed | 0% | Announced only; no power pathway confirmed |

- Where only a partial phase is funded, the figure reflects what has been disclosed (not full campus aspiration)
- *Power secured* status is manually assessed from public disclosures; defaults to unconfirmed if not explicitly announced

**Other providers that track Australian DC builds**
[Data Center Dynamics](https://www.datacenterdynamics.com/en/market/australasia/) ·
[datacentermap.com](https://www.datacentermap.com/australia/) ·
[datacenterhawk.com](https://datacenterhawk.com/market/australia) ·
[AIIA Data Centre Industry Report](https://www.aiia.com.au/)
        """,
        unsafe_allow_html=False,
    )

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
        fig.update_layout(
            template=st.session_state.get("plotly_template", "plotly_dark"),
            margin=dict(l=40, r=20, t=40, b=80),
            legend=dict(orientation="h", yanchor="top", y=-0.2, x=0),
        )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig = capacity_by_operator_bar(projects)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("### Forecast Pipeline by Risk Category")
fig = capacity_forecast_chart(projects)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Cumulative stated capacity by project startup year, colour-coded by certainty tier. "
    "Proposed projects with no confirmed startup year pinned to 2028. "
    "Power secured status for Approved projects based on public disclosures."
)

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

b4, b5, _ = st.columns(3)
with b4:
    fig = market_breakdown_pie(projects, "workload_type", mw_col, "By Workload Type")
    st.plotly_chart(fig, use_container_width=True)
with b5:
    fig = market_breakdown_pie(projects, "power_strategy", mw_col, "By Power Strategy")
    st.plotly_chart(fig, use_container_width=True)

st.info(
    "**Source — Manually curated Australian DC project database.**  \n"
    "Every entry is traced to a named public source: ASX/NZX announcements, company IR pages, "
    "NSW/VIC/QLD State Significant Development (SSD) portals, "
    "[Data Center Dynamics](https://www.datacenterdynamics.com/en/market/australasia/), "
    "[datacentermap.com](https://www.datacentermap.com/australia/), "
    "[datacenterhawk.com](https://datacenterhawk.com/market/australia), and operator press releases. "
    "No estimated or synthesised entries. Coverage excludes undisclosed hyperscaler on-premises deployments, "
    "enterprise facilities <10 MW, and classified government infrastructure. "
    "Updated periodically as announcements are made — there is no automated refresh.  \n"
    "See *Data sources & methodology* above for capacity weighting rules.",
    icon=":material/info:",
)

