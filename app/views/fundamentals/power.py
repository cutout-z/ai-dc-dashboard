"""DC Power — demand forecasts, supply gap, queue bottleneck, sourcing tracker."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"

st.title("Power")
st.caption(
    "Power constraint — not silicon — is now the binding constraint on hyperscale AI clusters. "
    "All major forecasters project near-doubling of data centre power demand by 2030. "
    "The key risk: if power build-out falls behind, CAPEX commitments become stranded."
)

# ══════════════════════════════════════════════════════════════
# DC Power Demand Forecasts (existing)
# ══════════════════════════════════════════════════════════════
st.header("DC Power Demand Forecasts")

power_path = DATA_DIR / "dc_power_forecasts.csv"
if power_path.exists():
    df_power = pd.read_csv(power_path)

    col1, col2 = st.columns(2)
    with col1:
        df_global = df_power[df_power["region"] == "Global"]
        if not df_global.empty:
            fig_global = px.line(df_global, x="year", y="demand_twh", color="source", line_dash="scenario",
                                  markers=True, title="Global DC Power Demand (TWh)",
                                  labels={"demand_twh": "TWh", "year": "Year"})
            fig_global.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_global, use_container_width=True)

    with col2:
        df_us = df_power[df_power["region"].isin(["United States", "PJM Interconnect", "Texas"])]
        if not df_us.empty:
            fig_us = px.line(df_us, x="year", y="demand_twh", color="region", line_dash="source",
                              markers=True, title="US / Regional DC Power Demand (TWh)",
                              labels={"demand_twh": "TWh", "year": "Year"})
            fig_us.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_us, use_container_width=True)

    with st.expander("Full Forecast Data"):
        st.dataframe(df_power[["source", "region", "year", "demand_twh", "scenario", "notes"]],
                      use_container_width=True, hide_index=True)
else:
    st.warning("DC power forecasts CSV missing (data/reference/dc_power_forecasts.csv).")

# ══════════════════════════════════════════════════════════════
# Supply Context
# ══════════════════════════════════════════════════════════════
st.header("Supply Context")
st.caption(
    "No published forecast projects DC-specific power supply. "
    "Instead, read the demand growth (above) against these supply-side constraints: "
    "grid additions are mostly intermittent, the interconnection queue has a 5-year wait "
    "and 13% completion rate, and firm baseload additions are minimal."
)

supply_path = DATA_DIR / "dc_power_supply.csv"

if supply_path.exists():
    df_supply = pd.read_csv(supply_path)

    # Current DC consumption vs demand growth
    col_s1, col_s2 = st.columns(2)

    with col_s1:
        m1, m2 = st.columns(2)
        df_dc_us = df_supply[(df_supply["region"] == "United States")
                              & (df_supply["supply_type"] == "DC Consumption")]
        df_dc_gl = df_supply[(df_supply["region"] == "Global")
                              & (df_supply["supply_type"] == "DC Consumption")]
        if not df_dc_us.empty:
            m1.metric("US DC Consumption (2024)", f"{df_dc_us.iloc[0]['supply_twh']:.0f} TWh",
                       help="IEA Electricity 2025 — 45% of global DC consumption")
        if not df_dc_gl.empty:
            m2.metric("Global DC Consumption (2024)", f"{df_dc_gl.iloc[0]['supply_twh']:.0f} TWh",
                       help="IEA Electricity 2025 — ~1.5% of global electricity")

        # Demand growth delta
        demand_2030_gl = df_power[
            (df_power["region"] == "Global") & (df_power["source"] == "IEA")
            & (df_power["year"] == 2030)
        ]["demand_twh"].values
        demand_2030_us = df_power[
            (df_power["region"] == "United States") & (df_power["source"] == "IEA")
            & (df_power["year"] == 2030)
        ]["demand_twh"].values

        m3, m4 = st.columns(2)
        if len(demand_2030_us):
            m3.metric("US Demand 2030 (IEA)", f"{demand_2030_us[0]:.0f} TWh",
                       delta=f"+{demand_2030_us[0] - 183:.0f} TWh vs today",
                       delta_color="inverse")
        if len(demand_2030_gl):
            m4.metric("Global Demand 2030 (IEA)", f"{demand_2030_gl[0]:.0f} TWh",
                       delta=f"+{demand_2030_gl[0] - 415:.0f} TWh vs today",
                       delta_color="inverse")

    with col_s2:
        # 2025 planned additions breakdown
        st.markdown("**US Planned Capacity Additions — 2025 (EIA)**")
        df_adds = df_supply[df_supply["supply_type"].str.startswith("Planned Additions (")].copy()
        if not df_adds.empty:
            df_adds["label"] = df_adds["supply_type"].str.extract(r"\((.+)\)")
            df_adds = df_adds.sort_values("capacity_gw", ascending=True)
            fig_adds = go.Figure()
            colors = {"Solar": "#F39C12", "Battery": "#3498DB", "Wind": "#2ECC71",
                       "Gas": "#95A5A6", "Total": "#E74C3C"}
            df_adds_no_total = df_adds[df_adds["label"] != "Total"]
            fig_adds.add_trace(go.Bar(
                y=df_adds_no_total["label"],
                x=df_adds_no_total["capacity_gw"],
                orientation="h",
                marker_color=[colors.get(l, "#888") for l in df_adds_no_total["label"]],
                text=df_adds_no_total["capacity_gw"].apply(lambda v: f"{v:.1f} GW"),
                textposition="outside",
            ))
            fig_adds.update_layout(
                height=250, showlegend=False,
                xaxis_title="GW", yaxis_title="",
                margin=dict(l=0, r=0, t=0, b=0),
            )
            st.plotly_chart(fig_adds, use_container_width=True)
            st.caption(
                "63 GW total planned. Solar + battery = 81%. "
                "Only 4.4 GW gas (firm baseload). "
                "DCs need 24/7 power — intermittent additions don't close the gap alone."
            )

    with st.expander("Supply Data Detail"):
        st.dataframe(df_supply, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# Interconnection Queue Bottleneck
# ══════════════════════════════════════════════════════════════
st.header("Interconnection Queue Bottleneck")
st.caption(
    "The US interconnection queue is the key pipeline constraint. "
    "~2,900 GW of capacity is waiting to connect — over 2x total installed US capacity — "
    "but only ~13% of queued projects historically reach operation."
)

queue_path = DATA_DIR / "dc_queue_metrics.csv"

if queue_path.exists():
    df_queue = pd.read_csv(queue_path)
    df_us = df_queue[df_queue["region"] == "United States"].copy()

    col_q1, col_q2, col_q3 = st.columns(3)

    with col_q1:
        st.markdown("**US Queue Depth (GW)**")
        df_depth = df_us[df_us["metric"] == "Queue Depth"].sort_values("year")
        fig_depth = go.Figure()
        fig_depth.add_trace(go.Bar(
            x=df_depth["year"].astype(str), y=df_depth["value"],
            marker_color="#E67E22",
            text=df_depth["value"].apply(lambda v: f"{v:,.0f}"),
            textposition="outside",
            hovertemplate="%{x}: %{y:,.0f} GW<extra></extra>",
        ))
        fig_depth.add_hline(
            y=1290, line_dash="dash", line_color="gray",
            annotation_text="Total US Installed Capacity",
            annotation_position="top left",
        )
        fig_depth.update_layout(
            height=350, yaxis_title="GW",
            showlegend=False,
            xaxis=dict(type="category"),
        )
        st.plotly_chart(fig_depth, use_container_width=True)

    with col_q2:
        st.markdown("**Median Wait Time (Years)**")
        df_wait = df_us[df_us["metric"] == "Avg Wait Time"].sort_values("year")
        fig_wait = go.Figure()
        fig_wait.add_trace(go.Scatter(
            x=df_wait["year"].astype(str), y=df_wait["value"],
            mode="lines+markers+text",
            line=dict(color="#E74C3C", width=3),
            marker=dict(size=10),
            text=df_wait["value"].apply(lambda v: f"{v:.1f}"),
            textposition="top center",
            hovertemplate="%{x}: %{y:.1f} years<extra></extra>",
        ))
        fig_wait.update_layout(
            height=350, yaxis_title="Years",
            showlegend=False,
            xaxis=dict(type="category"),
        )
        st.plotly_chart(fig_wait, use_container_width=True)
        st.caption("Median time from interconnection request to commercial operation, "
                    "by project completion year cohort (LBNL)")

    with col_q3:
        st.markdown("**Queue Completion Rate (%)**")
        df_comp = df_us[df_us["metric"] == "Completion Rate"].sort_values("year")
        # Year here = end of request cohort (e.g. 2019 = requests filed 2000-2019)
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            x=df_comp["year"].apply(lambda y: f"2000–{y}"),
            y=df_comp["value"],
            marker_color="#2ECC71",
            text=df_comp["value"].apply(lambda v: f"{v}%"),
            textposition="outside",
            hovertemplate="%{x} requests: %{y}% completed<extra></extra>",
        ))
        fig_comp.update_layout(
            height=350, yaxis_title="%",
            showlegend=False,
            yaxis_range=[0, 30],
            xaxis=dict(type="category"),
        )
        st.plotly_chart(fig_comp, use_container_width=True)
        st.caption("% of requests filed in cohort that reached commercial operation (LBNL)")

    # Regional highlights — ERCOT & PJM
    df_regional = df_queue[df_queue["region"] != "United States"].copy()
    if not df_regional.empty:
        st.subheader("Regional Highlights")

        col_r1, col_r2 = st.columns(2)

        # ERCOT large load queue explosion
        df_ercot_ll = df_regional[
            (df_regional["region"] == "ERCOT")
            & (df_regional["metric"] == "Large Load Queue")
        ].sort_values("year")
        if not df_ercot_ll.empty:
            with col_r1:
                st.markdown("**ERCOT Large Load Queue (GW)**")
                fig_ercot = go.Figure()
                fig_ercot.add_trace(go.Bar(
                    x=df_ercot_ll["year"].astype(str),
                    y=df_ercot_ll["value"],
                    marker_color="#E74C3C",
                    text=df_ercot_ll["value"].apply(lambda v: f"{v:.0f}"),
                    textposition="outside",
                ))
                fig_ercot.update_layout(
                    height=300, yaxis_title="GW", showlegend=False,
                    xaxis=dict(type="category"),
                )
                st.plotly_chart(fig_ercot, use_container_width=True)
                st.caption("73% of large load requests are data centers. "
                           "Nearly 4x increase in one year.")

        # PJM stats
        df_pjm = df_regional[df_regional["region"] == "PJM Interconnect"]
        if not df_pjm.empty:
            with col_r2:
                st.markdown("**PJM Key Metrics**")
                for _, row in df_pjm.iterrows():
                    unit = row["unit"]
                    val = row["value"]
                    fmt = f"{val:,.0f} {unit}" if val == int(val) else f"{val:.1f} {unit}"
                    st.metric(row["metric"], fmt)
                st.caption("PJM has the longest wait times among US ISOs")

    with st.expander("Full Queue Data"):
        st.dataframe(df_queue, use_container_width=True, hide_index=True)
else:
    st.info("Queue metrics missing (data/reference/dc_queue_metrics.csv).")

# ══════════════════════════════════════════════════════════════
# Hyperscaler Power Sourcing Tracker
# ══════════════════════════════════════════════════════════════
st.header("Hyperscaler Power Sourcing Tracker")
st.caption(
    "How the majors are securing power for their DC buildout — "
    "PPAs, nuclear restarts/SMRs, behind-fence generation. "
    "Contracted capacity vs projected demand shows who's positioned and who's exposed."
)

sourcing_path = DATA_DIR / "dc_power_sourcing.csv"

if sourcing_path.exists():
    df_src = pd.read_csv(sourcing_path)

    # Stacked bar: contracted capacity by source type per company
    df_src["capacity_gw"] = pd.to_numeric(df_src["capacity_gw"], errors="coerce")
    df_chart = df_src.dropna(subset=["capacity_gw"]).copy()

    # Map detailed source_type → display category for chart colours
    def _source_category(st_val: str) -> str:
        s = str(st_val)
        if s.startswith("Renewable PPA") or s.startswith("Clean Energy"):
            return "Renewable / Clean"
        if "SMR" in s or "TerraPower" in s or "Oklo" in s:
            return "Nuclear (SMR / Advanced)"
        if "Restart" in s:
            return "Nuclear (Restart)"
        if "Existing" in s or "Vistra" in s or "Constellation" in s:
            return "Nuclear (Existing)"
        if "Fusion" in s:
            return "Nuclear (Fusion)"
        if "Geothermal" in s:
            return "Geothermal"
        if "Acquisition" in s or "Total Contracted" in s:
            return "Portfolio / Other"
        return "Other"

    df_chart["source_cat"] = df_chart["source_type"].apply(_source_category)

    SOURCE_COLORS = {
        "Renewable / Clean": "#2ECC71",
        "Nuclear (Restart)": "#F39C12",
        "Nuclear (Existing)": "#E67E22",
        "Nuclear (SMR / Advanced)": "#E74C3C",
        "Nuclear (Fusion)": "#D5A6BD",
        "Geothermal": "#1ABC9C",
        "Portfolio / Other": "#3498DB",
        "Other": "#BDC3C7",
    }

    # Categorise by firmness
    firm_statuses = {"Contracted", "PPA", "Actual"}
    df_chart["firmness"] = df_chart["status"].apply(
        lambda s: "Contracted" if s in firm_statuses else "Pipeline"
    )

    # Sum by company and source type
    company_order = ["Microsoft", "Amazon", "Google", "Meta", "Oracle", "CoreWeave", "Apple"]
    df_chart["company"] = pd.Categorical(df_chart["company"], categories=company_order, ordered=True)

    st.markdown("**Contracted & Pipeline Power Capacity by Source (GW)**")
    fig_src = px.bar(
        df_chart.sort_values("company"),
        x="company", y="capacity_gw", color="source_cat",
        pattern_shape="firmness",
        labels={"capacity_gw": "Capacity (GW)", "company": "", "source_cat": "Source"},
        barmode="stack",
        color_discrete_map=SOURCE_COLORS,
        pattern_shape_map={"Contracted": "", "Pipeline": "/"},
        category_orders={"company": company_order},
        hover_data=["source_type", "status", "counterparty", "details"],
    )
    fig_src.update_layout(
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_src, use_container_width=True)

    # Summary table: total contracted vs pipeline per company
    df_summary = df_chart.groupby(["company", "firmness"])["capacity_gw"].sum().unstack(fill_value=0)
    if "Contracted" not in df_summary.columns:
        df_summary["Contracted"] = 0.0
    if "Pipeline" not in df_summary.columns:
        df_summary["Pipeline"] = 0.0
    df_summary["Total"] = df_summary["Contracted"] + df_summary["Pipeline"]
    df_summary = df_summary.reset_index()
    df_summary = df_summary.sort_values("Total", ascending=False)

    st.subheader("Capacity Summary")
    st.dataframe(
        df_summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Contracted": st.column_config.NumberColumn(format="%.1f GW"),
            "Pipeline": st.column_config.NumberColumn(format="%.1f GW"),
            "Total": st.column_config.NumberColumn(format="%.1f GW"),
        },
    )

    # Detail table
    with st.expander("Full Sourcing Detail"):
        display_cols = ["company", "source_type", "capacity_gw", "status",
                        "counterparty", "announced_date", "details", "reference"]
        display_cols = [c for c in display_cols if c in df_src.columns]
        st.dataframe(df_src[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("Power sourcing data missing (data/reference/dc_power_sourcing.csv).")
