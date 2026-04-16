"""Equity Analysis (key players) — Mag 7, AI Infra, DC Operators.

Share price performance is split into per-group tiles. Fundamentals + charts below.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

st.title("Equity Analysis (key players)")

from app.lib.equities import fetch_equities_data

with st.spinner("Fetching equity data..."):
    stocks = fetch_equities_data()

if not stocks:
    st.warning("No equity data available. Check network connection.")
    st.stop()


# ── Shared formatters ──
def _color_returns(val):
    if val is None or pd.isna(val):
        return "color: gray"
    return "color: #22c55e" if val >= 0 else "color: #ef4444"


def _fmt_pct(val):
    if val is None or pd.isna(val):
        return "-"
    return f"{val:+.2f}%"


def _fmt_price(val):
    if val is None or pd.isna(val):
        return "-"
    return f"${val:,.2f}"


def _fmt_mcap(val):
    if val is None or pd.isna(val):
        return "-"
    if val >= 1000:
        return f"${val / 1000:.2f}T"
    return f"${val:.1f}B"


def _fmt_pe(val):
    if val is None or pd.isna(val):
        return "-"
    return f"{val:.1f}x"


def _fmt_eps(val):
    if val is None or pd.isna(val):
        return "-"
    return f"${val:.2f}"




# ──────────────────────────────────────────────
# 1. SHARE PRICE PERFORMANCE — per-group tiles
# ──────────────────────────────────────────────
st.header("Share Price Performance")

return_cols = ["Daily %", "1M %", "3M %", "6M %", "1Y %", "5Y %", "10Y %"]

# Preserve group order from MAG7_AI_STOCKS
seen_groups = []
for s in stocks:
    if s["group"] not in seen_groups:
        seen_groups.append(s["group"])

for group in seen_groups:
    group_stocks = [s for s in stocks if s["group"] == group]
    perf_rows = []
    for s in group_stocks:
        ret = s.get("returns", {})
        perf_rows.append({
            "Ticker": s["symbol"],
            "Name": s["name"],
            "Price": s["price"],
            "Daily %": s["change_pct"],
            "1M %": ret.get("1M"),
            "3M %": ret.get("3M"),
            "6M %": ret.get("6M"),
            "1Y %": ret.get("1Y"),
            "5Y %": ret.get("5Y"),
            "10Y %": ret.get("10Y"),
        })

    df_perf = pd.DataFrame(perf_rows)

    fund_rows = []
    for s in group_stocks:
        mcap = s.get("market_cap")
        mcap_fmt = round(mcap / 1e9, 1) if mcap else None
        fund_rows.append({
            "Ticker": s["symbol"],
            "Name": s["name"],
            "Mkt Cap ($B)": mcap_fmt,
            "PE (T)": s.get("pe_trailing"),
            "PE (F)": s.get("pe_forward"),
            "EPS (T)": s.get("eps_trailing"),
            "EPS (F)": s.get("eps_forward"),
            "52W Low": s.get("week52_low"),
            "52W High": s.get("week52_high"),
            "1Y Target Est": s.get("target_mean_1y"),
        })
    df_fund = pd.DataFrame(fund_rows)

    # Both tables have 10 columns; force equal widths so columns align between tables.
    perf_col_config = {col: st.column_config.Column(width="small") for col in df_perf.columns}
    fund_col_config = {col: st.column_config.Column(width="small") for col in df_fund.columns}

    with st.container(border=True):
        st.subheader(group)
        fmt_map = {col: _fmt_pct for col in return_cols}
        fmt_map["Price"] = _fmt_price
        styled = (
            df_perf.style
            .format(fmt_map)
            .map(_color_returns, subset=return_cols)
        )
        # Tile height scales with row count (~35px per row + header)
        row_h = 35 * (len(df_perf) + 1) + 3
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            height=row_h,
            column_config=perf_col_config,
        )

        styled_fund = df_fund.style.format({
            "Mkt Cap ($B)": _fmt_mcap,
            "PE (T)": _fmt_pe,
            "PE (F)": _fmt_pe,
            "EPS (T)": _fmt_eps,
            "EPS (F)": _fmt_eps,
            "52W Low": _fmt_price,
            "52W High": _fmt_price,
            "1Y Target Est": _fmt_price,
        })
        fund_h = 35 * (len(df_fund) + 1) + 3
        st.dataframe(
            styled_fund,
            use_container_width=True,
            hide_index=True,
            height=fund_h,
            column_config=fund_col_config,
        )

# ──────────────────────────────────────────────
# 2. CHARTS
# ──────────────────────────────────────────────
col1, col2 = st.columns(2)

# --- P/E Comparison ---
with col1:
    st.subheader("P/E Comparison")
    pe_data = [s for s in stocks if s.get("pe_forward") is not None]
    if pe_data:
        pe_data.sort(key=lambda x: x.get("pe_forward") or 0)
        fig_pe = go.Figure()
        fig_pe.add_trace(go.Bar(
            y=[s["symbol"] for s in pe_data],
            x=[s.get("pe_trailing") for s in pe_data],
            name="Trailing PE",
            orientation="h",
            marker_color="rgba(156, 163, 175, 0.5)",
        ))
        fig_pe.add_trace(go.Bar(
            y=[s["symbol"] for s in pe_data],
            x=[s.get("pe_forward") for s in pe_data],
            name="Forward PE",
            orientation="h",
            marker_color="rgba(59, 130, 246, 0.85)",
        ))
        fig_pe.update_layout(
            barmode="group",
            height=500,
            xaxis_title="P/E Ratio",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_pe, use_container_width=True)
    else:
        st.info("P/E data not available.")

# --- Market Cap Treemap ---
with col2:
    st.subheader("Market Cap Treemap")
    tree_data = [s for s in stocks if s.get("market_cap") and s.get("returns", {}).get("1Y") is not None]
    if tree_data:
        df_tree = pd.DataFrame([{
            "symbol": s["symbol"],
            "name": s["name"],
            "group": s["group"],
            "market_cap": s["market_cap"],
            "ytd_pct": s["returns"].get("1Y", 0) or 0,
        } for s in tree_data])

        df_tree["label"] = df_tree.apply(
            lambda r: f"{r['symbol']}<br>${r['market_cap'] / 1e12:.2f}T<br>{r['ytd_pct']:+.1f}%"
            if r["market_cap"] >= 1e12
            else f"{r['symbol']}<br>${r['market_cap'] / 1e9:.0f}B<br>{r['ytd_pct']:+.1f}%",
            axis=1,
        )

        fig_tree = px.treemap(
            df_tree,
            path=["group", "label"],
            values="market_cap",
            color="ytd_pct",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
        )
        fig_tree.update_layout(
            height=500,
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_colorbar=dict(title="1Y %"),
        )
        st.plotly_chart(fig_tree, use_container_width=True)
    else:
        st.info("Market cap data not available.")

# ──────────────────────────────────────────────
# 3. VALUATION HEAT — bubble risk context
# ──────────────────────────────────────────────
st.header("Valuation Heat")
st.caption(
    "Bubble-risk context for current valuations. Nasdaq-100 PE via QQQ ETF (live). "
    "Mag 7 market cap concentration compared to dot-com peak. "
    "Framework: boomorbubble.ai (Exponential View)."
)

col_vh1, col_vh2 = st.columns(2)

with col_vh1:
    st.subheader("Nasdaq-100 PE Context")
    try:
        import yfinance as yf
        qqq = yf.Ticker("QQQ")
        qqq_info = qqq.info
        qqq_pe = qqq_info.get("trailingPE")
        if qqq_pe:
            benchmarks = [
                ("Dot-com Peak (Mar 2000)", 175, "#ef4444"),
                ("Pre-COVID (2019)", 25, "#6b7280"),
                ("Current QQQ", qqq_pe, "#3b82f6"),
            ]
            fig_pe_ctx = go.Figure()
            for label, val, color in benchmarks:
                fig_pe_ctx.add_trace(go.Bar(
                    y=[label], x=[val], orientation="h",
                    marker_color=color, showlegend=False,
                    text=[f"{val:.0f}x"], textposition="outside",
                    hovertemplate=f"{label}: {val:.1f}x<extra></extra>",
                ))

            # Zone shading
            fig_pe_ctx.add_vrect(x0=0, x1=30, fillcolor="#22c55e", opacity=0.05, line_width=0)
            fig_pe_ctx.add_vrect(x0=30, x1=40, fillcolor="#f59e0b", opacity=0.05, line_width=0)
            fig_pe_ctx.add_vrect(x0=40, x1=200, fillcolor="#ef4444", opacity=0.05, line_width=0)

            fig_pe_ctx.update_layout(
                height=250, xaxis_title="Trailing P/E",
                margin=dict(l=0, r=60, t=10, b=0),
            )
            st.plotly_chart(fig_pe_ctx, use_container_width=True)
            st.caption(
                f"QQQ trailing PE: **{qqq_pe:.1f}x** — "
                f"{'Green (<30x)' if qqq_pe < 30 else 'Amber (30–40x)' if qqq_pe < 40 else 'Red (>40x)'}. "
                "Dot-com peak was ~175x. Source: Yahoo Finance (live)."
            )
        else:
            st.info("QQQ PE not available from yfinance.")
    except Exception as e:
        st.warning(f"Could not fetch QQQ data: {e}")

with col_vh2:
    st.subheader("Mag 7 Market Cap Concentration")
    mag7_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
    mag7_stocks = [s for s in stocks if s["symbol"] in mag7_tickers and s.get("market_cap")]

    if mag7_stocks:
        mag7_total = sum(s["market_cap"] for s in mag7_stocks) / 1e12
        mag7_data = sorted(mag7_stocks, key=lambda s: s["market_cap"], reverse=True)

        fig_conc = go.Figure()
        fig_conc.add_trace(go.Bar(
            x=[s["symbol"] for s in mag7_data],
            y=[s["market_cap"] / 1e12 for s in mag7_data],
            marker_color=[
                "#3b82f6" if s["symbol"] != "NVDA" else "#76B900"
                for s in mag7_data
            ],
            hovertemplate="%{x}: $%{y:.2f}T<extra></extra>",
        ))
        fig_conc.update_layout(
            height=250, yaxis_title="Market Cap ($T)",
            showlegend=False,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_conc, use_container_width=True)
        st.caption(
            f"Mag 7 combined: **${mag7_total:.1f}T**. "
            f"At dot-com peak, top 5 were ~18% of S&P 500 (S&P Dow Jones). "
            f"Today's Mag 7 share is estimated at ~33% — nearly 2x the dot-com concentration."
        )
    else:
        st.info("Mag 7 market cap data not available.")

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
