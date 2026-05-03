"""Speed and Context — throughput, context length, and the speed/capability trade-off."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, CONTEXT_WINDOWS, PROVIDER_COLOURS,
    fetch_zeroeval_models, preprocess_ze, chart_layout,
    provider_sidebar,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()
sel_providers = provider_sidebar()

st.title("Speed and Context")
st.caption(
    "What you trade off when deploying models: context length, throughput, "
    "and how much speed costs in capability."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pareto_decreasing(data: pd.DataFrame, x_col: str, y_col: str) -> pd.DataFrame:
    """Pareto frontier: best y at each x level (decreasing curve left→right)."""
    d = data.dropna(subset=[x_col, y_col]).sort_values(x_col, ascending=False)
    best_y: float = -1e9
    rows: list = []
    for _, r in d.iterrows():
        if r[y_col] > best_y:
            best_y = r[y_col]
            rows.append(r)
    return pd.DataFrame(rows[::-1])


def _scatter_by_provider(
    data: pd.DataFrame,
    score_col: str,
    y_label: str,
    *,
    log_x: bool = False,
    height: int = 360,
) -> go.Figure:
    """Scatter chart colored by provider with decreasing Pareto frontier."""
    fig = go.Figure()
    known = set(PROVIDER_COLOURS.keys())

    for prov in PROVIDER_COLOURS:
        if prov not in sel_providers:
            continue
        sub = data[data["provider"] == prov]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["throughput"], y=sub[score_col] * 100,
            text=sub["name"], name=prov, mode="markers",
            marker=dict(color=PROVIDER_COLOURS[prov], size=7, opacity=0.8),
            hovertemplate="%{text}<br>%{x:.0f} tok/s · %{y:.1f}%<extra></extra>",
        ))

    others = data[~data["provider"].isin(known)]
    if not others.empty:
        fig.add_trace(go.Scatter(
            x=others["throughput"], y=others[score_col] * 100,
            text=others["name"], name="Others", mode="markers",
            marker=dict(color="#6b7280", size=6, opacity=0.6),
            hovertemplate="%{text}<br>%{x:.0f} tok/s · %{y:.1f}%<extra></extra>",
        ))

    pf = _pareto_decreasing(data, "throughput", score_col)
    if not pf.empty:
        fig.add_trace(go.Scatter(
            x=pf["throughput"], y=pf[score_col] * 100,
            mode="lines", showlegend=False,
            line=dict(color="#3b82f6", width=2),
        ))

    layout_kw: dict = dict(
        xaxis_title="Throughput (tokens/sec)",
        yaxis_title=y_label,
        height=height,
        **CHART_LAYOUT,
    )
    if log_x:
        layout_kw["xaxis_type"] = "log"
    fig.update_layout(**layout_kw)
    return fig


# ---------------------------------------------------------------------------
# Row 1 — The Context Race  +  The Speed Tax
# ---------------------------------------------------------------------------
col_ctx, col_tax = st.columns(2)

with col_ctx:
    st.markdown("**The Context Race**")
    st.caption("Maximum context window over time — each step is a new record")

    sorted_cw = sorted(CONTEXT_WINDOWS, key=lambda r: r["date"])
    records: list[dict] = []
    max_tok = 0
    for r in sorted_cw:
        if r["tokens"] > max_tok:
            max_tok = r["tokens"]
            records.append(r)

    fig_ctx = go.Figure()

    # Scatter dots for all known models -----------------------------------------
    if not df.empty and "context" in df.columns:
        ctx_data = df.dropna(subset=["release_date", "context"])
        ctx_data = ctx_data[ctx_data["context"] > 0]
        if not ctx_data.empty:
            for typ, colour in [("Open source", "#10b981"), ("Proprietary", "#9ca3af")]:
                label = "Open Source" if typ == "Open source" else "Proprietary"
                sub = ctx_data[ctx_data["is_open"] == label]
                if sub.empty:
                    continue
                fig_ctx.add_trace(go.Scatter(
                    x=sub["release_date"], y=sub["context"],
                    text=sub["name"], name=typ, mode="markers",
                    marker=dict(color=colour, size=5, opacity=0.5),
                    hovertemplate="%{text}<br>%{y:,.0f} tokens<extra></extra>",
                ))
    else:
        fig_ctx.add_trace(go.Scatter(
            x=[r["date"] for r in sorted_cw],
            y=[r["tokens"] for r in sorted_cw],
            text=[r["model"] for r in sorted_cw],
            mode="markers", showlegend=False,
            marker=dict(color="#6b7280", size=5, opacity=0.45),
            hovertemplate="%{text}<br>%{y:,.0f} tokens<extra></extra>",
        ))

    # Record-breaking step line -------------------------------------------------
    fig_ctx.add_trace(go.Scatter(
        x=[r["date"] for r in records],
        y=[r["tokens"] for r in records],
        text=[r["model"] for r in records],
        mode="lines+markers+text",
        line=dict(color="#f59e0b", width=2.5, shape="hv"),
        marker=dict(color="#f59e0b", size=8),
        textposition="top left",
        textfont=dict(size=10, color="#d1d5db"),
        showlegend=False,
        hovertemplate="%{text}<br>%{y:,.0f} tokens<extra></extra>",
    ))

    current = records[-1]
    fig_ctx.update_layout(
        yaxis_title="Context Window (tokens)",
        yaxis_type="log",
        height=360,
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_ctx, use_container_width=True)
    st.caption(
        f"Current record: {current['model']} at "
        f"{current['tokens'] / 1e6:.1f}M tokens"
    )

with col_tax:
    st.markdown("**The Speed Tax**")
    st.caption(
        "The tradeoff between intelligence and speed "
        "— faster models are rarely the smartest"
    )

    if not ze_df.empty and not df.empty:
        sp = df.dropna(subset=["gpqa_score", "throughput"])
        sp = sp[sp["throughput"] > 0].copy()
        if not sp.empty:
            fig_tax = _scatter_by_provider(
                sp, "gpqa_score", "GPQA Score (%)", log_x=True,
            )
            st.plotly_chart(fig_tax, use_container_width=True)
            pf = _pareto_decreasing(sp, "throughput", "gpqa_score")
            if not pf.empty:
                best = pf.iloc[0]
                st.caption(
                    f"Pareto-optimal: {best['name']} — "
                    f"{best['gpqa_score'] * 100:.1f}% GPQA "
                    f"at {best['throughput']:.0f} tok/s"
                )


# ---------------------------------------------------------------------------
# Row 2 — Throughput Frontiers
# ---------------------------------------------------------------------------
if not ze_df.empty and not df.empty:
    st.subheader("Throughput Frontiers")
    st.caption("Capability vs inference speed across benchmarks")

    col_gpqa, col_swe = st.columns(2)

    with col_gpqa:
        sp2 = df.dropna(subset=["gpqa_score", "throughput"])
        sp2 = sp2[sp2["throughput"] > 0].copy()
        if not sp2.empty:
            st.markdown("**GPQA Score (%) vs Throughput (tokens/sec)**")
            st.caption("Pareto frontier analysis")
            fig_g = _scatter_by_provider(sp2, "gpqa_score", "GPQA Score (%)")
            st.plotly_chart(fig_g, use_container_width=True)

    with col_swe:
        ss = df.dropna(subset=["swe_bench_verified_score", "throughput"])
        ss = ss[ss["throughput"] > 0].copy()
        if not ss.empty:
            st.markdown("**SWE-Bench Verified (%) vs Throughput (tokens/sec)**")
            st.caption("Pareto frontier analysis")
            fig_s = _scatter_by_provider(
                ss, "swe_bench_verified_score", "SWE-Bench Verified (%)",
            )
            st.plotly_chart(fig_s, use_container_width=True)

st.caption(ATTR)
