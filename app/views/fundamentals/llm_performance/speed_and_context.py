"""Speed and Context — throughput, context length, and the speed/capability trade-off."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, CONTEXT_WINDOWS,
    fetch_zeroeval_models, preprocess_ze, chart_layout,
    explainer, provider_traces, pareto_front, provider_sidebar,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()
sel_providers = provider_sidebar()

st.title("Speed and Context")
st.caption(
    "What you trade off when deploying models: throughput, context length, "
    "and how speed costs capability."
)

st.subheader("Context Window Expansion")
explainer(
    what="Maximum prompt size each frontier model can process in a single call, plotted on a log scale. From 4K tokens (GPT-3) to 10M tokens (Llama 4 Maverick) — a ~2500x expansion in five years.",
    why="Context window is a hard constraint on what applications are possible. Long-context unlocks RAG-free codebases, whole-book summarisation, and multi-hour agent loops. The 'memory wall' has been the hardest architectural constraint to break.",
    source="Provider announcements and model cards. Context sizes are quoted maximums — effective context (where recall stays high) is often shorter.",
)
fig_ctx_win = go.Figure()
for trace in provider_traces(
    CONTEXT_WINDOWS, x_key="date", y_key="tokens",
    sel_providers=sel_providers,
    hover_fmt="%{text}<br>%{y:,.0f} tokens",
):
    fig_ctx_win.add_trace(trace)
fig_ctx_win.update_layout(yaxis_title="Context Window (tokens)", yaxis_type="log", **CHART_LAYOUT)
st.plotly_chart(fig_ctx_win, use_container_width=True)

if not ze_df.empty and not df.empty:
    sp = df.dropna(subset=["gpqa_score", "throughput"])
    sp = sp[sp["throughput"] > 0].copy()
    if not sp.empty:
        pf_sp = pareto_front(sp, "throughput", "gpqa_score")
        fig_sp = go.Figure()
        for typ, colour, sym in [("Open Source", "#10b981", "circle"), ("Proprietary", "#f59e0b", "diamond")]:
            sub = sp[sp["is_open"] == typ]
            fig_sp.add_trace(go.Scatter(
                x=sub["throughput"], y=sub["gpqa_score"] * 100, text=sub["name"],
                name=typ, mode="markers",
                marker=dict(color=colour, size=7, opacity=0.8, symbol=sym),
                hovertemplate="%{text}<br>%{x:.0f} tok/s · %{y:.1f}%<extra></extra>",
            ))
        if not pf_sp.empty:
            fig_sp.add_trace(go.Scatter(
                x=pf_sp["throughput"], y=pf_sp["gpqa_score"] * 100,
                mode="lines", showlegend=False,
                line=dict(color="#ffffff", width=1.5, dash="dot"),
            ))
        fig_sp.update_layout(
            title="The Speed Tax — GPQA vs Throughput",
            xaxis_title="Throughput (tok/s)",
            yaxis_title="GPQA Score (%)",
            height=360,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_sp, use_container_width=True)

    ss = df.dropna(subset=["swe_bench_verified_score", "throughput"])
    ss = ss[ss["throughput"] > 0].copy()
    if not ss.empty:
        pf_ss = pareto_front(ss, "throughput", "swe_bench_verified_score")
        fig_ss = go.Figure()
        for typ, colour in [("Open Source", "#10b981"), ("Proprietary", "#f59e0b")]:
            sub = ss[ss["is_open"] == typ]
            fig_ss.add_trace(go.Scatter(
                x=sub["throughput"], y=sub["swe_bench_verified_score"] * 100, text=sub["name"],
                name=typ, mode="markers",
                marker=dict(color=colour, size=7, opacity=0.8),
                hovertemplate="%{text}<br>%{x:.0f} tok/s · %{y:.1f}%<extra></extra>",
            ))
        if not pf_ss.empty:
            fig_ss.add_trace(go.Scatter(
                x=pf_ss["throughput"], y=pf_ss["swe_bench_verified_score"] * 100,
                mode="lines", showlegend=False,
                line=dict(color="#ffffff", width=1.5, dash="dot"),
            ))
        fig_ss.update_layout(
            title="SWE-Bench vs Throughput",
            xaxis_title="Throughput (tok/s)",
            yaxis_title="SWE-Bench Score (%)",
            height=360,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_ss, use_container_width=True)
    st.caption(ATTR)
