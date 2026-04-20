"""Company Analysis — Operator profiles, market share, financials."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

from app.lib.au_dc_charts import COLOUR_PALETTE, CHART_LAYOUT, price_history_chart
from app.lib.au_dc_financials import fetch_asx_dc_quotes, fetch_asx_dc_history

_AU_DC_DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc"
DATA_DIR = _AU_DC_DATA / "processed"
REF_DIR = _AU_DC_DATA / "reference"

st.title("Company Analysis")

projects_path = DATA_DIR / "projects.parquet"
if not projects_path.exists():
    st.error("Project database not found.")
    st.stop()

projects = pd.read_parquet(projects_path)
operators_ref = pd.read_csv(REF_DIR / "operator_types.csv") if (REF_DIR / "operator_types.csv").exists() else None

# Financial data — live, 5-minute cache
_fin_quotes = fetch_asx_dc_quotes()
_fin_history = fetch_asx_dc_history()
fin_quotes = _fin_quotes if not _fin_quotes.empty else None
fin_history = _fin_history if not _fin_history.empty else None

# --- Controls ---
st.sidebar.header("Controls")
risk_view = st.sidebar.radio("Capacity View", ["Unrisked", "Risked"], index=0, key="au_co_risk")
mw_col = "risked_mw" if risk_view == "Risked" else "facility_mw"
group_by = st.sidebar.radio("Group By", ["Operator", "Parent Company", "Operator Type"], index=0, key="au_co_group")
group_col = {"Operator": "operator", "Parent Company": "parent_company", "Operator Type": "operator_type"}[group_by]

# ========================================
# Market Share
# ========================================
st.markdown("### Market Share")

share_basis = st.radio("Share Basis", ["Capacity (MW)", "Number of Projects"], horizontal=True, key="au_co_basis")
val_col = mw_col if share_basis == "Capacity (MW)" else "project_name"
agg_func = "sum" if share_basis == "Capacity (MW)" else "count"

market_share = (
    projects.groupby(group_col).agg(value=(val_col, agg_func)).reset_index()
    .sort_values("value", ascending=False)
)
market_share["share_pct"] = (market_share["value"] / market_share["value"].sum() * 100).round(1)

STAGE_COLOURS = {
    "Operating": "#16a34a",
    "Under Construction": "#f59e0b",
    "Announced": "#2563eb",
}
stage_map = {
    "Operating": "Operating",
    "Under Construction": "Under Construction",
    "Proposed": "Announced",
    "Approved": "Announced",
}
projects_stage = projects.copy()
projects_stage["stage"] = projects_stage["status"].map(stage_map).fillna("Announced")

col1, col2 = st.columns(2)

with col1:
    fig = px.pie(
        market_share, values="value", names=group_col,
        title=f"Market Share by {group_by} ({risk_view})", hole=0.4,
        color=group_col, color_discrete_map=COLOUR_PALETTE,
    )
    fig.update_layout(**CHART_LAYOUT, showlegend=False)
    fig.update_traces(textposition="inside", textinfo="percent+label", insidetextorientation="radial")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    top_operators = market_share.sort_values("value", ascending=True).tail(15)[group_col].tolist()

    stage_share = (
        projects_stage[projects_stage[group_col].isin(top_operators)]
        .groupby([group_col, "stage"])
        .agg(value=(val_col, agg_func))
        .reset_index()
    )

    # Add per-operator source attribution for hover tooltip
    if "source" in projects_stage.columns:
        src_map = (
            projects_stage[projects_stage[group_col].isin(top_operators)]
            .groupby(group_col)["source"]
            .apply(lambda s: "<br>".join(
                f"· {v}" for v in sorted(s.dropna().astype(str).unique()) if v.strip()
            ))
        )
        stage_share["Sources"] = stage_share[group_col].map(src_map).fillna("—")
    else:
        stage_share["Sources"] = "—"

    fig = px.bar(
        stage_share,
        x="value", y=group_col, orientation="h", barmode="stack",
        color="stage",
        title=f"{share_basis} by {group_by}",
        labels={"value": share_basis, group_col: "", "stage": "Stage"},
        color_discrete_map=STAGE_COLOURS,
        category_orders={
            group_col: top_operators,
            "stage": ["Announced", "Under Construction", "Operating"],
        },
        custom_data=["Sources"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{y}</b> — %{fullData.name}<br>"
            "%{x:,.0f} MW<br>"
            "<br><i>Sources:</i><br>%{customdata[0]}"
            "<extra></extra>"
        )
    )
    fig.update_layout(
        **{**CHART_LAYOUT, "margin": dict(l=40, r=20, t=40, b=100)},
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

# Stage-breakdown table
stage_pivot = (
    projects_stage
    .groupby([group_col, "stage"])
    .agg(value=(val_col, agg_func))
    .reset_index()
    .pivot(index=group_col, columns="stage", values="value")
    .fillna(0)
    .reset_index()
)
for stage in ["Operating", "Under Construction", "Announced"]:
    if stage not in stage_pivot.columns:
        stage_pivot[stage] = 0

total_op = stage_pivot["Operating"].sum()
total_uc = stage_pivot["Under Construction"].sum()
total_ann = stage_pivot["Announced"].sum()
grand_total = total_op + total_uc + total_ann

stage_pivot["Total"] = stage_pivot["Operating"] + stage_pivot["Under Construction"] + stage_pivot["Announced"]
stage_pivot["Op %"] = (stage_pivot["Operating"] / max(total_op, 1e-9) * 100).round(1)
stage_pivot["Op+UC %"] = (
    (stage_pivot["Operating"] + stage_pivot["Under Construction"]) / max(total_op + total_uc, 1e-9) * 100
).round(1)
stage_pivot["Total %"] = (stage_pivot["Total"] / max(grand_total, 1e-9) * 100).round(1)
stage_pivot = stage_pivot.sort_values("Total", ascending=False).rename(columns={group_col: group_by})

col_label = "MW" if share_basis == "Capacity (MW)" else "Projects"
st.dataframe(
    stage_pivot[[group_by, "Operating", "Under Construction", "Announced", "Total", "Op %", "Op+UC %", "Total %"]],
    use_container_width=True, hide_index=True,
    column_config={
        group_by: group_by,
        "Operating": st.column_config.NumberColumn(f"Operating ({col_label})", format="%d"),
        "Under Construction": st.column_config.NumberColumn(f"Under Constr. ({col_label})", format="%d"),
        "Announced": st.column_config.NumberColumn(f"Announced ({col_label})", format="%d"),
        "Total": st.column_config.NumberColumn(f"Total ({col_label})", format="%d"),
        "Op %": st.column_config.NumberColumn("Op Share %", format="%.1f"),
        "Op+UC %": st.column_config.NumberColumn("Op+UC Share %", format="%.1f"),
        "Total %": st.column_config.NumberColumn("Total Share %", format="%.1f"),
    },
)

with st.expander("Data sources & methodology"):
    st.markdown(
        """
