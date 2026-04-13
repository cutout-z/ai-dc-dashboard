"""Project Analysis — Full project database with filtering."""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from app.lib.au_dc_charts import COLOUR_PALETTE, CHART_LAYOUT

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc" / "processed"

st.title("Project Analysis")

projects_path = DATA_DIR / "projects.parquet"
if not projects_path.exists():
    st.error("Project database not found.")
    st.stop()

projects = pd.read_parquet(projects_path)

# ========================================
# Filters
# ========================================
st.sidebar.header("Filters")

statuses = ["All"] + sorted(projects["status"].unique().tolist())
sel_status = st.sidebar.multiselect("Status", statuses, default=["All"], key="au_proj_status")

regions_list = ["All"] + sorted(projects["nem_region"].unique().tolist())
sel_region = st.sidebar.multiselect("Region", regions_list, default=["All"], key="au_proj_region")

op_types = ["All"] + sorted(projects["operator_type"].dropna().unique().tolist())
sel_op_type = st.sidebar.multiselect("Operator Type", op_types, default=["All"], key="au_proj_optype")

min_mw = st.sidebar.slider("Min Facility MW", 0, int(projects["facility_mw"].max()), 0, key="au_proj_mw")

# Apply filters
filtered = projects.copy()
if "All" not in sel_status:
    filtered = filtered[filtered["status"].isin(sel_status)]
if "All" not in sel_region:
    filtered = filtered[filtered["nem_region"].isin(sel_region)]
if "All" not in sel_op_type:
    filtered = filtered[filtered["operator_type"].isin(sel_op_type)]
filtered = filtered[filtered["facility_mw"] >= min_mw]

# ========================================
# KPIs
# ========================================
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Projects Shown", len(filtered))
with k2:
    st.metric("Total MW (Unrisked)", f"{filtered['facility_mw'].sum():,.0f}")
with k3:
    st.metric("Total MW (Risked)", f"{filtered['risked_mw'].sum():,.0f}")
with k4:
    if "capex_estimated" in filtered.columns:
        total_capex = filtered["capex_aud_m"].dropna().sum()
        est_count = filtered["capex_estimated"].sum()
        st.metric("Total CAPEX", f"A${total_capex:,.0f}M",
                  delta=f"{int(est_count)} estimated" if est_count > 0 else None)
    else:
        known_capex = filtered["capex_aud_m"].dropna().sum()
        st.metric("Known CAPEX", f"A${known_capex:,.0f}M" if known_capex > 0 else "N/A")

st.markdown("---")

# ========================================
# Project Table
# ========================================
st.markdown("### Project Database")

display_cols = [
    "project_name", "operator", "parent_company", "operator_type",
    "nem_region", "state", "suburb", "status", "size_class",
    "facility_mw", "critical_it_mw", "risked_mw",
    "startup_year", "full_capacity_year", "capex_aud_m", "capex_estimated",
    "power_strategy", "workload_type", "financial_sponsor", "source",
]
available = [c for c in display_cols if c in filtered.columns]

st.dataframe(
    filtered[available].sort_values("facility_mw", ascending=False),
    use_container_width=True, hide_index=True, height=600,
    column_config={
        "project_name": "Project", "operator": "Operator", "parent_company": "Parent",
        "operator_type": "Type", "nem_region": "Region", "state": "State",
        "suburb": "Suburb", "status": "Status", "size_class": "Size",
        "facility_mw": st.column_config.NumberColumn("Facility MW", format="%d"),
        "critical_it_mw": st.column_config.NumberColumn("IT MW", format="%d"),
        "risked_mw": st.column_config.NumberColumn("Risked MW", format="%d"),
        "startup_year": st.column_config.NumberColumn("Startup", format="%d"),
        "full_capacity_year": st.column_config.NumberColumn("Full Capacity", format="%d"),
        "capex_aud_m": st.column_config.NumberColumn("CAPEX (A$M)", format="%d"),
        "capex_estimated": st.column_config.CheckboxColumn("Est?", default=False),
        "power_strategy": "Power Strategy", "workload_type": "Workload",
        "financial_sponsor": "Sponsor", "source": "Source",
    },
)

st.markdown("---")

# ========================================
# Project Deep Dive
# ========================================
st.markdown("### Project Deep Dive")

project_names = sorted(filtered["project_name"].unique().tolist())
selected_project = st.selectbox("Select Project", project_names, key="au_proj_select")

