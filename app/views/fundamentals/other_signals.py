"""Other Signals — semi demand, frontier labs, GPU leases, LLM capability, DC power, risk."""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

from app.lib.fx import convert_to_usd
from app.lib.hardware import ARCH_COLOURS, ARCH_ORDER, flagship_per_generation, load_nvidia_dc_gpus

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
# COMPUTE & HARDWARE
# ══════════════════════════════════════════════

CHART_LAYOUT = dict(
    template=st.session_state.get("plotly_template", "plotly_dark"),
    font=dict(family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    hoverlabel=dict(bgcolor=st.session_state.get("hoverlabel_bg", "#333"), font_size=12),
)


def _compute_y_range(scores, max_score=100.0, floor=0.0):
    if not scores:
        return (floor, max_score)
    lo = min(scores)
    hi = max(scores)
    y_min = max(floor, lo - lo * 0.10)
    y_max = min(max_score, hi + hi * 0.05)
    if y_max <= y_min:
        y_max = y_min + 1
    return (y_min, y_max)


st.header("Compute & Hardware")

gpu_df = load_nvidia_dc_gpus()

if gpu_df.empty:
    st.warning(
        "NVIDIA hardware data missing. Expected at data/external/ml_hardware.csv "
        "(sourced from https://epoch.ai/data/ml_hardware.csv). Run `/ai-research` to refresh."
    )
else:
    st.subheader("NVIDIA Data-Centre GPU Performance")
    with st.expander("About this chart"):
        st.markdown("**What it shows.** Peak dense Tensor-FP16/BF16 throughput for each NVIDIA data-centre GPU SKU, plotted against release date. Log scale. Coloured by architecture family (Volta → Ampere → Hopper → Blackwell).")
        st.markdown("**Why it matters.** Training FLOPS per chip has grown ~20× in 8 years (125 TFLOPS V100 → 2500 TFLOPS GB300). Combined with cluster scaling, this is what enables each new frontier-model generation.")
        st.markdown("**Source.** Epoch AI — *Machine Learning Hardware* dataset (epoch.ai/data/machine-learning-hardware), CC-BY licence.")

    fig_gpu = go.Figure()
    for arch in ARCH_ORDER:
        sub = gpu_df[gpu_df["arch"] == arch]
        if sub.empty:
            continue
        hbm_txt = sub["hbm_gb"].map(lambda v: f"{v:.0f} GB HBM" if pd.notna(v) else "HBM —")
        bw_txt = sub["mem_bw_gb_s"].map(lambda v: f"{v:,.0f} GB/s" if pd.notna(v) else "bw —")
        price_txt = sub["price_usd"].map(lambda v: f"${v:,.0f}" if pd.notna(v) else "price —")
        custom = list(zip(sub["tdp_w"].fillna(0), hbm_txt, bw_txt, price_txt))
        fig_gpu.add_trace(go.Scatter(
            x=sub["release_date"],
            y=sub["tflops_tensor_fp16"],
            text=sub["name"],
            customdata=custom,
            name=arch,
            mode="markers",
            marker=dict(size=10, color=ARCH_COLOURS[arch], line=dict(width=1, color="#1f2937")),
            hovertemplate=(
                "%{text}<br>"
                "%{y:,.0f} TFLOPS (Tensor FP16/BF16)<br>"
                "TDP: %{customdata[0]:.0f} W<br>"
                "%{customdata[1]}<br>"
                "%{customdata[2]}<br>"
                "%{customdata[3]}"
                f"<extra>{arch}</extra>"
            ),
        ))

    fig_gpu.update_layout(
        yaxis_title="Tensor-FP16/BF16 Performance (TFLOPS)",
        yaxis_type="log",
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_gpu, use_container_width=True)

    st.subheader("Performance per Watt — Flagship Line")
    with st.expander("About this chart"):
        st.markdown("**What it shows.** Tensor-FP16 TFLOPS divided by TDP (W) for the flagship SKU of each NVIDIA data-centre generation.")
        st.markdown("**Why it matters.** Power (not silicon) is the binding constraint on hyperscale training clusters. Perf-per-watt determines whether the next cluster can be built inside a given power envelope.")
        st.markdown("**Source.** Derived from Epoch AI ML Hardware dataset.")

    flagships = flagship_per_generation(gpu_df)
    flagships = flagships[flagships["tdp_w"].notna()]
    flagships["perf_per_watt"] = flagships["tflops_tensor_fp16"] / flagships["tdp_w"]

    fig_ppw = go.Figure()
    fig_ppw.add_trace(go.Scatter(
        x=flagships["release_date"],
        y=flagships["perf_per_watt"],
        text=flagships["name"] + " (" + flagships["arch"] + ")",
        mode="lines+markers",
        line=dict(color="#10b981", width=2),
        marker=dict(size=10, color="#10b981"),
        hovertemplate="%{text}<br>%{y:.2f} TFLOPS/W<extra></extra>",
    ))

    y_min, y_max = _compute_y_range(flagships["perf_per_watt"].tolist(), max_score=10, floor=0.1)
    fig_ppw.update_layout(
        yaxis_title="Tensor FP16 TFLOPS per Watt",
        yaxis_range=[y_min, y_max],
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_ppw, use_container_width=True)

    st.subheader("H100 Rental Prices")
    with st.expander("About this chart"):
        st.markdown("**What it shows.** Monthly median H100 rental price in $/GPU-hour, broken out by provider tier.")
        st.markdown("**Why it matters.** H100 lease rates are the cleanest public proxy for GPU depreciation and chip obsolescence. Sharp 2025 declines reflect Blackwell supply coming online.")
        st.markdown("**Source.** Silicon Data — *H100 Rental Index* (silicondata.com/blog/h100-rental-price-over-time).")

    @st.cache_data(ttl=86400)
    def load_h100_prices() -> pd.DataFrame:
        csv = DATA_DIR / "h100_rental_prices.csv"
        if not csv.exists():
            return pd.DataFrame()
        df = pd.read_csv(csv)
        df["month"] = pd.to_datetime(df["month"])
        return df

    h100_df = load_h100_prices()
    if h100_df.empty:
        st.warning("H100 rental price CSV missing.")
    else:
        tier_colours = {
            "Hyperscaler": "#3b82f6",
            "Neocloud":    "#a855f7",
            "Marketplace": "#10b981",
        }

        fig_h100 = go.Figure()
        for tier in ["Hyperscaler", "Neocloud", "Marketplace"]:
            sub = h100_df[h100_df["tier"] == tier].sort_values("month")
            if sub.empty:
                continue
            fig_h100.add_trace(go.Scatter(
                x=sub["month"],
                y=sub["price_usd_per_gpu_hr"],
                name=tier,
                mode="lines+markers",
                line=dict(color=tier_colours[tier], width=2),
                marker=dict(size=6, color=tier_colours[tier]),
                hovertemplate=f"{tier}<br>%{{x|%b %Y}}: $%{{y:.2f}}/GPU-hr<extra></extra>",
            ))

        y_min, y_max = _compute_y_range(
            h100_df["price_usd_per_gpu_hr"].tolist(), max_score=12, floor=0.5
        )
        fig_h100.update_layout(
            yaxis_title="$ per GPU-hour",
            yaxis_range=[y_min, y_max],
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_h100, use_container_width=True)

# ══════════════════════════════════════════════
# ROUNDHILL GENERATIVE AI & TECH ETF (CHAT)
# ══════════════════════════════════════════════
st.header("Roundhill Generative AI & Tech ETF (CHAT)")
st.caption(
    "Actively managed ETF tracking the generative AI value chain across four segments: "
    "**Platforms** (LLM development), **Infrastructure** (GPUs, semis), "
    "**Enterprise Software** (business AI apps), and **Consumer Software** (consumer AI apps). "
    "Includes non-US exposure (Chinese AI, Korean semiconductors). "
    "[Fund details →](https://www.roundhillinvestments.com/etf/chat/)"
)

try:
    import yfinance as yf

    _chat_etf = yf.Ticker("CHAT")
    _chat_info = _chat_etf.info
    _chat_price = _chat_info.get("regularMarketPrice") or _chat_info.get("previousClose")
    _chat_aum = _chat_info.get("totalAssets")
    _chat_pe = _chat_info.get("trailingPE")
    _chat_ytd = _chat_info.get("ytdReturn")
    _chat_52lo = _chat_info.get("fiftyTwoWeekLow")
    _chat_52hi = _chat_info.get("fiftyTwoWeekHigh")

    col_chat1, col_chat2, col_chat3, col_chat4 = st.columns(4)
    if _chat_price:
        col_chat1.metric("Price", f"${_chat_price:.2f}")
    if _chat_aum:
        col_chat2.metric("AUM", f"${_chat_aum / 1e9:.2f}B")
    if _chat_pe:
        col_chat3.metric("Trailing PE", f"{_chat_pe:.1f}x")
    if _chat_ytd is not None:
        col_chat4.metric("YTD Return", f"{_chat_ytd * 100:+.1f}%")

    col_ch1, col_ch2 = st.columns([2, 1])
    with col_ch1:
        _chat_holdings = _chat_etf.get_funds_data()
        if hasattr(_chat_holdings, "top_holdings") and _chat_holdings.top_holdings is not None:
            df_hold = _chat_holdings.top_holdings.head(10).copy()
            df_hold = df_hold.reset_index()
            df_hold.columns = ["Ticker", "Name", "Weight"]
            df_hold["Weight"] = df_hold["Weight"].apply(lambda x: f"{x * 100:.1f}%")
            st.dataframe(df_hold, use_container_width=True, hide_index=True)
        else:
            st.info("Holdings data not available from yfinance.")

    with col_ch2:
        if _chat_52lo and _chat_52hi and _chat_price:
            pct_of_range = (_chat_price - _chat_52lo) / (_chat_52hi - _chat_52lo) * 100 if _chat_52hi > _chat_52lo else 50
            st.markdown(
                f"**52-Week Range**  \n"
                f"${_chat_52lo:.2f} — ${_chat_52hi:.2f}  \n"
                f"Currently at {pct_of_range:.0f}% of range"
            )
        st.markdown(
            "**Why track CHAT?**  \n"
            "CHAT is the closest pure-play ETF to the AI infrastructure thesis this dashboard monitors. "
            "Its price action reflects market consensus on the generative AI value chain — "
            "a useful cross-check against the individual signals tracked above."
        )
        st.caption("Expense ratio: 0.75% · Inception: May 2023 · Actively managed")

except Exception as e:
    st.warning(f"Could not fetch CHAT ETF data: {e}")

# ══════════════════════════════════════════════
# INDUSTRY STRAIN — investment/revenue ratio
# ══════════════════════════════════════════════
st.header("Industry Strain")
st.caption(
    "The ratio of deployed AI CAPEX to AI end-customer revenue. "
    "Revenue = frontier lab ARR + cloud AI services (Azure AI, AWS AI). "
    "NVIDIA GPU revenue is excluded — it's a supply-chain transfer, not end-customer revenue. "
    "Telecom CAPEX/revenue peaked at ~4x before the bust (2001)."
)

from app.lib.bubble_gauges import industry_strain as _calc_industry_strain, ZONE_COLORS

_is = _calc_industry_strain(DB_PATH)
if _is["value"] is not None:
    col_is1, col_is2 = st.columns([2, 1])
    with col_is1:
        # Bar chart: CAPEX vs AI Revenue with ratio annotation
        is_fig = go.Figure()

        # Parse components from detail string
        lab_arr, cloud_ai = 0, 0
        val_path = DATA_DIR / "frontier_lab_valuations.csv"
        if val_path.exists():
            df_v = pd.read_csv(val_path)
            df_arr = df_v[df_v["metric"] == "arr"].sort_values("date")
            for company in df_arr["company"].unique():
                lab_arr += df_arr[df_arr["company"] == company].iloc[-1]["value"]

        supp_path = DATA_DIR / "ai_supplement.csv"
        if supp_path.exists():
            df_s = pd.read_csv(supp_path)
            for _, row in df_s.iterrows():
                desc = str(row.get("Metric Description", ""))
                if "AI" in desc and "%" not in desc:
                    val_str = str(row.get("FY2025E", ""))
                    val_str = val_str.replace(">", "").replace(",", "").replace('"', "").strip()
                    try:
                        cloud_ai += float(val_str) / 1000
                    except (ValueError, TypeError):
                        pass

        capex_bn = float(_is["detail"].split("$")[1].split("B")[0])

        is_fig.add_trace(go.Bar(
            x=["Hyperscaler CAPEX"], y=[capex_bn],
            marker_color="#ef4444", name="CAPEX Deployed",
            hovertemplate="CAPEX: $%{y:.0f}B<extra></extra>",
        ))
        is_fig.add_trace(go.Bar(
            x=["AI Revenue"], y=[lab_arr],
            marker_color="#22c55e", name="Frontier Lab ARR",
            hovertemplate="Lab ARR: $%{y:.0f}B<extra></extra>",
        ))
        is_fig.add_trace(go.Bar(
            x=["AI Revenue"], y=[cloud_ai],
            marker_color="#3b82f6", name="Cloud AI Revenue",
            hovertemplate="Cloud AI: $%{y:.0f}B<extra></extra>",
        ))

        is_fig.update_layout(
            barmode="stack", height=350,
            yaxis_title="$B (trailing 4Q / annualized)",
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(is_fig, use_container_width=True)

    with col_is2:
        zone_color = ZONE_COLORS[_is["zone"]]
        st.markdown(
            f'<div style="border:2px solid {zone_color}; border-radius:8px; '
            f'padding:1rem; text-align:center; margin-top:1rem;">'
            f'<div style="font-size:0.8rem; color:#9ca3af;">Investment / Revenue</div>'
            f'<div style="font-size:2.5rem; font-weight:700; color:{zone_color};">'
            f'{_is["value_fmt"]}</div>'
            f'<div style="font-size:0.85rem; color:{zone_color};">{_is["zone"].upper()}</div>'
            f'<div style="font-size:0.75rem; color:#9ca3af; margin-top:0.5rem;">'
            f'Telecom peak: 4.0x</div>'
            f'<div style="font-size:0.7rem; color:#6b7280; margin-top:0.3rem;">'
            f'Green &lt;3x · Amber 3–5x · Red &gt;5x</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ══════════════════════════════════════════════
# FUNDING QUALITY
# ══════════════════════════════════════════════
st.header("Funding Quality")
st.caption(
    "Assesses the sustainability of capital flowing into AI infrastructure. "
    "Tracks debt-vs-equity funding mix and circular financing arrangements "
    "(where an investor is also a major customer/supplier — e.g. Nvidia investing in companies that buy Nvidia GPUs)."
)

deals_path = DATA_DIR / "funding_deals.csv"
if deals_path.exists():
    df_deals = pd.read_csv(deals_path)
    df_deals["date"] = pd.to_datetime(df_deals["date"])
    df_deployed = df_deals[df_deals["type"] != "hybrid"].copy()

    col_fq1, col_fq2 = st.columns([2, 1])

    with col_fq1:
        # Deal type breakdown
        type_totals = df_deployed.groupby("type")["amount_bn"].sum().reset_index()
        type_colors = {"equity": "#22c55e", "debt": "#ef4444", "ipo": "#3b82f6", "balance_sheet": "#6b7280"}

        fq_fig = go.Figure()
        fq_fig.add_trace(go.Bar(
            x=type_totals["type"],
            y=type_totals["amount_bn"],
            marker_color=[type_colors.get(t, "#888") for t in type_totals["type"]],
            hovertemplate="%{x}: $%{y:.1f}B<extra></extra>",
        ))
        fq_fig.update_layout(
            height=300, yaxis_title="$B",
            showlegend=False,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fq_fig, use_container_width=True)

        # Deal table
        circular_deals = df_deployed[df_deployed["is_circular"].astype(bool)]
        if not circular_deals.empty:
            st.markdown("**Circular financing arrangements:**")
            for _, deal in circular_deals.iterrows():
                st.caption(
                    f"• **{deal['entity']}** ${deal['amount_bn']:.0f}B ({deal['type']}) — "
                    f"{deal['notes']}"
                )

    with col_fq2:
        from app.lib.bubble_gauges import funding_quality as _calc_fq
        _fq = _calc_fq()
        if _fq["value"] is not None:
            fq_color = ZONE_COLORS[_fq["zone"]]
            circ_count = int(df_deployed["is_circular"].astype(bool).sum())
            st.markdown(
                f'<div style="border:2px solid {fq_color}; border-radius:8px; '
                f'padding:1rem; text-align:center; margin-top:1rem;">'
                f'<div style="font-size:0.8rem; color:#9ca3af;">Funding Quality</div>'
                f'<div style="font-size:2rem; font-weight:700; color:{fq_color};">'
                f'{_fq["value_fmt"]}</div>'
                f'<div style="font-size:1rem; color:{fq_color};">'
                f'{circ_count} circular deals</div>'
                f'<div style="font-size:0.85rem; color:{fq_color};">{_fq["zone"].upper()}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ══════════════════════════════════════════════
# 5-GAUGE BUBBLE RISK SUMMARY
# ══════════════════════════════════════════════
st.header("Bubble Risk Dashboard")
st.caption(
    "5-gauge framework inspired by [boomorbubble.ai](https://boomorbubble.ai/) "
    "(Azeem Azhar, Exponential View). "
    "Rule: 0–1 red = Boom · 2 red = Caution · 3+ red = Bubble."
)

from app.lib.bubble_gauges import all_gauges, overall_assessment, DIRECTION_ARROWS

gauges = all_gauges(DB_PATH)
assessment = overall_assessment(gauges)

# Overall badge
st.markdown(
    f'<div style="text-align:center; padding:0.5rem 0;">'
    f'<span style="font-size:1.4rem; font-weight:700; color:{assessment["color"]};">'
    f'{assessment["label"]}</span>'
    f'<span style="font-size:0.85rem; color:#9ca3af; margin-left:0.75rem;">'
    f'{assessment["detail"]}</span></div>',
    unsafe_allow_html=True,
)

# Gauge table
gauge_rows = []
for g in gauges:
    zone_color = ZONE_COLORS.get(g["zone"], "#6b7280")
    arrow = DIRECTION_ARROWS.get(g["direction"], "→")
    gauge_rows.append({
        "Gauge": g["name"],
        "Reading": g["value_fmt"],
        "Zone": g["zone"].upper(),
        "Trend": arrow,
        "Benchmark": g["benchmark"],
        "Detail": g["detail"],
    })
df_gauges = pd.DataFrame(gauge_rows)
st.dataframe(df_gauges, use_container_width=True, hide_index=True)

# Qualitative signals table (preserved from original)
st.subheader("Qualitative Signals")
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

*Updated April 2026. Quantitative gauges auto-computed from reference data + live feeds.*
""")

conn.close()