**Capacity basis**

- **Unrisked** — total announced `facility_mw` across all project stages (Operating, Under Construction, Proposed/Approved).
  Represents maximum potential capacity if all projects are delivered as disclosed.
- **Risked** — probability-weighted capacity. Each project is discounted by stage
  (e.g. Proposed projects carry a lower weight than Operating or Under Construction).

**What "Capacity (MW)" means**

Figures represent **total facility power draw** (IT load + cooling + ancillaries), as disclosed by operators.
Where only critical IT load is available, facility MW is estimated using a standard PUE conversion.
This is *not* contracted or committed capacity — it is the stated design capacity of each facility.

**Data sources**

Project data is manually curated from public disclosures including ASX/NZX announcements,
company investor relations websites, state planning portals (e.g. NSW SSD), and DCI/Cushman & Wakefield
market reports. Data is updated periodically and may not reflect the latest announcements.
        """
    )

st.markdown("---")

# ========================================
# Company Profiles
# ========================================
st.markdown("### Company Profile")

operators_list = sorted(projects["operator"].unique().tolist())
selected_op = st.selectbox("Select Operator", operators_list, key="au_co_op")

op_projects = projects[projects["operator"] == selected_op]

p1, p2, p3, p4 = st.columns(4)
with p1:
    st.metric("Data Centres", len(op_projects))
with p2:
    st.metric("Total Capacity", f"{op_projects['facility_mw'].sum():,.0f} MW")
with p3:
    operating_mw = op_projects[op_projects["status"] == "Operating"]["facility_mw"].sum()
    st.metric("Operating", f"{operating_mw:,.0f} MW")
with p4:
    pipeline_mw = op_projects[op_projects["status"] != "Operating"]["facility_mw"].sum()
    st.metric("Pipeline", f"{pipeline_mw:,.0f} MW")

if operators_ref is not None:
    op_info = operators_ref[operators_ref["operator"] == selected_op]
    if not op_info.empty:
        info = op_info.iloc[0]
        cols = st.columns(4)
        with cols[0]:
            st.markdown(f"**Type:** {info.get('operator_type', 'N/A')}")
        with cols[1]:
            st.markdown(f"**Parent:** {info.get('parent_company', 'N/A')}")
        with cols[2]:
            listed = "Yes" if info.get("listed") else "No"
            st.markdown(f"**Listed:** {listed}")
        with cols[3]:
            st.markdown(f"**Ticker:** {info.get('ticker', 'N/A')}")

st.markdown("#### Projects")
display_cols = ["project_name", "nem_region", "state", "suburb", "status",
                "facility_mw", "critical_it_mw", "startup_year", "capex_aud_m",
                "workload_type", "power_strategy"]
available = [c for c in display_cols if c in op_projects.columns]
st.dataframe(
    op_projects[available].sort_values("facility_mw", ascending=False),
    use_container_width=True, hide_index=True,
    column_config={
        "project_name": "Project", "nem_region": "Region", "state": "State",
        "suburb": "Suburb", "status": "Status",
        "facility_mw": st.column_config.NumberColumn("Facility MW", format="%d"),
        "critical_it_mw": st.column_config.NumberColumn("IT MW", format="%d"),
        "startup_year": st.column_config.NumberColumn("Startup", format="%d"),
        "capex_aud_m": st.column_config.NumberColumn("CAPEX (A$M)", format="%d"),
        "workload_type": "Workload", "power_strategy": "Power Strategy",
    },
)

fig = px.bar(
    op_projects.groupby("status")["facility_mw"].sum().reset_index(),
    x="status", y="facility_mw", color="status", color_discrete_map=COLOUR_PALETTE,
    title=f"{selected_op} — Capacity by Status",
    labels={"facility_mw": "Capacity (MW)", "status": ""},
)
fig.update_layout(**CHART_LAYOUT, showlegend=False)
st.plotly_chart(fig, use_container_width=True)

# Financial data for listed operator
if fin_quotes is not None and operators_ref is not None:
    op_info = operators_ref[operators_ref["operator"] == selected_op]
    if not op_info.empty:
        ticker = op_info.iloc[0].get("ticker", "")
        if ticker and ticker in fin_quotes["ticker"].values:
            st.markdown("---")
            st.markdown("#### Financials")
            q = fin_quotes[fin_quotes["ticker"] == ticker].iloc[0]

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                mc = q.get("market_cap")
                st.metric("Market Cap", f"A${mc/1e9:.1f}B" if pd.notna(mc) and mc > 0 else "N/A")
            with f2:
                pe = q.get("pe_ratio")
                st.metric("P/E (TTM)", f"{pe:.1f}" if pd.notna(pe) else "N/A")
            with f3:
                ev = q.get("ev_ebitda")
                st.metric("EV/EBITDA", f"{ev:.1f}x" if pd.notna(ev) else "N/A")
            with f4:
                beta = q.get("beta")
                st.metric("Beta", f"{beta:.2f}" if pd.notna(beta) else "N/A")

            f5, f6, f7, f8 = st.columns(4)
            with f5:
                rg = q.get("revenue_growth")
                st.metric("Revenue Growth", f"{rg:.1%}" if pd.notna(rg) else "N/A")
            with f6:
                pm = q.get("profit_margin")
                st.metric("Profit Margin", f"{pm:.1%}" if pd.notna(pm) else "N/A")
            with f7:
                dte = q.get("debt_to_equity")
                st.metric("Debt/Equity", f"{dte:.0f}%" if pd.notna(dte) else "N/A")
            with f8:
                dy = q.get("dividend_yield")
                st.metric("Div Yield", f"{dy:.1%}" if pd.notna(dy) and dy > 0 else "N/A")

            if fin_history is not None and ticker in fin_history["ticker"].values:
                ticker_hist = fin_history[fin_history["ticker"] == ticker]
                fig = price_history_chart(ticker_hist, {ticker: q.get("name", ticker)})
                st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========================================
# ASX DC Operators Comparison
# ========================================
if fin_quotes is not None and len(fin_quotes) > 1:
    st.markdown("### ASX DC Operators — Financial Comparison")

    display_fin = fin_quotes[["ticker", "name", "price", "market_cap", "pe_ratio",
                               "forward_pe", "ev_ebitda", "revenue_growth",
                               "debt_to_equity", "beta"]].copy()
    display_fin["market_cap"] = (display_fin["market_cap"] / 1e9).round(1)

    st.dataframe(
        display_fin, use_container_width=True, hide_index=True,
        column_config={
            "ticker": "Ticker", "name": "Company",
            "price": st.column_config.NumberColumn("Price (A$)", format="%.2f"),
            "market_cap": st.column_config.NumberColumn("MCap (A$B)", format="%.1f"),
            "pe_ratio": st.column_config.NumberColumn("P/E", format="%.1f"),
            "forward_pe": st.column_config.NumberColumn("Fwd P/E", format="%.1f"),
            "ev_ebitda": st.column_config.NumberColumn("EV/EBITDA", format="%.1f"),
            "revenue_growth": st.column_config.NumberColumn("Rev Growth", format="%.1%"),
            "debt_to_equity": st.column_config.NumberColumn("D/E %", format="%.0f"),
            "beta": st.column_config.NumberColumn("Beta", format="%.2f"),
        },
    )

    if fin_history is not None:
        ticker_names = dict(zip(fin_quotes["ticker"], fin_quotes["name"]))
        fig = price_history_chart(fin_history, ticker_names)
        fig.update_layout(
            title="ASX DC Operators — Share Price (12 Months)",
            **{**CHART_LAYOUT, "margin": dict(l=40, r=20, t=40, b=80)},
            legend=dict(orientation="h", yanchor="top", y=-0.15, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)
