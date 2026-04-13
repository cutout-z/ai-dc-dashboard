"""AI & DC CAPEX — annual + quarterly spending with forward guidance overlay."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

DB_PATH = st.session_state["db_path"]
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"

COMPANY_COLORS = {
    "Microsoft": "#00A4EF",
    "Alphabet": "#EA4335",
    "Amazon": "#FF9900",
    "Meta": "#1877F2",
    "Oracle": "#C74634",
    "CoreWeave": "#00BFA5",
    "Apple": "#A3AAAE",
}

# Companies with non-December fiscal year ends
FYE_NOTES = {
    "Microsoft": "FYE Jun",
    "Oracle": "FYE May",
    "Apple": "FYE Sep",
}

ALL_COMPANIES = list(COMPANY_COLORS.keys())

st.title("AI & DC CAPEX Tracker")

conn = sqlite3.connect(DB_PATH)

# ── Company filter ──────────────────────────────────────────
selected = st.multiselect(
    "Companies",
    ALL_COMPANIES,
    default=ALL_COMPANIES,
    key="capex_companies",
)
if not selected:
    st.warning("Select at least one company.")
    st.stop()

# Build SQL IN clause from company names
selected_sql = ", ".join(f"'{c}'" for c in selected)

# ══════════════════════════════════════════════════════════════
# Annual CAPEX with Guidance Overlay
# ══════════════════════════════════════════════════════════════
st.subheader("Annual CAPEX vs Forward Guidance")

# FYE footnote
fye_flags = [f"{co} ({note})" for co, note in FYE_NOTES.items() if co in selected]
if fye_flags:
    st.caption("**Non-calendar FYE:** " + " · ".join(fye_flags))

try:
    df_annual = pd.read_sql(
        f"""
        SELECT ticker, company, period, value as capex_usd
        FROM quarterly_financials
        WHERE metric = 'capex' AND frequency = 'annual'
          AND company IN ({selected_sql})
        ORDER BY period
        """,
        conn,
    )
except Exception:
    df_annual = pd.DataFrame()

if not df_annual.empty:
    df_annual["capex_bn"] = df_annual["capex_usd"] / 1e9
    df_annual["period"] = pd.to_datetime(df_annual["period"])
    df_annual["year"] = df_annual["period"].dt.year

    fig_annual = go.Figure()

    for company in selected:
        color = COMPANY_COLORS.get(company, "#888")
        mask = df_annual["company"] == company
        df_c = df_annual[mask].sort_values("year")
        if df_c.empty:
            continue
        fig_annual.add_trace(go.Bar(
            x=df_c["year"],
            y=df_c["capex_bn"],
            name=company,
            marker_color=color,
        ))

    # Guidance overlay
    guidance_path = DATA_DIR / "capex_guidance.csv"
    if guidance_path.exists():
        df_guide = pd.read_csv(guidance_path)
        df_guide = df_guide[df_guide["guidance_usd_b"].notna()]
        df_guide = df_guide[df_guide["company"].isin(selected)]

        if not df_guide.empty:
            df_guide["year"] = df_guide["fiscal_year"].str.extract(r"(\d{4})").astype(int)
            guide_by_year = df_guide.groupby("year")["guidance_usd_b"].sum().reset_index()

            fig_annual.add_trace(go.Scatter(
                x=guide_by_year["year"],
                y=guide_by_year["guidance_usd_b"],
                name="Combined Guidance",
                mode="markers+lines",
                marker=dict(size=14, symbol="diamond", color="white",
                            line=dict(width=2, color="red")),
                line=dict(dash="dash", color="red", width=2),
            ))


    fig_annual.update_layout(
        barmode="stack",
        height=500,
        yaxis_title="CAPEX ($B)",
        xaxis_title="Year",
        xaxis=dict(dtick=1),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_annual, use_container_width=True)

    # Guidance detail + history expander
    if guidance_path.exists():
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            with st.expander("Current Guidance"):
                df_gd = pd.read_csv(guidance_path)
                df_gd = df_gd[df_gd["guidance_usd_b"].notna() & df_gd["company"].isin(selected)]
                display_cols = ["company", "fiscal_year", "fy_end_month",
                                "guidance_usd_b", "guidance_low", "guidance_high",
                                "prior_guidance_usd_b", "guidance_date", "notes"]
                display_cols = [c for c in display_cols if c in df_gd.columns]
                st.dataframe(df_gd[display_cols], use_container_width=True, hide_index=True)

        history_path = DATA_DIR / "capex_guidance_history.csv"
        with col_g2:
            if history_path.exists():
                with st.expander("Guidance Revision History"):
                    df_hist = pd.read_csv(history_path)
                    df_hist = df_hist[df_hist["company"].isin(selected)]
                    df_hist = df_hist.sort_values(
                        ["company", "fiscal_year", "announced_date"]
                    )
                    hist_cols = ["company", "fiscal_year", "guidance_usd_b",
                                 "guidance_low", "guidance_high",
                                 "announced_date", "source", "notes"]
                    hist_cols = [c for c in hist_cols if c in df_hist.columns]
                    st.dataframe(df_hist[hist_cols], use_container_width=True,
                                 hide_index=True)
else:
    st.warning("No annual CAPEX data. Run: python scripts/fetch_financials.py")

# ══════════════════════════════════════════════════════════════
# Quarterly CAPEX
# ══════════════════════════════════════════════════════════════
st.subheader("Quarterly CAPEX")

df_capex = pd.read_sql(
    f"""
    SELECT ticker, company, period, capex_usd
    FROM v_hyperscaler_capex
    WHERE company IN ({selected_sql})
    ORDER BY period
    """,
    conn,
)

if not df_capex.empty:
    df_capex["capex_bn"] = df_capex["capex_usd"] / 1e9
    df_capex["period"] = pd.to_datetime(df_capex["period"])
    df_capex["quarter"] = df_capex["period"].dt.to_period("Q").astype(str)
    df_capex = df_capex.sort_values("period")

    # Drop trailing quarter if incomplete (e.g. Oracle reports one quarter ahead)
    co_per_q = df_capex.groupby("quarter")["company"].nunique()
    last_q = sorted(co_per_q.index)[-1]
    if co_per_q[last_q] < co_per_q.median():
        df_capex = df_capex[df_capex["quarter"] != last_q]

    quarter_order = sorted(df_capex["quarter"].unique())

    col1, col2 = st.columns(2)

    with col1:
        fig_q = px.bar(
            df_capex, x="quarter", y="capex_bn", color="company",
            title="Quarterly CAPEX ($B)",
            labels={"capex_bn": "CAPEX ($B)", "quarter": "Quarter"},
            barmode="stack",
            color_discrete_map=COMPANY_COLORS,
            category_orders={"quarter": quarter_order},
        )
        fig_q.update_layout(height=450, xaxis_type="category",
                            xaxis_tickangle=-45,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                        title_text=""))
        st.plotly_chart(fig_q, use_container_width=True)

    with col2:
        fig_ind = px.line(
            df_capex, x="quarter", y="capex_bn", color="company",
            title="Individual CAPEX Trends",
            labels={"capex_bn": "$B", "quarter": "Quarter"},
            color_discrete_map=COMPANY_COLORS,
            category_orders={"quarter": quarter_order},
        )
        fig_ind.update_layout(height=450, xaxis_type="category",
                              xaxis_tickangle=-45,
                              legend=dict(title_text=""))
        st.plotly_chart(fig_ind, use_container_width=True)

    # QoQ growth
    df_total = df_capex.groupby("quarter")["capex_bn"].sum().reset_index()
    df_total = df_total.sort_values("quarter").reset_index(drop=True)
    df_total["qoq_pct"] = df_total["capex_bn"].pct_change() * 100

    fig_total = go.Figure()
    fig_total.add_trace(go.Bar(
        x=df_total["quarter"], y=df_total["capex_bn"],
        name="Total CAPEX", marker_color="#4A90D9"
    ))
    fig_total.add_trace(go.Scatter(
        x=df_total["quarter"], y=df_total["qoq_pct"],
        name="QoQ %", yaxis="y2", line=dict(color="red", width=2),
        mode="lines+markers"
    ))
    fig_total.update_layout(
        title="Aggregate CAPEX + QoQ Growth",
        yaxis=dict(title="CAPEX ($B)"),
        yaxis2=dict(title="QoQ %", overlaying="y", side="right"),
        height=350, showlegend=False, xaxis_type="category",
        xaxis_tickangle=-45,
    )
    st.plotly_chart(fig_total, use_container_width=True)
else:
    st.warning("No quarterly CAPEX data. Run: python scripts/fetch_financials.py")

conn.close()
