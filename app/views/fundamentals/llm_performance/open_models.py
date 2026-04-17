"""Open Models — growth of open-weight models vs proprietary and the US/China race."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, PROVIDER_COLOURS,
    fetch_zeroeval_models, preprocess_ze, chart_layout, sota_prog,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()

st.title("Open Models")
st.caption(
    "How open-weight models are growing, how close they are to proprietary systems, "
    "and where the open race is happening."
)

if ze_df.empty or df.empty:
    st.info("Live data unavailable — ZeroEval API offline.")
else:
    ql = df.groupby(["quarter", "is_open"]).size().reset_index(name="count")
    ql["pct"] = ql.groupby("quarter")["count"].transform(lambda x: x / x.sum() * 100)
    fig_open = go.Figure()
    for lic, colour in [("Open Source", "#10b981"), ("Proprietary", "#f59e0b")]:
        sub = ql[ql["is_open"] == lic]
        fig_open.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["pct"], name=lic,
            mode="lines+markers", line=dict(color=colour, width=2),
            hovertemplate=f"{lic}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_open.update_layout(
        title="Open vs Proprietary Releases (%)",
        yaxis_title="Share (%)",
        height=320,
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_open, use_container_width=True)

    fig_gap = go.Figure()
    for grp, colour in [("Proprietary", "#f59e0b"), ("Open Source", "#10b981")]:
        prog = sota_prog(df[df["is_open"] == grp], "gpqa_score")
        if prog.empty:
            continue
        prog_ext = pd.concat(
            [prog, pd.DataFrame([{"date": df["release_date"].max(), "score": prog["score"].iloc[-1], "model": ""}])],
            ignore_index=True,
        )
        fig_gap.add_trace(go.Scatter(
            x=prog_ext["date"], y=prog_ext["score"], name=grp,
            mode="lines", line=dict(color=colour, width=2, shape="hv"),
            hovertemplate=f"{grp} SOTA: %{{y:.1f}}%<extra></extra>",
        ))
    fig_gap.update_layout(
        title="The Closing Gap — GPQA SOTA",
        yaxis_title="GPQA Score (%)",
        height=320,
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_gap, use_container_width=True)

    df["race_grp"] = df.apply(
        lambda r: f"{'US' if r['country'] == 'US' else 'CN'} {r['is_open']}"
        if r["country"] in ("US", "CN") else None, axis=1)
    fig_race = go.Figure()
    for grp, colour in [
        ("US Open Source", "#10b981"), ("US Proprietary", "#3b82f6"),
        ("CN Open Source", "#f59e0b"), ("CN Proprietary", "#ef4444"),
    ]:
        mask = df["race_grp"] == grp
        if not mask.any():
            continue
        prog = sota_prog(df[mask], "gpqa_score")
        if prog.empty:
            continue
        prog_ext = pd.concat(
            [prog, pd.DataFrame([{"date": df["release_date"].max(), "score": prog["score"].iloc[-1], "model": ""}])],
            ignore_index=True,
        )
        fig_race.add_trace(go.Scatter(
            x=prog_ext["date"], y=prog_ext["score"], name=grp,
            mode="lines", line=dict(color=colour, width=2, shape="hv"),
            hovertemplate=f"{grp}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_race.update_layout(
        title="Open Weights Race: US vs China (GPQA SOTA)",
        yaxis_title="GPQA Score (%)",
        yaxis_range=[0, 105],
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_race, use_container_width=True)
    st.caption(ATTR)
