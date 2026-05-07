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
    tree_data = [s for s in stocks if s.get("market_cap")]
    if tree_data:
        has_returns = any(s.get("returns", {}).get("1Y") is not None for s in tree_data)
        rows = []
        for s in tree_data:
            ret_1y = s.get("returns", {}).get("1Y")
            mc = s["market_cap"]
            mc_label = f"${mc / 1e12:.2f}T" if mc >= 1e12 else f"${mc / 1e9:.0f}B"
            label = f"{s['symbol']}<br>{mc_label}" + (f"<br>{ret_1y:+.1f}%" if ret_1y is not None else "")
            rows.append({
                "symbol": s["symbol"],
                "group": s["group"],
                "market_cap": mc,
                "ytd_pct": ret_1y if ret_1y is not None else 0,
                "label": label,
            })
        df_tree = pd.DataFrame(rows)

        fig_tree = px.treemap(
            df_tree,
            path=["group", "label"],
            values="market_cap",
            **({"color": "ytd_pct", "color_continuous_scale": "RdYlGn", "color_continuous_midpoint": 0}
               if has_returns else {}),
        )
        fig_tree.update_layout(
            height=500,
            margin=dict(l=0, r=0, t=30, b=0),
            **({"coloraxis_colorbar": dict(title="1Y %")} if has_returns else {}),
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

        # Live S&P 500 total float market cap estimate.
        # S&P 500 float market cap = index level × S&P 500 divisor.
        # Divisor ≈ 8.9B as of 2024 (S&P Dow Jones; adjusts slowly via corporate actions).
        _SP500_DIVISOR = 8.9e9
        _mag7_pct = None
        _sp500_mc_T = None
        try:
            import yfinance as yf
            _gspc_hist = yf.Ticker("^GSPC").history(period="1d")
            if not _gspc_hist.empty:
                _gspc_level = float(_gspc_hist["Close"].iloc[-1])
                _sp500_mc_T = _gspc_level * _SP500_DIVISOR / 1e12
                _mag7_pct = mag7_total / _sp500_mc_T * 100
        except Exception:
            pass

        _pct_label = f"{_mag7_pct:.0f}%" if _mag7_pct else "~33% (est.)"

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
            margin=dict(l=0, r=0, t=30, b=0),
            title=dict(
                text=f"Combined: ${mag7_total:.1f}T  ·  S&P 500 share: {_pct_label}",
                font=dict(size=12, color="#9ca3af"),
                x=0,
            ),
        )
        st.plotly_chart(fig_conc, use_container_width=True)

        if _mag7_pct and _sp500_mc_T:
            _vs_dotcom = _mag7_pct / 18  # dot-com top-5 were ~18% of S&P 500
            st.caption(
                f"Mag 7 combined: **${mag7_total:.1f}T** — **{_mag7_pct:.0f}%** of estimated S&P 500 "
                f"float market cap (${_sp500_mc_T:.0f}T, live via index level). "
                f"At dot-com peak, top 5 were ~18% of S&P 500 — current Mag 7 concentration is "
                f"**{_vs_dotcom:.1f}×** the dot-com level. "
                f"(S&P 500 total estimated using index level × divisor method; approximate.)"
            )
        else:
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
    "Expense ratio: 0.75% · Inception: May 2023. "
    "[Fund details →](https://www.roundhillinvestments.com/etf/chat/)"
)
st.markdown(
    "**Why track CHAT?** "
    "CHAT is the closest pure-play ETF to the AI infrastructure thesis this dashboard monitors. "
    "Its price action reflects market consensus on the generative AI value chain — "
    "a useful cross-check against the individual signals tracked above."
)

