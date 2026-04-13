"""Regional Analysis — Power & supply trends, DC demand vs grid capacity."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

from app.lib.au_dc_charts import (
    dc_demand_scenarios_line,
    dc_share_of_nem_line,
    grid_capacity_stacked_bar,
    nem_demand_actual_line,
    COLOUR_PALETTE,
    CHART_LAYOUT,
)

_AU_DC_DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc"
DATA_DIR = _AU_DC_DATA / "processed"
REF_DIR = _AU_DC_DATA / "reference"

st.title("Regional Analysis")

# Load data
projects_path = DATA_DIR / "projects.parquet"
dc_demand_path = DATA_DIR / "dc_demand.parquet"
grid_path = DATA_DIR / "grid_capacity.parquet"
regions_path = REF_DIR / "nem_regions.csv"

projects = pd.read_parquet(projects_path) if projects_path.exists() else None
dc_demand = pd.read_parquet(dc_demand_path) if dc_demand_path.exists() else None
grid_capacity = pd.read_parquet(grid_path) if grid_path.exists() else None
regions = pd.read_csv(regions_path) if regions_path.exists() else None

nem_demand_path = DATA_DIR / "nem_demand_actual.parquet"
nem_demand = pd.read_parquet(nem_demand_path) if nem_demand_path.exists() else None

esoo_path = DATA_DIR / "esoo_forecasts.parquet"
esoo = pd.read_parquet(esoo_path) if esoo_path.exists() else None

# --- Controls ---
st.sidebar.header("Controls")
risk_view = st.sidebar.radio("Capacity View", ["Unrisked", "Risked"], index=0, key="au_reg_risk")
mw_col = "risked_mw" if risk_view == "Risked" else "facility_mw"

# ========================================
# Section 1: DC Demand vs Grid
# ========================================
st.markdown("## Power & Supply Trends")

if dc_demand is not None:
    col1, col2 = st.columns(2)
    with col1:
        fig = dc_demand_scenarios_line(dc_demand)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = dc_share_of_nem_line(dc_demand)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Data Centre vs Non-Data Centre Demand")
    scenario = st.selectbox("Scenario", dc_demand["scenario"].unique(), index=1, key="au_reg_scenario")
    sdf = dc_demand[dc_demand["scenario"] == scenario].sort_values("year")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=sdf["year"], y=sdf["dc_consumption_twh"], name="Data Centre", marker_color="#2563eb"))
    fig.add_trace(go.Bar(x=sdf["year"], y=sdf["total_nem_demand_twh"] - sdf["dc_consumption_twh"],
                         name="Non-Data Centre", marker_color="#d1d5db"))
    fig.update_layout(barmode="stack", title=f"NEM Electricity Demand Composition — {scenario}",
                      xaxis_title="Year", yaxis_title="Consumption (TWh)", **CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========================================
# Section 2: Grid Capacity by Region
# ========================================
st.markdown("## Grid Generation Capacity")

if grid_capacity is not None:
    fig = grid_capacity_stacked_bar(grid_capacity)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Grid Capacity Detail"):
        pivot = (
            grid_capacity[grid_capacity["status"] == "Operating"]
            .pivot_table(index="nem_region", columns="fuel_category", values="capacity_mw", aggfunc="sum", fill_value=0)
        )
        pivot["Total"] = pivot.sum(axis=1)
        st.dataframe(pivot.style.format("{:,.0f}"), use_container_width=True)

    st.markdown("### Generation Pipeline (Committed + Proposed)")
    pipeline = grid_capacity[grid_capacity["status"].isin(["Committed", "Proposed"])]
    if not pipeline.empty:
        fig = px.bar(
            pipeline.groupby(["nem_region", "fuel_category", "status"])["capacity_mw"].sum().reset_index(),
            x="nem_region", y="capacity_mw", color="fuel_category",
            facet_col="status", color_discrete_map=COLOUR_PALETTE,
            title="Generation Pipeline by Region & Fuel Type",
            labels={"capacity_mw": "Capacity (MW)", "nem_region": "NEM Region"},
            barmode="stack",
        )
        fig.update_layout(**CHART_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No grid pipeline data available.")
else:
    st.warning("Grid capacity data not available.")

st.markdown("---")

# ========================================
# Section 3: Regional Screener
# ========================================
st.markdown("## Regional Screener")

if projects is not None and regions is not None:
    dc_by_region = (
        projects.groupby("nem_region")
        .agg(
            num_projects=("project_name", "count"),
            total_mw_unrisked=("facility_mw", "sum"),
            total_mw_risked=("risked_mw", "sum"),
            operating_mw=("facility_mw", lambda x: x[projects.loc[x.index, "status"] == "Operating"].sum()),
            pipeline_mw=("facility_mw", lambda x: x[projects.loc[x.index, "status"] != "Operating"].sum()),
            capex_known=("capex_aud_m", lambda x: x.dropna().sum()),
        )
        .reset_index()
    )

    screener = dc_by_region.merge(regions, on="nem_region", how="left")
    screener["compute_per_capita_kw_per_m"] = (
        screener["total_mw_unrisked"] * 1000 / (screener["population_2024"] / 1_000_000)
    ).round(1)

    if grid_capacity is not None:
        grid_by_region = (
            grid_capacity[grid_capacity["status"] == "Operating"]
            .groupby("nem_region")["capacity_mw"].sum().reset_index()
            .rename(columns={"capacity_mw": "grid_capacity_mw"})
        )
        screener = screener.merge(grid_by_region, on="nem_region", how="left")
        screener["dc_as_pct_of_grid"] = (screener["total_mw_unrisked"] / screener["grid_capacity_mw"] * 100).round(2)

    display_cols = ["nem_region", "state", "num_projects", "operating_mw", "pipeline_mw",
                    "total_mw_unrisked", "total_mw_risked", "compute_per_capita_kw_per_m"]
    if "grid_capacity_mw" in screener.columns:
        display_cols += ["grid_capacity_mw", "dc_as_pct_of_grid"]
    if screener["capex_known"].sum() > 0:
        display_cols.append("capex_known")

    st.dataframe(
        screener[display_cols].sort_values("total_mw_unrisked", ascending=False),
        use_container_width=True,
        column_config={
            "nem_region": "Region", "state": "State",
            "num_projects": "# Projects",
            "operating_mw": st.column_config.NumberColumn("Operating MW", format="%d"),
            "pipeline_mw": st.column_config.NumberColumn("Pipeline MW", format="%d"),
            "total_mw_unrisked": st.column_config.NumberColumn("Total MW (Unrisked)", format="%d"),
            "total_mw_risked": st.column_config.NumberColumn("Total MW (Risked)", format="%d"),
            "compute_per_capita_kw_per_m": st.column_config.NumberColumn("kW per M Pop", format="%.1f"),
            "grid_capacity_mw": st.column_config.NumberColumn("Grid Capacity MW", format="%d"),
            "dc_as_pct_of_grid": st.column_config.NumberColumn("DC as % of Grid", format="%.2f%%"),
            "capex_known": st.column_config.NumberColumn("Known CAPEX (A$M)", format="%d"),
        },
    )

st.markdown("---")

# ========================================
# Section 4: DC Capacity by Region
# ========================================
st.markdown("## DC Capacity by Region")

if projects is not None:
    selected_region = st.selectbox("Select Region", ["All"] + sorted(projects["nem_region"].unique().tolist()), key="au_reg_region")
    filtered = projects if selected_region == "All" else projects[projects["nem_region"] == selected_region]

    col1, col2 = st.columns(2)
    with col1:
        agg = filtered.groupby(["operator", "status"])[mw_col].sum().reset_index()
        agg_total = agg.groupby("operator")[mw_col].sum().sort_values(ascending=True)
        top_ops = agg_total.tail(10).index.tolist()
        agg = agg[agg["operator"].isin(top_ops)]
        fig = px.bar(
            agg, x=mw_col, y="operator", color="status", orientation="h",
            color_discrete_map=COLOUR_PALETTE,
            title=f"Top Operators — {selected_region} ({risk_view})",
            labels={mw_col: "Capacity (MW)", "operator": ""}, barmode="stack",
        )
        fig.update_layout(**CHART_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        status_agg = filtered.groupby("status")[mw_col].sum().reset_index()
        fig = px.pie(
            status_agg, values=mw_col, names="status",
            color="status", color_discrete_map=COLOUR_PALETTE,
            title=f"Status Mix — {selected_region}", hole=0.4,
        )
        fig.update_layout(**CHART_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========================================
# Section 5: Actual NEM Demand
# ========================================
st.markdown("## Actual NEM Demand")

if nem_demand is not None:
    fig = nem_demand_actual_line(nem_demand)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Annual NEM Demand Summary"):
        nem_demand["year"] = pd.to_datetime(nem_demand["year_month"]).dt.year
        annual = nem_demand.groupby(["year", "nem_region"])["energy_twh"].sum().reset_index()
        pivot = annual.pivot_table(index="year", columns="nem_region", values="energy_twh", aggfunc="sum")
        pivot["Total"] = pivot.sum(axis=1)
        st.dataframe(pivot.style.format("{:.1f}"), use_container_width=True)

    st.caption("Source: AEMO DISPATCHREGIONSUM via NEMOSIS — 5-minute dispatch data aggregated to monthly averages")
else:
    st.info("Actual NEM demand data not available.")

st.markdown("---")

# ========================================
# Section 6: ESOO Supply-Demand Balance
# ========================================
st.markdown("## ESOO Supply-Demand Balance")

if esoo is not None:
    selected_esoo_region = st.selectbox("ESOO Region", sorted(esoo["nem_region"].unique().tolist()), key="au_reg_esoo")
    rdf = esoo[esoo["nem_region"] == selected_esoo_region].sort_values("year")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=rdf["year"], y=rdf["available_supply_mw"], name="Available Supply (MW)", marker_color="#22c55e"))
    fig.add_trace(go.Scatter(x=rdf["year"], y=rdf["max_demand_mw"], name="Max Demand (MW)",
                             mode="lines+markers", line=dict(color="#dc2626", width=2)))
    fig.update_layout(title=f"Supply-Demand Balance — {selected_esoo_region}",
                      xaxis_title="Year", yaxis_title="MW", **CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Source: AEMO 2025 ESOO, Step Change scenario, 10% POE maximum demand.")
else:
    st.info("ESOO forecast data not available.")
