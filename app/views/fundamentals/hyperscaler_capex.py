"""AI & DC CAPEX — annual + quarterly spending with forward guidance overlay."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import calendar
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
                marker=dict(size=14, symbol="diamond",
                            color=st.session_state["marker_line_color"],
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
# Forecast Year Bridge
# ══════════════════════════════════════════════════════════════
st.subheader("Forecast Year Bridge")
st.caption(
    "Quarterly actuals filling toward full-year CAPEX guidance "
    "for each company's current forecast year"
)

guidance_path_b = DATA_DIR / "capex_guidance.csv"
history_path_b = DATA_DIR / "capex_guidance_history.csv"

if guidance_path_b.exists():
    df_guide_b = pd.read_csv(guidance_path_b)
    df_guide_b = df_guide_b[
        df_guide_b["guidance_usd_b"].notna() & df_guide_b["company"].isin(selected)
    ]
    df_guide_b["year_num"] = (
        df_guide_b["fiscal_year"].str.extract(r"(\d{4})").astype(int)
    )

    # Forward-looking fiscal year per company (max year)
    idx_b = df_guide_b.groupby("company")["year_num"].idxmax()
    fwd_guide = df_guide_b.loc[idx_b].copy().sort_values("company")

    # Fresh quarterly query (unfiltered — bridge needs all available quarters)
    df_q_bridge = pd.read_sql(
        f"""SELECT company, period, capex_usd
            FROM v_hyperscaler_capex
            WHERE company IN ({selected_sql})
            ORDER BY period""",
        conn,
    )
    df_q_bridge["period"] = pd.to_datetime(df_q_bridge["period"])
    df_q_bridge["capex_bn"] = df_q_bridge["capex_usd"] / 1e9

    # Revision history
    df_hist_b = pd.DataFrame()
    if history_path_b.exists():
        df_hist_b = pd.read_csv(history_path_b)
        df_hist_b = df_hist_b[df_hist_b["company"].isin(selected)]

    Q_COLORS = {1: "#1B4F72", 2: "#2E86C1", 3: "#5DADE2", 4: "#85C1E9"}
    REMAIN_CLR = "rgba(100,100,100,0.25)"
    _shown = set()

    fig_bridge = go.Figure()
    annots = []

    for _, gr in fwd_guide.iterrows():
        co = gr["company"]
        fy_m = int(gr["fy_end_month"])
        yr = int(gr["year_num"])
        g_bn = gr["guidance_usd_b"]
        fy_lbl = gr["fiscal_year"]

        # Fiscal year boundaries
        fy_end_day = calendar.monthrange(yr, fy_m)[1]
        fy_end_dt = pd.Timestamp(yr, fy_m, fy_end_day)
        fy_start_dt = (
            pd.Timestamp(yr, 1, 1)
            if fy_m == 12
            else pd.Timestamp(yr - 1, fy_m + 1, 1)
        )

        # Actuals falling within this fiscal year
        m = (
            (df_q_bridge["company"] == co)
            & (df_q_bridge["period"] >= fy_start_dt)
            & (df_q_bridge["period"] <= fy_end_dt)
        )
        df_fy = df_q_bridge[m].sort_values("period")

        x_lbl = f"{co} ({fy_lbl})"
        cumul = 0.0

        for i, (_, qr) in enumerate(df_fy.iterrows(), start=1):
            qn = min(i, 4)
            lg = f"Q{qn}"
            show = lg not in _shown
            if show:
                _shown.add(lg)
            fig_bridge.add_trace(
                go.Bar(
                    x=[x_lbl],
                    y=[qr["capex_bn"]],
                    name=lg,
                    legendgroup=lg,
                    marker_color=Q_COLORS[qn],
                    showlegend=show,
                    hovertemplate=(
                        f"Q{qn}: ${qr['capex_bn']:.1f}B<extra>{co}</extra>"
                    ),
                )
            )
            cumul += qr["capex_bn"]

        # Remaining to guidance
        remain = max(0.0, g_bn - cumul)
        show_r = "Remaining" not in _shown
        if show_r:
            _shown.add("Remaining")
        fig_bridge.add_trace(
            go.Bar(
                x=[x_lbl],
                y=[remain],
                name="Remaining",
                legendgroup="Remaining",
                marker=dict(color=REMAIN_CLR, line=dict(color="#888", width=1)),
                showlegend=show_r,
                hovertemplate=f"Remaining: ${remain:.1f}B<extra>{co}</extra>",
            )
        )

        # Guidance range (low–high) as error bars
        g_lo = gr["guidance_low"]
        g_hi = gr["guidance_high"]
        if pd.notna(g_lo) and pd.notna(g_hi):
            fig_bridge.add_trace(
                go.Scatter(
                    x=[x_lbl],
                    y=[g_bn],
                    error_y=dict(
                        type="data",
                        symmetric=False,
                        array=[g_hi - g_bn],
                        arrayminus=[g_bn - g_lo],
                        color=st.session_state["error_bar_color"],
                        thickness=2,
                        width=15,
                    ),
                    mode="markers",
                    marker=dict(size=1, color="rgba(0,0,0,0)"),
                    showlegend=False,
                    hovertemplate=(
                        f"Range: ${g_lo:.0f}B – ${g_hi:.0f}B"
                        f"<extra>{co}</extra>"
                    ),
                )
            )

        # Prior guidance revisions (diamond markers)
        if not df_hist_b.empty:
            rev_m = (df_hist_b["company"] == co) & (
                df_hist_b["fiscal_year"] == fy_lbl
            )
            df_rev = df_hist_b[rev_m].sort_values("announced_date")
            if len(df_rev) > 1:
                for _, rr in df_rev.iloc[:-1].iterrows():
                    show_pg = "Prior Guidance" not in _shown
                    if show_pg:
                        _shown.add("Prior Guidance")
                    notes_txt = rr.get("notes", "") or ""
                    fig_bridge.add_trace(
                        go.Scatter(
                            x=[x_lbl],
                            y=[rr["guidance_usd_b"]],
                            mode="markers",
                            marker=dict(
                                size=14,
                                symbol="diamond",
                                color="rgba(255,80,80,0.9)",
                                line=dict(width=1.5, color=st.session_state["marker_line_color"]),
                            ),
                            name="Prior Guidance",
                            legendgroup="Prior Guidance",
                            showlegend=show_pg,
                            hovertemplate=(
                                f"Prior: ${rr['guidance_usd_b']:.0f}B"
                                f"<br>{rr['announced_date']}"
                                f"<br>{notes_txt}"
                                f"<extra>{co}</extra>"
                            ),
                        )
                    )

        # Annotations: guidance total on top, fill % inside actuals
        annots.append(
            dict(
                x=x_lbl,
                y=g_bn,
                text=f"${g_bn:.0f}B",
                showarrow=False,
                yshift=14,
                font=dict(size=11, color=st.session_state["annotation_color"]),
            )
        )
        if cumul > 0:
            pct = cumul / g_bn * 100
            annots.append(
                dict(
                    x=x_lbl,
                    y=cumul / 2,
                    text=f"{pct:.0f}%",
                    showarrow=False,
                    font=dict(size=12, color=st.session_state["annotation_color"]),
                )
            )

    fig_bridge.update_layout(
        barmode="stack",
        height=500,
        yaxis_title="CAPEX ($B)",
        xaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        annotations=annots,
    )
    st.plotly_chart(fig_bridge, use_container_width=True)

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

else:
    st.warning("No quarterly CAPEX data. Run: python scripts/fetch_financials.py")

conn.close()
