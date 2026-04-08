"""Bubble Tracker — Key indicators for AI bubble risk assessment."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="Bubble Tracker", layout="wide")

DB_PATH = st.session_state.get("db_path", str(Path(__file__).parent.parent.parent / "data" / "db" / "ai_research.db"))
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "reference"

COMPANY_COLORS = {
    "Microsoft": "#00A4EF",
    "Alphabet": "#EA4335",
    "Amazon": "#FF9900",
    "Meta": "#1877F2",
}

st.title("Bubble Tracker")

conn = sqlite3.connect(DB_PATH)

# ══════════════════════════════════════════════
# 1. HYPERSCALER CAPEX
# ══════════════════════════════════════════════
st.header("Hyperscaler CAPEX")

# --- 1a. Annual CAPEX with Guidance Overlay ---
st.subheader("Annual CAPEX vs Forward Guidance")

# Try to load annual data; fall back to computing from quarterly
try:
    df_annual = pd.read_sql("""
        SELECT ticker, company, period, value as capex_usd
        FROM quarterly_financials
        WHERE metric = 'capex' AND frequency = 'annual'
          AND ticker IN ('MSFT', 'GOOGL', 'AMZN', 'META')
        ORDER BY period
    """, conn)
except Exception:
    df_annual = pd.DataFrame()

if not df_annual.empty:
    df_annual["capex_bn"] = df_annual["capex_usd"] / 1e9
    df_annual["period"] = pd.to_datetime(df_annual["period"])
    df_annual["year"] = df_annual["period"].dt.year

    # Stacked bar — annual actuals
    fig_annual = go.Figure()

    for company, color in COMPANY_COLORS.items():
        mask = df_annual["company"] == company
        df_c = df_annual[mask].sort_values("year")
        fig_annual.add_trace(go.Bar(
            x=df_c["year"],
            y=df_c["capex_bn"],
            name=company,
            marker_color=color,
        ))

    # Load guidance overlay
    guidance_path = DATA_DIR / "capex_guidance.csv"
    if guidance_path.exists():
        df_guide = pd.read_csv(guidance_path)
        df_guide = df_guide[df_guide["guidance_usd_b"].notna()]

        if not df_guide.empty:
            # Extract year from fiscal_year (e.g. "FY2025" -> 2025, "CY2025" -> 2025)
            df_guide["year"] = df_guide["fiscal_year"].str.extract(r"(\d{4})").astype(int)

            # Aggregate guidance per year
            guide_by_year = df_guide.groupby("year")["guidance_usd_b"].sum().reset_index()

            fig_annual.add_trace(go.Scatter(
                x=guide_by_year["year"],
                y=guide_by_year["guidance_usd_b"],
                name="Combined Guidance",
                mode="markers+lines",
                marker=dict(size=14, symbol="diamond", color="white", line=dict(width=2, color="red")),
                line=dict(dash="dash", color="red", width=2),
            ))

            # Add revision annotations
            revised = df_guide[df_guide["prior_guidance_usd_b"].notna()]
            for _, row in revised.iterrows():
                fig_annual.add_annotation(
                    x=row["year"],
                    y=row["guidance_usd_b"],
                    text=f"{row['company']}: ${row['prior_guidance_usd_b']:.0f}B→${row['guidance_usd_b']:.0f}B",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=0.8,
                    ax=0,
                    ay=-35,
                    font=dict(size=9, color="red"),
                )

    fig_annual.update_layout(
        barmode="stack",
        height=500,
        yaxis_title="CAPEX ($B)",
        xaxis_title="Year",
        xaxis=dict(dtick=1),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_annual, use_container_width=True)

    # Guidance detail table
    if guidance_path.exists():
        with st.expander("Guidance Detail"):
            df_guide_display = pd.read_csv(guidance_path)
            df_guide_display = df_guide_display[df_guide_display["guidance_usd_b"].notna()]
            st.dataframe(
                df_guide_display[["company", "fiscal_year", "guidance_usd_b", "prior_guidance_usd_b", "guidance_date", "notes"]],
                use_container_width=True,
                hide_index=True,
            )
else:
    st.warning("No annual CAPEX data. Run: python scripts/fetch_financials.py")

# --- 1b. Quarterly CAPEX — Progress vs Guidance Pace ---
st.subheader("Quarterly CAPEX")

df_capex = pd.read_sql("""
    SELECT ticker, company, period, capex_usd
    FROM v_hyperscaler_capex
    ORDER BY period
