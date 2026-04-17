"""Model Capabilities — capability progression, model type mix, and architectural shifts."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, CAPABILITY_MILESTONES,
    fetch_zeroeval_models, preprocess_ze, chart_layout, explainer,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()

st.title("Model Capabilities")
st.caption("Capability progression, model type mix, and architectural shifts.")

st.subheader("Task Complexity Over Time")
explainer(
    what="Qualitative capability progression of frontier AI systems, from few-shot learning (GPT-3, 2020) to autonomous reasoning agents (Claude 4, Grok 4). Each point marks a distinct capability milestone.",
    why="Benchmark scores plateau and reset; capability steps do not. This chart answers 'what can models *do* now that they couldn't 12 months ago?' — the question investors actually care about.",
    source="Hand-curated from provider release announcements. Complexity levels are qualitative, not a measured metric.",
)
fig_complexity = go.Figure()
fig_complexity.add_trace(go.Scatter(
    x=[m["date"] for m in CAPABILITY_MILESTONES],
    y=[m["complexity"] for m in CAPABILITY_MILESTONES],
    text=[m["event"] for m in CAPABILITY_MILESTONES],
    mode="lines+markers",
    line=dict(color="#f59e0b", width=2, shape="spline"),
    marker=dict(size=8, color="#f59e0b"),
    hovertemplate="%{text}<br>Complexity: %{y}<extra></extra>",
))
fig_complexity.update_layout(
    yaxis_title="Capability Level",
    yaxis_range=[0, 10],
    showlegend=False,
    **CHART_LAYOUT,
)
st.plotly_chart(fig_complexity, use_container_width=True)

if not ze_df.empty and not df.empty:
    qmm = (df.groupby("quarter").apply(
        lambda g: pd.Series({
            "Multimodal": (g["multimodal"] == True).sum() / len(g) * 100,  # noqa: E712
            "Text-only":  (g["multimodal"] != True).sum() / len(g) * 100,  # noqa: E712
        })).reset_index().melt(id_vars="quarter", var_name="type", value_name="pct"))
    fig_mm = go.Figure()
    for typ, colour in [("Multimodal", "#8b5cf6"), ("Text-only", "#3b82f6")]:
        sub = qmm[qmm["type"] == typ]
        fig_mm.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["pct"], name=typ,
            mode="lines+markers", line=dict(color=colour, width=2),
            hovertemplate=f"{typ}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_mm.update_layout(
        title="The Multimodal Shift",
        yaxis_title="% of New Releases",
        height=320,
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_mm, use_container_width=True)

    moe_df = df[df["is_open"] == "Open Source"].dropna(subset=["gpqa_score"]).copy()
    if not moe_df.empty:
        moe_df["arch"] = moe_df["is_moe"].apply(lambda x: "MoE" if x is True else "Dense")
        fig_moe = go.Figure()
        for arch, colour in [("MoE", "#10b981"), ("Dense", "#6b7280")]:
            sub = moe_df[moe_df["arch"] == arch]
            fig_moe.add_trace(go.Scatter(
                x=sub["release_date"], y=sub["gpqa_score"] * 100, text=sub["name"],
                name=arch, mode="markers",
                marker=dict(color=colour, size=8, opacity=0.8),
                hovertemplate="%{text}: %{y:.1f}%<extra></extra>",
            ))
        fig_moe.update_layout(
            title="MoE Adoption — Open Models",
            xaxis_title="",
            xaxis_range=["2023-01-01", None],
            yaxis_title="GPQA Score (%)",
            height=320,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_moe, use_container_width=True)
    st.caption(ATTR)
