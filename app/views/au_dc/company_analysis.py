"""Company Analysis — Operator profiles, market share, financials."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

from app.lib.au_dc_charts import COLOUR_PALETTE, CHART_LAYOUT, price_history_chart

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

# Financial data
quotes_path = DATA_DIR / "financials_quotes.parquet"
history_path = DATA_DIR / "financials_history.parquet"
fin_quotes = pd.read_parquet(quotes_path) if quotes_path.exists() else None
fin_history = pd.read_parquet(history_path) if history_path.exists() else None

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

col1, col2 = st.columns(2)

with col1:
    fig = px.pie(
        market_share, values="value", names=group_col,
        title=f"Market Share by {group_by} ({risk_view})", hole=0.4,
        color=group_col, color_discrete_map=COLOUR_PALETTE,
    )
    fig.update_layout(**CHART_LAYOUT)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig = px.bar(
        market_share.sort_values("value", ascending=True).tail(15),
        x="value", y=group_col, orientation="h",
        title=f"{share_basis} by {group_by}",
        labels={"value": share_basis, group_col: ""},
        color_discrete_sequence=["#2563eb"],
    )
    fig.update_layout(**CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

st.dataframe(
    market_share.rename(columns={group_col: group_by, "value": share_basis, "share_pct": "Share %"}),
    use_container_width=True, hide_index=True,
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
                               "profit_margin", "debt_to_equity", "beta"]].copy()
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
            "profit_margin": st.column_config.NumberColumn("Margin", format="%.1%"),
            "debt_to_equity": st.column_config.NumberColumn("D/E %", format="%.0f"),
            "beta": st.column_config.NumberColumn("Beta", format="%.2f"),
        },
    )

    if fin_history is not None:
        ticker_names = dict(zip(fin_quotes["ticker"], fin_quotes["name"]))
        fig = price_history_chart(fin_history, ticker_names)
        fig.update_layout(title="ASX DC Operators — Share Price (12 Months)")
        st.plotly_chart(fig, use_container_width=True)
