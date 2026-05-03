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

# Benchmark descriptions — what each eval tests and why it matters
_BENCH_DESC: dict[str, str] = {
    "GPQA": "Graduate-level science questions (physics, chemistry, biology) designed to resist web search. Tests deep scientific reasoning.",
    "SWE-Bench": "Real GitHub issues from popular Python repos — models must write patches that pass the test suite. Tests practical software engineering.",
    "HLE": "Humanity\u2019s Last Exam — ~3,000 extremely hard questions across disciplines, crowdsourced from domain experts. Tests the outer limits of knowledge.",
    "AIME 2025": "American Invitational Mathematics Exam — 15 competition math problems requiring creative problem-solving. Answers are integers 000\u2013999.",
    "MMMLU": "Multilingual MMLU — knowledge & reasoning questions translated across 14 languages. Tests non-English understanding.",
    "SimpleQA": "Short factual questions with unambiguous answers. Tests factual accuracy and hallucination resistance.",
    "BrowseComp": "Questions requiring comprehensive web browsing to answer. Tests ability to find and synthesise information from the internet.",
    "Terminal Bench": "Tasks requiring terminal/shell use to accomplish goals. Tests command-line proficiency and system administration.",
    "MRCR v2": "Multi-Round Coreference Resolution — tracking entities across long, multi-turn conversations. Tests long-context recall accuracy.",
    "SciCode": "Scientific computing tasks — implementing algorithms from research papers in code. Tests translation of scientific methods into working programs.",
}

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
    st.caption(
        "**SOTA** (State of the Art) = the highest score any model has achieved on a benchmark to date. "
        "Each step in the chart is a new best model pushing the frontier."
    )
    _legend_items: list[tuple[str, str]] = []  # (label, colour)
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
        _legend_items.append((label, colour))
    sat_layout = {**CHART_LAYOUT}
    sat_layout["legend"] = dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
    sat_layout["showlegend"] = False  # replaced by custom HTML legend below
    fig_sat.update_layout(yaxis_title="SOTA Score (%)", yaxis_range=[0, 105], **sat_layout)
    st.plotly_chart(fig_sat, use_container_width=True, key="benchmark_saturation")

    # Custom HTML legend with CSS hover tooltips
    _tooltip_css = (
        "<style>"
        ".bench-legend{display:flex;flex-wrap:wrap;gap:6px 18px;padding:4px 0;}"
        ".bench-item{position:relative;display:inline-flex;align-items:center;gap:5px;"
        "font-size:13px;color:#e5e7eb;cursor:help;}"
        ".bench-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}"
        ".bench-item .bench-tip{visibility:hidden;opacity:0;position:absolute;"
        "bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);"
        "background:#1e293b;color:#e5e7eb;padding:8px 12px;border-radius:6px;"
        "font-size:12px;line-height:1.4;width:280px;z-index:999;"
        "box-shadow:0 4px 12px rgba(0,0,0,.4);pointer-events:none;"
        "transition:opacity .15s;white-space:normal;}"
        ".bench-item:hover .bench-tip{visibility:visible;opacity:1;}"
        "</style>"
    )
    _legend_html = '<div class="bench-legend">'
    for label, colour in _legend_items:
        desc = _BENCH_DESC.get(label, "")
        _legend_html += (
            f'<span class="bench-item">'
            f'<span class="bench-dot" style="background:{colour}"></span>{label}'
            f'<span class="bench-tip">{desc}</span>'
            f'</span>'
        )
    _legend_html += "</div>"
    st.markdown(_tooltip_css + _legend_html, unsafe_allow_html=True)
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
