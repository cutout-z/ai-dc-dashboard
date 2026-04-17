"""Benchmark Performance — frontier capability improvement and convergence."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, BENCH_MAP, PROVIDER_COLOURS, ORG_TO_PROVIDER,
    fetch_zeroeval_models, preprocess_ze, chart_layout, sota_prog,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()

st.title("Benchmark Performance")
st.caption("How quickly frontier capability is improving, and how tightly packed the leaders have become.")

if ze_df.empty or df.empty:
    st.info("Live data unavailable — ZeroEval API offline.")
else:
    _BENCH_COLOURS = px.colors.qualitative.Dark24

    st.subheader("Benchmark Saturation")
    st.caption("SOTA score progression over time — each step is a new best model.")
    fig_sat = go.Figure()
    for i, (col, label) in enumerate(BENCH_MAP.items()):
        prog = sota_prog(df, col)
        if prog.empty:
            continue
        colour = _BENCH_COLOURS[i % len(_BENCH_COLOURS)]
        prog_ext = pd.concat(
            [prog, pd.DataFrame([{"date": df["release_date"].max(), "score": prog["score"].iloc[-1], "model": ""}])],
            ignore_index=True,
        )
        fig_sat.add_trace(go.Scatter(
            x=prog_ext["date"], y=prog_ext["score"],
            name=label, mode="lines",
            line=dict(color=colour, width=1.5, shape="hv"),
            hovertemplate=f"{label}: %{{y:.1f}}%<br>%{{x|%b %Y}}<extra></extra>",
        ))
    fig_sat.update_layout(yaxis_title="SOTA Score (%)", yaxis_range=[0, 105], **CHART_LAYOUT)
    st.plotly_chart(fig_sat, use_container_width=True)
    st.caption(ATTR)

    st.subheader("The Convergence")
    st.caption("The gap between the #1 and #10 GPQA score — the frontier is getting crowded.")
    gpqa_valid = df.dropna(subset=["gpqa_score"]).sort_values("release_date")
    conv_rows = []
    for dt in gpqa_valid["release_date"].unique():
        pool = gpqa_valid[gpqa_valid["release_date"] <= dt]["gpqa_score"].sort_values(ascending=False)
        if len(pool) >= 10:
            conv_rows.append({"date": dt, "rank": "#1",  "score": pool.iloc[0] * 100})
            conv_rows.append({"date": dt, "rank": "#10", "score": pool.iloc[9] * 100})
    if conv_rows:
        conv_df = pd.DataFrame(conv_rows)
        fig_conv = go.Figure()
        for rank, colour in [("#1", "#3b82f6"), ("#10", "#8b5cf6")]:
            sub = conv_df[conv_df["rank"] == rank]
            fig_conv.add_trace(go.Scatter(
                x=sub["date"], y=sub["score"], name=rank,
                mode="lines+markers", line=dict(color=colour, width=2, shape="hv"),
                hovertemplate=f"{rank} GPQA: %{{y:.1f}}%<extra></extra>",
            ))
        fig_conv.update_layout(yaxis_title="GPQA Score (%)", **CHART_LAYOUT)
        st.plotly_chart(fig_conv, use_container_width=True)
        st.caption(ATTR)

    st.subheader("Lab Progress")
    st.caption("GPQA and SWE-Bench improvement over the last 12 months")
    cutoff_12mo = pd.Timestamp.today() - pd.DateOffset(months=12)
    col_lab1, col_lab2 = st.columns(2)
    for col_ui, (score_col, label, gain_color) in zip(
        [col_lab1, col_lab2],
        [("gpqa_score", "GPQA · General Knowledge", "#22c55e"),
         ("swe_bench_verified_score", "SWE-Bench · Coding", "#3b82f6")],
    ):
        with col_ui:
            cur = (df.dropna(subset=[score_col])
                     .groupby("organization")[score_col].max()
                     .mul(100).reset_index()
                     .rename(columns={score_col: "current", "organization": "org"}))
            old = (df[df["release_date"] <= cutoff_12mo]
                     .dropna(subset=[score_col])
                     .groupby("organization")[score_col].max()
                     .mul(100).reset_index()
                     .rename(columns={score_col: "base", "organization": "org"}))
            lab = cur.merge(old, on="org", how="left")
            lab["base"] = lab["base"].fillna(0)
            lab["gain"] = lab["current"] - lab["base"]
            lab = lab.sort_values("current").tail(12)

            fig_lab = go.Figure()
            fig_lab.add_trace(go.Bar(
                x=lab["base"], y=lab["org"], orientation="h",
                marker_color="#6b7280", name="12mo ago",
                hovertemplate="%{y}: %{x:.1f}% (12mo ago)<extra></extra>",
            ))
            fig_lab.add_trace(go.Bar(
                x=lab["gain"], y=lab["org"], orientation="h",
                marker_color=gain_color, name="Gain",
                text=[f"{v:.0f}%" for v in lab["current"]],
                textposition="outside",
                hovertemplate="%{y}: +%{x:.1f}% gain<extra></extra>",
            ))
            fig_lab.update_layout(
                title=label,
                barmode="stack",
                xaxis=dict(tickformat=".0f", ticksuffix="%", range=[0, 108]),
                height=420,
                **CHART_LAYOUT,
            )
            st.plotly_chart(fig_lab, use_container_width=True)
    st.caption(ATTR)

    st.subheader("Organization Progress")
    st.caption("Best GPQA score per organisation over time.")
    top_orgs = (df.dropna(subset=["gpqa_score"]).groupby("organization")["gpqa_score"].max()
                  .sort_values(ascending=False).head(8).index.tolist())
    fig_org = go.Figure()
    for org in top_orgs:
        prog = sota_prog(df[df["organization"] == org], "gpqa_score")
        if prog.empty:
            continue
        colour = PROVIDER_COLOURS.get(ORG_TO_PROVIDER.get(org, ""), "#6b7280")
        prog_ext = pd.concat(
            [prog, pd.DataFrame([{"date": df["release_date"].max(), "score": prog["score"].iloc[-1], "model": ""}])],
            ignore_index=True,
        )
        fig_org.add_trace(go.Scatter(
            x=prog_ext["date"], y=prog_ext["score"], name=org,
            mode="lines", line=dict(color=colour, width=2, shape="hv"),
            hovertemplate=f"{org}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_org.update_layout(yaxis_title="GPQA Score (%)", **CHART_LAYOUT)
    st.plotly_chart(fig_org, use_container_width=True)
    st.caption(ATTR)
