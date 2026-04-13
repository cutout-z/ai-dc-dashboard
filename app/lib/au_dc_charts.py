"""Shared chart components for the AU Data Centre dashboard section."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


COLOUR_PALETTE = {
    # Operator types
    "Colocation": "#2563eb",
    "Hyperscaler": "#7c3aed",
    "Developer": "#059669",
    "Telecom": "#d97706",
    "Technology": "#dc2626",
    # Fuel categories
    "Fossil": "#6b7280",
    "VRE": "#22c55e",
    "Clean Baseload": "#06b6d4",
    "Storage": "#f59e0b",
    "Other": "#a3a3a3",
    # Status
    "Operating": "#22c55e",
    "Under Construction": "#3b82f6",
    "Approved": "#f59e0b",
    "Proposed": "#ef4444",
    "Announced": "#ef4444",
    "Committed": "#3b82f6",
    # Scenarios
    "Baseline": "#6b7280",
    "Step Change": "#2563eb",
    "Progressive Change": "#059669",
    "CEFC High": "#dc2626",
}

CHART_LAYOUT = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12),
)


def capacity_by_region_bar(df: pd.DataFrame, title: str = "Capacity by Region") -> go.Figure:
    agg = df.groupby(["nem_region", "status"])["facility_mw"].sum().reset_index()
    fig = px.bar(
        agg, x="nem_region", y="facility_mw", color="status",
        color_discrete_map=COLOUR_PALETTE, title=title,
        labels={"facility_mw": "Capacity (MW)", "nem_region": "NEM Region", "status": "Status"},
        barmode="stack",
    )
    fig.update_layout(**CHART_LAYOUT)
    return fig


def capacity_by_operator_bar(df: pd.DataFrame, risked: bool = False, top_n: int = 15) -> go.Figure:
    mw_col = "risked_mw" if risked else "facility_mw"
    label = "Risked" if risked else "Unrisked"
    agg = df.groupby("operator")[mw_col].sum().sort_values(ascending=True).tail(top_n).reset_index()
    fig = px.bar(
        agg, x=mw_col, y="operator", orientation="h",
        title=f"Top Operators by Capacity ({label})",
        labels={mw_col: f"Capacity (MW) — {label}", "operator": ""},
        color_discrete_sequence=["#2563eb"],
    )
    fig.update_layout(**CHART_LAYOUT)
    return fig


def dc_demand_scenarios_line(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for scenario in df["scenario"].unique():
        sdf = df[df["scenario"] == scenario].sort_values("year")
        fig.add_trace(go.Scatter(
            x=sdf["year"], y=sdf["dc_consumption_twh"],
            name=scenario, mode="lines+markers",
            line=dict(color=COLOUR_PALETTE.get(scenario, "#6b7280"), width=2),
            marker=dict(size=5),
        ))
    fig.update_layout(
        title="Data Centre Energy Consumption Scenarios (TWh)",
        xaxis_title="Year", yaxis_title="DC Consumption (TWh)",
        **CHART_LAYOUT,
    )
    return fig


def dc_share_of_nem_line(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for scenario in df["scenario"].unique():
        sdf = df[df["scenario"] == scenario].sort_values("year")
        fig.add_trace(go.Scatter(
            x=sdf["year"], y=sdf["dc_share_pct"],
            name=scenario, mode="lines+markers",
            line=dict(color=COLOUR_PALETTE.get(scenario, "#6b7280"), width=2),
            marker=dict(size=5),
        ))
    fig.update_layout(
        title="Data Centre Share of NEM Demand (%)",
        xaxis_title="Year", yaxis_title="DC Share (%)",
        **CHART_LAYOUT,
    )
    return fig


def market_breakdown_pie(df: pd.DataFrame, group_col: str, value_col: str = "facility_mw",
                         title: str = "") -> go.Figure:
    agg = df.groupby(group_col)[value_col].sum().reset_index()
    agg = agg[agg[value_col] > 0].sort_values(value_col, ascending=False)
    fig = px.pie(
        agg, values=value_col, names=group_col, title=title, hole=0.4,
        color=group_col, color_discrete_map=COLOUR_PALETTE,
    )
    fig.update_layout(**CHART_LAYOUT)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


def capacity_trajectory_line(projects: pd.DataFrame, dc_demand: pd.DataFrame = None) -> go.Figure:
    timeline = projects.dropna(subset=["startup_year"]).copy()
    timeline["startup_year"] = timeline["startup_year"].astype(int)
    yearly = timeline.groupby("startup_year")["facility_mw"].sum().sort_index().cumsum().reset_index()
    yearly.columns = ["year", "cumulative_mw"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=yearly["year"], y=yearly["cumulative_mw"],
        name="DC Capacity (MW)", mode="lines+markers",
        line=dict(color="#2563eb", width=3), marker=dict(size=6),
    ))

    if dc_demand is not None:
        for scenario in dc_demand["scenario"].unique():
            sdf = dc_demand[dc_demand["scenario"] == scenario].sort_values("year")
            approx_mw = sdf["dc_consumption_twh"] * 1_000_000 / 8760
            fig.add_trace(go.Scatter(
                x=sdf["year"], y=approx_mw,
                name=f"Demand — {scenario} (avg MW)", mode="lines",
                line=dict(color=COLOUR_PALETTE.get(scenario, "#6b7280"), width=2, dash="dash"),
            ))

    fig.update_layout(
        title="DC Capacity Trajectory vs Demand Scenarios",
        xaxis_title="Year", yaxis_title="MW",
        **CHART_LAYOUT,
    )
    return fig


def nem_demand_actual_line(demand: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    region_colors = {
        "NSW1": "#2563eb", "VIC1": "#7c3aed", "QLD1": "#059669",
        "SA1": "#d97706", "TAS1": "#06b6d4",
    }
    for region in sorted(demand["nem_region"].unique()):
        rdf = demand[demand["nem_region"] == region].sort_values("year_month")
        fig.add_trace(go.Scatter(
            x=rdf["year_month"], y=rdf["avg_demand_mw"],
            name=region, mode="lines",
            line=dict(color=region_colors.get(region, "#6b7280"), width=1.5),
        ))
    fig.update_layout(
        title="Actual NEM Demand by Region (Monthly Average MW)",
        xaxis_title="Month", yaxis_title="Average Demand (MW)",
        **CHART_LAYOUT,
    )
    return fig


def price_history_chart(history: pd.DataFrame, ticker_names: dict = None) -> go.Figure:
    fig = go.Figure()
    colors = ["#2563eb", "#059669", "#d97706"]
    for i, ticker in enumerate(history["ticker"].unique()):
        tdf = history[history["ticker"] == ticker].sort_values("date")
        name = ticker_names.get(ticker, ticker) if ticker_names else ticker
        fig.add_trace(go.Scatter(
            x=tdf["date"], y=tdf["close"],
            name=name, mode="lines",
            line=dict(color=colors[i % len(colors)], width=2),
        ))
    fig.update_layout(
        title="Share Price (12 Months)",
        xaxis_title="Date", yaxis_title="Price (AUD)",
        **CHART_LAYOUT,
    )
    return fig


def grid_capacity_stacked_bar(df: pd.DataFrame, region: str = None) -> go.Figure:
    if region and region != "All":
        df = df[df["nem_region"] == region]
    agg = df[df["status"] == "Operating"].groupby(["nem_region", "fuel_category"])["capacity_mw"].sum().reset_index()
    fig = px.bar(
        agg, x="nem_region", y="capacity_mw", color="fuel_category",
        color_discrete_map=COLOUR_PALETTE,
        title="Grid Generation Capacity by Region & Fuel Type (Operating)",
        labels={"capacity_mw": "Capacity (MW)", "nem_region": "NEM Region", "fuel_category": "Fuel Type"},
        barmode="stack",
    )
    fig.update_layout(**CHART_LAYOUT)
    return fig
