"""Efficiency and Scale — how architecture, parameters, and training scale affect capability."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, PROVIDER_COLOURS,
    fetch_zeroeval_models, preprocess_ze, chart_layout,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()

st.title("Efficiency and Scale")
st.caption("How architecture, parameters, and training scale affect capability.")

if ze_df.empty or df.empty:
    st.info("Live data unavailable — ZeroEval API offline.")
else:
    mp = df.dropna(subset=["gpqa_score", "blended_price"])
    mp = mp[mp["blended_price"] > 0].copy()
    if not mp.empty:
        mp["arch"] = mp["is_moe"].apply(lambda x: "MoE" if x is True else "Dense")
        fig_moe_p = go.Figure()
        for arch, colour in [("MoE", "#10b981"), ("Dense", "#6b7280")]:
            sub = mp[mp["arch"] == arch]
            fig_moe_p.add_trace(go.Scatter(
                x=sub["blended_price"], y=sub["gpqa_score"] * 100, text=sub["name"],
                name=arch, mode="markers",
                marker=dict(color=colour, size=7, opacity=0.8),
                hovertemplate="%{text}<br>$%{x:.3f}/M · %{y:.1f}%<extra></extra>",
            ))
        fig_moe_p.update_layout(
            title="Performance vs Price by Architecture (MoE vs Dense)",
            xaxis_title="Blended Price ($/1M tokens)",
            xaxis_type="log",
            yaxis_title="GPQA Score (%)",
            height=360,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_moe_p, use_container_width=True)

    t2 = df.dropna(subset=["gpqa_score", "params"])
    t2 = t2[t2["params"] > 0].copy()
    if not t2.empty:
        t2["tier"] = pd.cut(
            t2["params"],
            bins=[0, 10e9, 70e9, 200e9, float("inf")],
            labels=["Tiny (<10B)", "Small (10–70B)", "Large (70–200B)", "Frontier (200B+)"],
        )
        fig_t2 = go.Figure()
        for tier_lbl, colour in [
            ("Tiny (<10B)", "#6b7280"), ("Small (10–70B)", "#3b82f6"),
            ("Large (70–200B)", "#f59e0b"), ("Frontier (200B+)", "#ef4444"),
        ]:
            sub = t2[t2["tier"].astype(str) == tier_lbl]
            if sub.empty:
                continue
            fig_t2.add_trace(go.Box(
                x=sub["tier"].astype(str), y=sub["gpqa_score"] * 100, name=tier_lbl,
                boxpoints="all", jitter=0.5, pointpos=0,
                marker_color=colour, marker_size=5,
                text=sub["name"].tolist(),
                hovertemplate="%{text}: %{y:.1f}%<extra></extra>",
            ))
        fig_t2.update_layout(
            title="GPQA Score by Model Size Tier",
            xaxis_title="Model Tier",
            yaxis_title="GPQA Score (%)",
            showlegend=False,
            height=360,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_t2, use_container_width=True)

    st.subheader("The Efficiency Curve")
    st.caption("Smallest model to reach each GPQA threshold — intelligence is getting smaller.")
    eff = df.dropna(subset=["gpqa_score", "params"])
    eff = eff[eff["params"] > 0].sort_values("release_date")
    if not eff.empty:
        fig_eff = go.Figure()
        for thresh, colour in [
            (0.4, "#6b7280"), (0.5, "#3b82f6"), (0.6, "#10b981"),
            (0.7, "#f59e0b"), (0.8, "#ef4444"),
        ]:
            above = eff[eff["gpqa_score"] >= thresh]
            if above.empty:
                continue
            rows, min_p = [], float("inf")
            for _, r in above.iterrows():
                if r["params"] < min_p:
                    min_p = r["params"]
                    rows.append({"date": r["release_date"], "params": min_p, "model": r["name"]})
            if not rows:
                continue
            ep = pd.DataFrame(rows)
            ep_ext = pd.concat(
                [ep, pd.DataFrame([{"date": df["release_date"].max(), "params": ep["params"].iloc[-1], "model": ""}])],
                ignore_index=True,
            )
            fig_eff.add_trace(go.Scatter(
                x=ep_ext["date"], y=ep_ext["params"],
                name=f"{int(thresh*100)}% GPQA", mode="lines",
                line=dict(color=colour, width=2, shape="hv"),
                hovertemplate=f"{int(thresh*100)}% GPQA: %{{y:.2e}} params<extra></extra>",
            ))
        fig_eff.update_layout(yaxis_title="Parameters", yaxis_type="log", **CHART_LAYOUT)
        st.plotly_chart(fig_eff, use_container_width=True)
    st.caption(ATTR)