""", conn)

if not df_capex.empty:
    df_capex["capex_bn"] = df_capex["capex_usd"] / 1e9
    df_capex["period"] = pd.to_datetime(df_capex["period"])
    # Convert period-end dates to quarter labels (e.g. 2025-03-31 → "Q1 2025")
    df_capex["quarter"] = df_capex["period"].dt.to_period("Q").astype(str)
    df_capex = df_capex.sort_values("period")

    col1, col2 = st.columns(2)

    with col1:
        fig_q = px.bar(
            df_capex, x="quarter", y="capex_bn", color="company",
            title="Quarterly CAPEX ($B)",
            labels={"capex_bn": "CAPEX ($B)", "quarter": "Quarter"},
            barmode="stack",
            color_discrete_map=COMPANY_COLORS,
        )
        fig_q.update_layout(height=400, xaxis_type="category",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_q, use_container_width=True)

    with col2:
        fig_ind = px.line(
            df_capex, x="quarter", y="capex_bn", color="company",
            title="Individual CAPEX Trends",
            labels={"capex_bn": "$B", "quarter": "Quarter"},
            color_discrete_map=COMPANY_COLORS,
        )
        fig_ind.update_layout(height=400, xaxis_type="category")
        st.plotly_chart(fig_ind, use_container_width=True)

    # QoQ growth
    df_total = df_capex.groupby("quarter")["capex_bn"].sum().reset_index()
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
    )
    st.plotly_chart(fig_total, use_container_width=True)
else:
    st.warning("No quarterly CAPEX data. Run: python scripts/fetch_financials.py")

# --- 1c. Earnings Calendar ---
st.subheader("Earnings Calendar")

from app.lib.equities import fetch_earnings_calendar

with st.spinner("Fetching earnings dates..."):
    earnings = fetch_earnings_calendar()

if earnings:
    df_earn = pd.DataFrame(earnings)
    df_earn = df_earn[df_earn["earnings_date"].notna()]
    if not df_earn.empty:
        df_earn["earnings_date"] = pd.to_datetime(df_earn["earnings_date"], errors="coerce")
        df_earn = df_earn.dropna(subset=["earnings_date"]).sort_values("earnings_date")
        df_earn["days_away"] = (df_earn["earnings_date"] - pd.Timestamp.now()).dt.days

        cols = st.columns(len(df_earn))
        for i, (_, row) in enumerate(df_earn.iterrows()):
            days = row["days_away"]
            delta_str = "Today" if days == 0 else (f"{abs(days)}d ago" if days < 0 else f"in {days}d")
            cols[i].metric(row["ticker"], row["earnings_date"].strftime("%Y-%m-%d"), delta_str)

# ══════════════════════════════════════════════
# 2. SEMI DEMAND BELLWETHERS
# ══════════════════════════════════════════════
st.header("Semi Demand Bellwethers")

df_semi = pd.read_sql("""
    SELECT ticker, company, period, revenue_usd
    FROM v_semi_revenue
    ORDER BY period