proj = filtered[filtered["project_name"] == selected_project]
if not proj.empty:
    p = proj.iloc[0]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Core Attributes")
        st.markdown(f"**Operator:** {p.get('operator', 'N/A')}")
        st.markdown(f"**Parent Company:** {p.get('parent_company', 'N/A')}")
        st.markdown(f"**Operator Type:** {p.get('operator_type', 'N/A')}")
        st.markdown(f"**Status:** {p.get('status', 'N/A')}")
        st.markdown(f"**Workload:** {p.get('workload_type', 'N/A')}")
        st.markdown(f"**Power Strategy:** {p.get('power_strategy', 'N/A')}")

    with col2:
        st.markdown("#### Location & Timing")
        st.markdown(f"**NEM Region:** {p.get('nem_region', 'N/A')}")
        st.markdown(f"**State:** {p.get('state', 'N/A')}")
        st.markdown(f"**Suburb:** {p.get('suburb', 'N/A')}")
        st.markdown(f"**Startup Year:** {int(p['startup_year']) if pd.notna(p.get('startup_year')) else 'N/A'}")
        st.markdown(f"**Full Capacity:** {int(p['full_capacity_year']) if pd.notna(p.get('full_capacity_year')) else 'N/A'}")

    with col3:
        st.markdown("#### Technical & Economics")
        st.markdown(f"**Facility Power:** {p.get('facility_mw', 'N/A'):,.0f} MW" if pd.notna(p.get('facility_mw')) else "**Facility Power:** N/A")
        st.markdown(f"**Critical IT Power:** {p.get('critical_it_mw', 'N/A'):,.0f} MW" if pd.notna(p.get('critical_it_mw')) else "**Critical IT Power:** N/A")
        st.markdown(f"**Risk Weight:** {p.get('risk_weight', 'N/A'):.0%}" if pd.notna(p.get('risk_weight')) else "**Risk Weight:** N/A")
        st.markdown(f"**Risked MW:** {p.get('risked_mw', 'N/A'):,.0f} MW" if pd.notna(p.get('risked_mw')) else "**Risked MW:** N/A")
        capex = p.get('capex_aud_m')
        capex_est = p.get('capex_estimated', False)
        if pd.notna(capex):
            est_label = " *(estimated)*" if capex_est else ""
            st.markdown(f"**CAPEX:** A${capex:,.0f}M{est_label}")
        else:
            st.markdown("**CAPEX:** Not disclosed")
        st.markdown(f"**Size Class:** {p.get('size_class', 'N/A')}")

    # Efficiency metrics
    project_pue = p.get("pue") if pd.notna(p.get("pue")) else None
    project_wue = p.get("wue") if pd.notna(p.get("wue")) else None
    pue_source = p.get("pue_source", "")

    if project_pue or project_wue:
        st.markdown("---")
        st.markdown("#### Efficiency Metrics")
        eff1, eff2 = st.columns(2)
        with eff1:
            st.metric("PUE", f"{project_pue:.2f}" if project_pue else "N/A")
        with eff2:
            st.metric("WUE (L/kWh)", f"{project_wue:.2f}" if project_wue else "N/A")
        if pue_source:
            st.caption(f"Source: {pue_source}")

    # Estimated energy consumption
    if pd.notna(p.get("facility_mw")):
        st.markdown("---")
        st.markdown("#### Estimated Energy Metrics")
        default_pue = project_pue if project_pue else 1.4
        pue = st.slider("PUE (adjust to override)", 1.05, 2.0, float(default_pue), 0.01, key="au_proj_pue")
        it_mw = p["critical_it_mw"] if pd.notna(p.get("critical_it_mw")) else p["facility_mw"] / pue
        facility_mw = p["facility_mw"]
        annual_gwh = facility_mw * 8760 / 1000

        e1, e2, e3 = st.columns(3)
        with e1:
            st.metric("Max Annual Energy", f"{annual_gwh:,.0f} GWh")
        with e2:
            st.metric("Equivalent Homes", f"{annual_gwh * 1000 / 6.5:,.0f}")
        with e3:
            st.metric("Estimated IT MW", f"{it_mw:,.0f} MW")

    st.markdown(f"**Source:** {p.get('source', 'N/A')}")

st.markdown("---")

# ========================================
# Charts
# ========================================
st.markdown("### Visualisations")

tab1, tab2 = st.tabs(["By Size Class", "Timeline"])

with tab1:
    size_agg = filtered.groupby(["size_class", "status"])["facility_mw"].sum().reset_index()
    fig = px.bar(
        size_agg, x="size_class", y="facility_mw", color="status",
        color_discrete_map=COLOUR_PALETTE,
        title="Capacity by Size Class",
        labels={"facility_mw": "Capacity (MW)", "size_class": ""},
        barmode="stack",
    )
    fig.update_layout(**CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    timeline = filtered.dropna(subset=["startup_year"])
    if not timeline.empty:
        timeline_agg = timeline.groupby(["startup_year", "status"])["facility_mw"].sum().reset_index()
        fig = px.bar(
            timeline_agg, x="startup_year", y="facility_mw", color="status",
            color_discrete_map=COLOUR_PALETTE,
            title="Capacity by Startup Year",
            labels={"facility_mw": "Capacity (MW)", "startup_year": "Year"},
            barmode="stack",
        )
        fig.update_layout(**CHART_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No startup year data available for timeline chart.")