try:
    import yfinance as yf
    import requests as _req
    import concurrent.futures as _cf

    # ── Fetch summary info ──
    _chat_etf = yf.Ticker("CHAT")
    _chat_info = _chat_etf.info
    _chat_price = _chat_info.get("regularMarketPrice") or _chat_info.get("previousClose")
    _chat_aum = _chat_info.get("totalAssets")
    _chat_ytd = _chat_info.get("ytdReturn")
    _chat_52lo = _chat_info.get("fiftyTwoWeekLow")
    _chat_52hi = _chat_info.get("fiftyTwoWeekHigh")

    # ── Fetch holdings ──
    df_hold = None
    try:
        _qs = _req.get(
            "https://query2.finance.yahoo.com/v10/finance/quoteSummary/CHAT",
            params={"modules": "topHoldings"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if _qs.status_code == 200:
            _raw = (_qs.json().get("quoteSummary", {})
                              .get("result", [{}])[0]
                              .get("topHoldings", {})
                              .get("holdings", []))
            if _raw:
                df_hold = pd.DataFrame([{
                    "Ticker": h.get("symbol", ""),
                    "Name":   h.get("holdingName", ""),
                    "_weight_raw": h.get("holdingPercent", {}).get("raw", 0),
                } for h in _raw])
    except Exception:
        pass

    # Fallback to yfinance funds_data
    if df_hold is None or df_hold.empty:
        _chat_hd = _chat_etf.get_funds_data()
        if hasattr(_chat_hd, "top_holdings") and _chat_hd.top_holdings is not None:
            df_hold = _chat_hd.top_holdings.copy().reset_index()
            df_hold.columns = ["Ticker", "Name", "_weight_raw"]

    # ── Parallel PE fetch + weighted avg forward PE ──
    wtd_fwd_pe = None
    _pe_map = {}
    _pe_pairs = []
    if df_hold is not None and not df_hold.empty:
        def _fetch_pe(sym):
            try:
                info = yf.Ticker(sym).info
                fpe = info.get("forwardPE")
                tpe = info.get("trailingPE")
                fpe_raw = fpe if fpe and 0 < fpe < 5000 else None
                tpe_raw = tpe if tpe and 0 < tpe < 5000 else None
                return sym, (
                    f"{fpe_raw:.1f}x" if fpe_raw else "—",
                    f"{tpe_raw:.1f}x" if tpe_raw else "—",
                    fpe_raw,
                )
            except Exception:
                return sym, ("—", "—", None)

        with _cf.ThreadPoolExecutor(max_workers=8) as _pool:
            _pe_map = dict(_pool.map(_fetch_pe, df_hold["Ticker"].tolist()))

        # Weighted average forward PE (US listings only — non-US return None)
        _pe_pairs = [
            (row["_weight_raw"], _pe_map.get(row["Ticker"], ("—", "—", None))[2])
            for _, row in df_hold.iterrows()
        ]
        _covered = [(w, pe) for w, pe in _pe_pairs if pe is not None]
        if _covered:
            _cov_w = sum(w for w, _ in _covered)
            wtd_fwd_pe = sum(w * pe for w, pe in _covered) / _cov_w if _cov_w else None

        # Format display columns (after weighted PE calc, so _weight_raw still available above)
        df_hold["Weight"] = df_hold["_weight_raw"].apply(lambda x: f"{x * 100:.1f}%")
        df_hold = df_hold.drop(columns=["_weight_raw"])
        df_hold["Fwd P/E"]   = df_hold["Ticker"].map(lambda s: _pe_map.get(s, ("—", "—", None))[0])
        df_hold["Trail P/E"] = df_hold["Ticker"].map(lambda s: _pe_map.get(s, ("—", "—", None))[1])

    # ── Metric tiles ──
    col_chat1, col_chat2, col_chat3, col_chat4 = st.columns(4)
    if _chat_price:
        col_chat1.metric("Price", f"${_chat_price:.2f}")
    if _chat_aum:
        col_chat2.metric("AUM", f"${_chat_aum / 1e9:.2f}B")
    if wtd_fwd_pe is not None:
        col_chat3.metric("Wtd Avg Fwd PE", f"{wtd_fwd_pe:.1f}x")
    if _chat_ytd is not None:
        col_chat4.metric("YTD Return", f"{_chat_ytd * 100:+.1f}%")

    # ── 52-week range (above the table) ──
    col_rng, _ = st.columns([2, 1])
    with col_rng:
        if _chat_52lo and _chat_52hi and _chat_price:
            pct_of_range = (
                (_chat_price - _chat_52lo) / (_chat_52hi - _chat_52lo) * 100
                if _chat_52hi > _chat_52lo else 50
            )
            _dot_pct = min(max(pct_of_range, 2), 98)
            st.markdown("**52-Week Range**")
            st.markdown(
                f"""<div style="padding:2px 0 14px 0;">
  <div style="display:flex;justify-content:space-between;font-size:0.78em;color:#9ca3af;margin-bottom:8px;">
    <div><div style="font-size:1.1em;color:#e5e7eb;font-weight:600;">${_chat_52lo:.2f}</div>52W Low</div>
    <div style="text-align:right"><div style="font-size:1.1em;color:#e5e7eb;font-weight:600;">${_chat_52hi:.2f}</div>52W High</div>
  </div>
  <div style="background:#374151;border-radius:6px;height:8px;position:relative;margin:0 2px;">
    <div style="position:absolute;left:{_dot_pct:.1f}%;transform:translateX(-50%);
                width:14px;height:14px;background:#3b82f6;border-radius:50%;top:-3px;
                box-shadow:0 0 8px rgba(59,130,246,0.6);"></div>
  </div>
  <div style="font-size:0.82em;color:#d1d5db;margin-top:10px;">
    Current: <strong>${_chat_price:.2f}</strong> &nbsp;·&nbsp; {pct_of_range:.0f}% of range
  </div>
</div>""",
                unsafe_allow_html=True,
            )
    # ── Holdings table ──
    if df_hold is not None and not df_hold.empty:
        _n_covered = sum(1 for _, pe in _pe_pairs if pe is not None)
        _pe_note = f"P/E unavailable for non-US listings (HK, KS) · Wtd avg fwd PE covers {_n_covered}/{len(_pe_pairs)} holdings"
        st.caption(f"Top {len(df_hold)} holdings · {_pe_note}")
        st.dataframe(df_hold, use_container_width=True, hide_index=True)
    else:
        st.info("Holdings data not available.")

except Exception as e:
    st.warning(f"Could not fetch CHAT ETF data: {e}")
