"""Other Signals — semi demand, frontier labs, GPU leases, LLM capability, DC power, risk."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

from app.lib.fx import convert_to_usd

DB_PATH = st.session_state["db_path"]
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"

st.title("Other Signals")
st.caption("Bubble-risk indicators beyond hyperscaler CAPEX.")

conn = sqlite3.connect(DB_PATH)

# ══════════════════════════════════════════════
# SEMI DEMAND BELLWETHERS
# ══════════════════════════════════════════════
st.header("Semi Demand Bellwethers")
st.caption(
    "TSMC monthly revenue is the highest-frequency public signal for AI hardware demand across the full value chain. "
    "ASML orders are a 6–12 month leading indicator of new node capacity. "
    "NVDA captures direct AI accelerator demand."
)

df_semi = pd.read_sql(
    """
    SELECT ticker, company, period, revenue_usd
    FROM v_semi_revenue
    ORDER BY period
    """,
    conn,
)

if not df_semi.empty:
    df_semi["period"] = pd.to_datetime(df_semi["period"])

    # The ETL stamps every row 'USD' but TSMC reports in TWD and ASML in EUR.
    # Convert each ticker's native currency to USD using historical Yahoo rates
    # so the chart compares like-for-like.
    df_semi["revenue_native"] = df_semi["revenue_usd"]
    for ticker, pair in [("TSM", "USDTWD=X"), ("ASML", "USDEUR=X")]:
        mask = df_semi["ticker"] == ticker
        if mask.any():
            df_semi.loc[mask, "revenue_native"] = convert_to_usd(
                df_semi.loc[mask, "revenue_usd"],
                df_semi.loc[mask, "period"],
                pair,
            )
    df_semi["revenue_bn"] = df_semi["revenue_native"] / 1e9

    st.caption(
        "TSMC and ASML converted to USD using historical Yahoo FX rates "
        "(USDTWD, USDEUR) at each reporting date."
    )

    fig_semi = px.line(
        df_semi, x="period", y="revenue_bn", color="company",
        title="Quarterly Revenue ($B USD)",
        labels={"revenue_bn": "Revenue ($B)"},
        color_discrete_map={"TSMC": "#CC0000", "ASML": "#00529B", "NVIDIA": "#76B900"},
    )
    fig_semi.update_layout(height=400)
    st.plotly_chart(fig_semi, use_container_width=True)

# --- TSMC Monthly Revenue ---
st.subheader("TSMC Monthly Revenue")
st.caption("Higher frequency signal than quarterly earnings. Converted to USD using historical Yahoo USDTWD rates.")

tsmc_path = DATA_DIR / "tsmc_monthly_revenue.csv"
if tsmc_path.exists():
    df_tsmc = pd.read_csv(tsmc_path)
    df_tsmc["date"] = pd.to_datetime(df_tsmc[["year", "month"]].assign(day=1))
    # Convert TWD billions → USD billions using historical FX
    df_tsmc["revenue_usd_b"] = convert_to_usd(
        df_tsmc["revenue_twd_b"], df_tsmc["date"], "USDTWD=X"
    )

    col1, col2 = st.columns(2)
    with col1:
        fig_rev = go.Figure()
        fig_rev.add_trace(go.Bar(
            x=df_tsmc["date"],
            y=df_tsmc["revenue_usd_b"],
            marker_color="#CC0000",
            customdata=df_tsmc["revenue_twd_b"],
            hovertemplate="%{x|%b %Y}<br>$%{y:.2f}B USD<br>%{customdata:.1f}B TWD<extra></extra>",
        ))
        fig_rev.update_layout(
            title="Monthly Revenue ($B USD)",
            yaxis_title="$B USD",
            height=350,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_rev, use_container_width=True)
    with col2:
        fig_yoy = go.Figure()
        fig_yoy.add_trace(go.Scatter(x=df_tsmc["date"], y=df_tsmc["yoy_pct"], mode="lines+markers",
                                      line=dict(color="#76B900", width=2), fill="tozeroy", fillcolor="rgba(118,185,0,0.1)"))
        fig_yoy.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_yoy.update_layout(title="YoY Growth %", yaxis_title="YoY %", height=350, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_yoy, use_container_width=True)

# ══════════════════════════════════════════════
# TOKEN CONSUMPTION & AI DEMAND
# ══════════════════════════════════════════════
st.header("AI Demand Indicators")
st.caption(
    "User growth is the clearest leading indicator of whether AI revenue can sustain current CAPEX levels. "
    "Rising users without commensurate monetisation would be a key bubble-risk signal."
)

token_path = DATA_DIR / "token_consumption.csv"
if token_path.exists():
    df_tokens = pd.read_csv(token_path)
    df_tokens["date"] = pd.to_datetime(df_tokens["date"])

    st.subheader("Frontier Model User Growth")
    st.caption("Mix of weekly active users (OpenAI) and monthly active users (Anthropic, Google, xAI) — compare directionally, not precisely.")
    df_users = df_tokens[df_tokens["metric"].str.contains("active_users")].copy()
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

# ══════════════════════════════════════════════
# FRONTIER LAB REVENUE & VALUATIONS
# ══════════════════════════════════════════════
st.header("Frontier Lab Revenue & Valuations")
st.caption(
    "Frontier labs are consuming the majority of AI CAPEX but are private. "
    "Funding round valuations and reported ARR are the only public signals. "
    "Implied EV/Revenue multiples of 15–30× represent the 'AI premium' the market is pricing in — "
    "the key question is whether revenue acceleration justifies the multiple expansion."
)

val_path = DATA_DIR / "frontier_lab_valuations.csv"
if val_path.exists():
    df_val = pd.read_csv(val_path)
    df_val["date"] = pd.to_datetime(df_val["date"])

    lab_colors = {"OpenAI": "#10b981", "Anthropic": "#d97706", "xAI": "#6366f1"}

    col1, col2 = st.columns(2)

    with col1:
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

    st.subheader("Implied Revenue Multiple")
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
# GPU LEASE PRICES
# ══════════════════════════════════════════════
st.header("GPU Lease Prices")
st.caption(
    "Spot GPU prices are the most real-time signal of AI compute supply/demand. "
    "Declining spot prices indicate supply outpacing demand; rising prices indicate the opposite. "
    "H100 spot at ~$1/hr (vs $4/hr peak) signals significant oversupply of prior-gen compute as Blackwell comes online."
)

gpu_path = DATA_DIR / "gpu_lease_prices.csv"
if gpu_path.exists():
    df_gpu = pd.read_csv(gpu_path)
    df_gpu["date"] = pd.to_datetime(df_gpu["date"])

    col1, col2 = st.columns(2)

    with col1:
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
        st.subheader("Current GPU Pricing")
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

    df_h100_spot = df_gpu[(df_gpu["gpu_model"] == "H100 80GB") & (df_gpu["commitment"] == "spot")]
    if not df_h100_spot.empty and len(df_h100_spot) >= 2:
        first_spot = df_h100_spot.iloc[0]["price_per_hour"]
        last_spot = df_h100_spot.iloc[-1]["price_per_hour"]
        spot_change = ((last_spot / first_spot) - 1) * 100
        st.caption(f"H100 spot market: ${first_spot:.2f}/hr → ${last_spot:.2f}/hr ({spot_change:+.0f}% since first tracked)")

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
# DC POWER DEMAND FORECASTS
# ══════════════════════════════════════════════
st.header("DC Power Demand Forecasts")
st.caption(
    "Power constraint — not silicon — is now the binding constraint on hyperscale AI clusters. "
    "All major forecasters project near-doubling of data centre power demand by 2030. "
    "The key risk: if power build-out falls behind, CAPEX commitments become stranded."
)

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
# BUBBLE RISK SUMMARY
# ══════════════════════════════════════════════
st.header("Risk Summary")
st.markdown("""
| Indicator | Signal | Direction | Notes |
|-----------|--------|-----------|-------|
| Hyperscaler CAPEX | Accelerating | Higher risk | Combined guidance >$350B for 2026, continued upward revisions |
| Semi demand | Strong | Supports thesis | TSMC revenue growth 35-45% YoY sustained through Q1 2026 |
| AI demand / tokens | Surging | Supports thesis | OpenAI ARR $25B, 900M WAU; Anthropic ARR $30B, surpassed OpenAI |
| Frontier lab valuations | Extreme | Higher risk | Anthropic $380B at ~13x ARR, xAI $230B, OpenAI TBD |
| GPU lease prices | Declining | Mixed | H100 spot <$1/hr, down >75% from peak — Blackwell driving migration |
| LLM capability | Advancing | Lower risk | GPQA >94%, HLE >53%, SWE-Bench >80% — continued rapid gains |
| Model cost deflation | Rapid | Mixed | Enables adoption, compresses enabler margins |
| Open source gap | Narrowing | Higher risk | Qwen3.5, Kimi K2.5 competitive with frontier on benchmarks |
| DC power demand | Surging | Higher risk | All forecasters projecting near-doubling by 2030 |

*Updated April 2026 via reference CSVs in data/reference/. Run /ai-research for automated updates.*
""")

conn.close()
