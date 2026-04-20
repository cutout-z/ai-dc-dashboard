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

def _chart_layout():
    import streamlit as _st
    return dict(
        template=_st.session_state.get("plotly_template", "plotly_dark"),
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        margin=dict(l=40, r=20, t=40, b=40),
        hoverlabel=dict(bgcolor=_st.session_state.get("hoverlabel_bg", "#333"), font_size=12),
    )

CHART_LAYOUT = _chart_layout()


def capacity_by_region_bar(df: pd.DataFrame, title: str = "Capacity by Region") -> go.Figure:
    agg = df.groupby(["nem_region", "status"])["facility_mw"].sum().reset_index()
    fig = px.bar(
        agg, x="nem_region", y="facility_mw", color="status",
        color_discrete_map=COLOUR_PALETTE, title=title,
        labels={"facility_mw": "Capacity (MW)", "nem_region": "NEM Region", "status": "Status"},
        barmode="stack",
    )
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.2, x=0),
        **{**CHART_LAYOUT, "margin": dict(l=40, r=20, t=40, b=80)},
    )
    return fig


def capacity_by_operator_bar(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    agg = df.groupby("operator").agg(
        risked=("risked_mw", "sum"),
        unrisked=("facility_mw", "sum"),
    ).reset_index()
    agg["speculative"] = agg["unrisked"] - agg["risked"]
    agg = agg.sort_values("unrisked", ascending=True).tail(top_n)

    # Aggregate sources per operator for hover tooltip
    if "source" in df.columns:
        src = (
            df[df["operator"].isin(agg["operator"])]
            .groupby("operator")["source"]
            .apply(lambda s: "<br>".join(
                f"· {v}" for v in sorted(s.dropna().astype(str).unique()) if v.strip()
            ))
            .reset_index()
            .rename(columns={"source": "sources"})
        )
        agg = agg.merge(src, on="operator", how="left")
        agg["sources"] = agg["sources"].fillna("—")
    else:
        agg["sources"] = "—"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=agg["operator"], x=agg["risked"],
        name="Risked", orientation="h",
        marker_color="#2563eb",
        customdata=agg[["unrisked", "sources"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Risked: <b>%{x:,.0f} MW</b><br>"
            "Unrisked total: %{customdata[0]:,.0f} MW<br>"
            "<br><i>Sources:</i><br>%{customdata[1]}"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        y=agg["operator"], x=agg["speculative"],
        name="Speculative (unrisked − risked)", orientation="h",
        marker_color="rgba(37,99,235,0.25)",
        marker_line=dict(color="#2563eb", width=1),
        customdata=agg[["unrisked", "sources"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Speculative: <b>%{x:,.0f} MW</b><br>"
            "Unrisked total: %{customdata[0]:,.0f} MW<br>"
            "<br><i>Sources:</i><br>%{customdata[1]}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        barmode="stack",
        title="Top Operators by Capacity",
        xaxis_title="Capacity (MW)",
        yaxis_title="",
        legend=dict(orientation="h", yanchor="top", y=-0.12, x=0),
        **{**CHART_LAYOUT, "margin": dict(l=40, r=20, t=40, b=90)},
    )
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
    fig.update_traces(textinfo="none")
    fig.update_layout(
        height=300,
        legend=dict(orientation="h", yanchor="top", y=-0.05, x=0.5, xanchor="center"),
        **{**CHART_LAYOUT, "margin": dict(l=20, r=20, t=40, b=70)},
    )
    return fig




def capacity_forecast_chart(projects: pd.DataFrame) -> go.Figure:
    """Cumulative risked capacity by year, stacked by risk tier.

    Risk tiers derived from risk_weight column set by the risk model:
      Operating / UC → 100%
      Approved (power secured) → 75%
      Approved (no power) → 25%
      Proposed → 0% (not shown)
    """
    timeline = projects.copy()
    # Operating with no startup_year are already built — pin to 2019 (shows from chart start)
    timeline.loc[(timeline["status"] == "Operating") & (timeline["startup_year"].isna()), "startup_year"] = 2019
    # Proposed/pipeline with no startup_year — pin to 2028 (conservative far end)
    timeline.loc[(timeline["status"] != "Operating") & (timeline["startup_year"].isna()), "startup_year"] = 2028
    timeline = timeline.dropna(subset=["startup_year"])
    timeline["startup_year"] = timeline["startup_year"].astype(int)

    # Map risk_weight + status → display group
    def _group(row):
        s, w = row["status"], row["risk_weight"]
        if s == "Operating":
            return "Operating"
        if s == "Under Construction":
            return "Under Construction"
        if s == "Approved" and w >= 0.74:
            return "Approved — Power Secured"
        if s == "Approved":
            return "Approved — Grid Pending"
        return "Proposed"

    timeline["group"] = timeline.apply(_group, axis=1)

    years = list(range(2020, 2031))
    groups = [
        "Operating",
        "Under Construction",
        "Approved — Power Secured",
        "Approved — Grid Pending",
        "Proposed",
    ]
    colors = {
        "Operating": "#22c55e",
        "Under Construction": "#3b82f6",
        "Approved — Power Secured": "#f59e0b",
        "Approved — Grid Pending": "#fde68a",
        "Proposed": "#ef4444",
    }

    rows = []
    for year in years:
        for group in groups:
            subset = timeline[(timeline["group"] == group) & (timeline["startup_year"] <= year)]
            rows.append({"year": year, "group": group, "mw": subset["facility_mw"].sum()})
    df = pd.DataFrame(rows)

    fig = go.Figure()
    for group in groups:
        gdf = df[df["group"] == group]
        if gdf["mw"].sum() == 0:
            continue
        fig.add_trace(go.Bar(
            x=gdf["year"], y=gdf["mw"],
            name=group,
            marker_color=colors[group],
        ))

    fig.update_layout(
        barmode="stack",
        xaxis_title="Year",
        yaxis_title="Cumulative Capacity (MW, unrisked)",
        legend=dict(orientation="h", yanchor="top", y=-0.15, x=0),
        **{**CHART_LAYOUT, "margin": dict(l=40, r=20, t=40, b=90)},
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