""", conn)

if not df_semi.empty:
    df_semi["revenue_bn"] = df_semi["revenue_usd"] / 1e9
    df_semi["period"] = pd.to_datetime(df_semi["period"])

    tsm_mask = df_semi["ticker"] == "TSM"
    if tsm_mask.any():
        st.caption("Note: TSMC revenue is reported in TWD (not USD). Divide by ~32 for approximate USD.")

    fig_semi = px.line(
        df_semi, x="period", y="revenue_bn", color="company",
        title="Quarterly Revenue ($B / TWD for TSMC)",
        labels={"revenue_bn": "Revenue ($B)"},
        color_discrete_map={"TSMC": "#CC0000", "ASML": "#00529B", "NVIDIA": "#76B900"},
    )
    fig_semi.update_layout(height=400)
    st.plotly_chart(fig_semi, use_container_width=True)

# --- 2b. TSMC Monthly Revenue ---
st.subheader("TSMC Monthly Revenue")
st.caption("Higher frequency signal than quarterly earnings.")

tsmc_path = DATA_DIR / "tsmc_monthly_revenue.csv"
if tsmc_path.exists():
    df_tsmc = pd.read_csv(tsmc_path)
    df_tsmc["date"] = pd.to_datetime(df_tsmc[["year", "month"]].assign(day=1))

    col1, col2 = st.columns(2)
    with col1:
        fig_rev = go.Figure()
        fig_rev.add_trace(go.Bar(x=df_tsmc["date"], y=df_tsmc["revenue_twd_b"], marker_color="#CC0000"))
        fig_rev.update_layout(title="Monthly Revenue (TWD B)", yaxis_title="TWD B", height=350, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_rev, use_container_width=True)
    with col2:
        fig_yoy = go.Figure()
        fig_yoy.add_trace(go.Scatter(x=df_tsmc["date"], y=df_tsmc["yoy_pct"], mode="lines+markers",
                                      line=dict(color="#76B900", width=2), fill="tozeroy", fillcolor="rgba(118,185,0,0.1)"))
        fig_yoy.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_yoy.update_layout(title="YoY Growth %", yaxis_title="YoY %", height=350, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_yoy, use_container_width=True)

# ══════════════════════════════════════════════
# 3. TOKEN CONSUMPTION & AI DEMAND
# ══════════════════════════════════════════════
st.header("AI Demand Indicators")

token_path = DATA_DIR / "token_consumption.csv"
if token_path.exists():
    df_tokens = pd.read_csv(token_path)
    df_tokens["date"] = pd.to_datetime(df_tokens["date"])

    col1, col2 = st.columns(2)

    with col1:
        # User growth
        st.subheader("Frontier Model User Growth")
        df_users = df_tokens[df_tokens["metric"].str.contains("active_users")]
        if not df_users.empty:
            df_users["value_m"] = df_users["value"] / 1e6
            fig_users = px.scatter(
                df_users, x="date", y="value_m", color="provider",
                size="value_m", title="Active Users (Millions)",
                labels={"value_m": "Users (M)", "date": ""},
            )
            fig_users.update_traces(marker=dict(sizemin=5))
            fig_users.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_users, use_container_width=True)

    with col2:
        # Revenue run rate
        st.subheader("OpenAI Revenue Run Rate")
        df_rev = df_tokens[df_tokens["metric"] == "annual_revenue_run_rate"]
        if not df_rev.empty:
            df_rev["value_b"] = df_rev["value"] / 1e9
            fig_arr = go.Figure()
            fig_arr.add_trace(go.Scatter(
                x=df_rev["date"], y=df_rev["value_b"],
                mode="lines+markers+text",
                text=[f"${v:.0f}B" for v in df_rev["value_b"]],
                textposition="top center",
                line=dict(color="#10b981", width=3),
                marker=dict(size=10),
            ))
            fig_arr.update_layout(
                title="ARR ($B)", yaxis_title="$B",
                height=400, margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_arr, use_container_width=True)

# ══════════════════════════════════════════════
# 4. FRONTIER LAB REVENUE & VALUATIONS
# ══════════════════════════════════════════════
st.header("Frontier Lab Revenue & Valuations")

val_path = DATA_DIR / "frontier_lab_valuations.csv"
if val_path.exists():
    df_val = pd.read_csv(val_path)
    df_val["date"] = pd.to_datetime(df_val["date"])

    lab_colors = {"OpenAI": "#10b981", "Anthropic": "#d97706", "xAI": "#6366f1"}

    col1, col2 = st.columns(2)

    with col1:
        # Valuation trajectory
        st.subheader("Valuation Trajectory")
        df_v = df_val[df_val["metric"] == "valuation"].sort_values("date")
        if not df_v.empty:
            fig_v = go.Figure()
            for company, color in lab_colors.items():
                df_c = df_v[df_v["company"] == company]
                if df_c.empty:
                    continue
                fig_v.add_trace(go.Scatter(
                    x=df_c["date"], y=df_c["value"],
                    mode="lines+markers+text",
                    name=company,
                    line=dict(color=color, width=2),
                    marker=dict(size=8),
                    text=[f"${v:.0f}B" for v in df_c["value"]],
                    textposition="top center",
                    textfont=dict(size=9),
                    hovertemplate="<b>%{fullData.name}</b><br>%{x|%b %Y}: $%{y:.0f}B<br>%{customdata}<extra></extra>",
                    customdata=df_c["source"],
                ))
            fig_v.update_layout(
                height=450,
                yaxis_title="Valuation ($B)",
                yaxis_type="log",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_v, use_container_width=True)

    with col2:
        # ARR trajectory
        st.subheader("Revenue Run Rate (ARR)")
        df_r = df_val[df_val["metric"] == "arr"].sort_values("date")
        if not df_r.empty:
            fig_r = go.Figure()
            for company, color in lab_colors.items():
                df_c = df_r[df_r["company"] == company]
                if df_c.empty:
                    continue
                fig_r.add_trace(go.Scatter(
                    x=df_c["date"], y=df_c["value"],
                    mode="lines+markers+text",
                    name=company,
                    line=dict(color=color, width=2),
                    marker=dict(size=8),
                    text=[f"${v:.1f}B" for v in df_c["value"]],
                    textposition="top center",
                    textfont=dict(size=9),
                ))
            fig_r.update_layout(
                height=450,
                yaxis_title="ARR ($B)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_r, use_container_width=True)

    # Valuation / Revenue multiple
    st.subheader("Implied Revenue Multiple")
    # For each company, compute latest valuation / latest ARR
    multiples = []
    for company in lab_colors:
        latest_val = df_val[(df_val["company"] == company) & (df_val["metric"] == "valuation")].sort_values("date").tail(1)
        latest_arr = df_val[(df_val["company"] == company) & (df_val["metric"] == "arr")].sort_values("date").tail(1)
        if not latest_val.empty and not latest_arr.empty:
            val = latest_val.iloc[0]["value"]
            arr = latest_arr.iloc[0]["value"]
            mult = val / arr if arr > 0 else None
            multiples.append({
                "Company": company,
                "Latest Valuation": f"${val:.0f}B",
                "Latest ARR": f"${arr:.1f}B",
                "EV/Revenue": f"{mult:.0f}x" if mult else "-",
                "Val Date": latest_val.iloc[0]["date"].strftime("%b %Y"),
                "ARR Date": latest_arr.iloc[0]["date"].strftime("%b %Y"),
            })
    if multiples:
        st.dataframe(pd.DataFrame(multiples), use_container_width=True, hide_index=True)

    # Full timeline
    with st.expander("Full Announcement Timeline"):
        df_display = df_val.sort_values("date", ascending=False)
        df_display["value_fmt"] = df_display.apply(
            lambda r: f"${r['value']:.1f}B" if r["unit"] == "USD_B" else f"${r['value']:.1f}B",
            axis=1,
        )
        st.dataframe(
            df_display[["date", "company", "metric", "value_fmt", "source", "notes"]].rename(
                columns={"value_fmt": "Value"}
            ),
            use_container_width=True, hide_index=True,
        )

# ══════════════════════════════════════════════
# 5. GPU LEASE PRICES
# ══════════════════════════════════════════════
st.header("GPU Lease Prices")
st.caption("Cloud GPU pricing from primary providers and secondary/spot markets.")

gpu_path = DATA_DIR / "gpu_lease_prices.csv"
if gpu_path.exists():
    df_gpu = pd.read_csv(gpu_path)
    df_gpu["date"] = pd.to_datetime(df_gpu["date"])

    col1, col2 = st.columns(2)

    with col1:
        # H100 pricing across providers
        st.subheader("H100 80GB Pricing")
        df_h100 = df_gpu[df_gpu["gpu_model"] == "H100 80GB"]
        if not df_h100.empty:
            fig_h100 = px.line(
                df_h100, x="date", y="price_per_hour",
                color="provider", line_dash="commitment",
                markers=True,
                title="H100 $/hr by Provider",
                labels={"price_per_hour": "$/hr", "date": ""},
            )
            fig_h100.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_h100, use_container_width=True)

    with col2:
        # All GPU models — latest prices
        st.subheader("Current GPU Pricing")
        latest_date = df_gpu["date"].max()
        # Get most recent price per gpu_model + provider + commitment
        df_latest = df_gpu.sort_values("date").groupby(["gpu_model", "provider", "commitment"]).last().reset_index()
        df_latest = df_latest.sort_values(["gpu_model", "price_per_hour"])

        fig_gpu_bar = px.bar(
            df_latest, x="gpu_model", y="price_per_hour",
            color="provider", pattern_shape="commitment",
            barmode="group",
            title="Latest Prices by GPU Model",
            labels={"price_per_hour": "$/hr", "gpu_model": "GPU"},
        )
        fig_gpu_bar.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_gpu_bar, use_container_width=True)

    # Price trend summary
    df_h100_spot = df_gpu[(df_gpu["gpu_model"] == "H100 80GB") & (df_gpu["commitment"] == "spot")]
    df_h100_od = df_gpu[(df_gpu["gpu_model"] == "H100 80GB") & (df_gpu["commitment"] == "on-demand")]
    if not df_h100_spot.empty and len(df_h100_spot) >= 2:
        first_spot = df_h100_spot.iloc[0]["price_per_hour"]
        last_spot = df_h100_spot.iloc[-1]["price_per_hour"]
        spot_change = ((last_spot / first_spot) - 1) * 100
        st.caption(f"H100 spot market: ${first_spot:.2f}/hr → ${last_spot:.2f}/hr ({spot_change:+.0f}% since first tracked)")

# ══════════════════════════════════════════════
# 6. LLM CAPABILITY TRACKING
# ══════════════════════════════════════════════
st.header("LLM Capability Frontier")

df_elo = pd.read_sql("SELECT * FROM llm_arena_elo ORDER BY elo DESC", conn)
df_specs = pd.read_sql("SELECT * FROM llm_model_specs ORDER BY intelligence_score DESC NULLS LAST", conn)

col1, col2 = st.columns(2)

with col1:
    if not df_elo.empty:
        fig_elo = px.bar(
            df_elo.head(15), x="elo", y="model", color="provider",
            orientation="h", title="Arena Elo Ratings (Top 15)",
            labels={"elo": "Elo Score"},
        )
        fig_elo.update_layout(height=450, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_elo, use_container_width=True)

with col2:
    if not df_specs.empty:
        df_plot = df_specs.dropna(subset=["intelligence_score", "input_price_per_m_tokens"])
        if not df_plot.empty:
            fig_frontier = px.scatter(
                df_plot, x="input_price_per_m_tokens", y="intelligence_score",
                text="model", color="provider",
                title="Intelligence vs Cost Frontier",
                labels={"input_price_per_m_tokens": "$/1M Input Tokens", "intelligence_score": "Intelligence Index"},
            )
            fig_frontier.update_traces(textposition="top center", textfont_size=9)
            fig_frontier.update_layout(height=450)
            st.plotly_chart(fig_frontier, use_container_width=True)

if not df_specs.empty:
    df_ctx = df_specs.dropna(subset=["context_window"]).sort_values("context_window", ascending=False)
    if not df_ctx.empty:
        df_ctx["ctx_k"] = df_ctx["context_window"] / 1000
        fig_ctx = px.bar(
            df_ctx.head(10), x="ctx_k", y="model", orientation="h",
            title="Context Window Leaders (K tokens)",
            labels={"ctx_k": "Context Window (K tokens)"}, color="provider",
        )
        fig_ctx.update_layout(height=350, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_ctx, use_container_width=True)

# --- Model Release Timeline ---
st.subheader("Frontier Model Release Timeline")

model_path = DATA_DIR / "model_releases.csv"
if model_path.exists():
    df_models = pd.read_csv(model_path)
    df_models["release_date"] = pd.to_datetime(df_models["release_date"])
    df_models = df_models.sort_values("release_date")

    category_colors = {"frontier": "#3b82f6", "open_source": "#22c55e", "reasoning": "#f59e0b"}

    fig_timeline = go.Figure()
    for cat, color in category_colors.items():
        df_cat = df_models[df_models["category"] == cat]
        if df_cat.empty:
            continue
        fig_timeline.add_trace(go.Scatter(
            x=df_cat["release_date"], y=df_cat["provider"],
            mode="markers+text",
            marker=dict(size=12, color=color, symbol="diamond"),
            text=df_cat["model"], textposition="top center", textfont=dict(size=9),
            name=cat.replace("_", " ").title(),
            hovertemplate="<b>%{text}</b><br>%{x|%Y-%m-%d}<br>%{customdata}<extra></extra>",
            customdata=df_cat["notable"],
        ))

    fig_timeline.update_layout(height=400, xaxis_title="Release Date",
                                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_timeline, use_container_width=True)

    df_models["quarter"] = df_models["release_date"].dt.to_period("Q").astype(str)
    q_counts = df_models.groupby(["quarter", "category"]).size().reset_index(name="count")
    fig_qcount = px.bar(q_counts, x="quarter", y="count", color="category",
                         title="Model Releases per Quarter", color_discrete_map=category_colors, barmode="stack")
    fig_qcount.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_qcount, use_container_width=True)

# ══════════════════════════════════════════════
# 7. DC POWER DEMAND FORECASTS
# ══════════════════════════════════════════════
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

# ══════════════════════════════════════════════
# 8. BUBBLE RISK SUMMARY
# ══════════════════════════════════════════════
st.header("Risk Summary")
st.markdown("""
| Indicator | Signal | Direction | Notes |
|-----------|--------|-----------|-------|
| Hyperscaler CAPEX | Accelerating | Higher risk | Combined guidance >$300B for 2025, significant upward revisions |
| Semi demand | Strong | Supports thesis | NVDA, TSMC revenue growth 30-45% YoY sustained |
| AI demand / tokens | Surging | Supports thesis | OpenAI ARR 5x in 18 months, 400M+ weekly users |
| Frontier lab valuations | Extreme | Higher risk | OpenAI $300B at ~19x revenue, Anthropic $62B at ~26x |
| GPU lease prices | Declining | Mixed | H100 spot down >50%, but signals oversupply of prior gen |
| LLM capability | Advancing | Lower risk | Continued Elo gains justify CAPEX |
| Model cost deflation | Rapid | Mixed | Enables adoption, compresses enabler margins |
| Open source gap | Narrowing | Higher risk | Reduces moat for paid frontier models |
| DC power demand | Surging | Higher risk | All forecasters projecting near-doubling by 2030 |

*Updated via reference CSVs in data/reference/. Run /ai-research for automated updates.*
""")

conn.close()
