"""Human Preference — Arena Elo ratings and benchmark vs human preference map."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, BENCH_COLS, PROVIDER_COLOURS, ORG_TO_PROVIDER,
    fetch_zeroeval_models, preprocess_ze, load_arena_elo,
    chart_layout, explainer, provider_sidebar,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
df_elo = load_arena_elo()
CHART_LAYOUT = chart_layout()
sel_providers = provider_sidebar()

st.title("Human Preference")
st.caption("How models rank when humans judge them head-to-head, vs. how they score on automated benchmarks.")

st.subheader("Arena Elo Ratings")
explainer(
    what="Chatbot Arena (lmsys.org) Elo scores — a head-to-head blind preference tournament where humans choose between model responses. Elo is computed from win rates across millions of votes.",
    why="Human preference Elo is the most neutral capability signal available. It has no benchmark contamination problem and aligns with what users actually prefer. It's the one metric all providers accept as credible.",
    source="LMSYS Chatbot Arena leaderboard (chat.lmsys.org). Updated via /ai-research skill.",
)
if not df_elo.empty:
    vis = [p for p in df_elo["provider"].unique() if p in sel_providers] if sel_providers else df_elo["provider"].unique().tolist()
    df_elo_vis = df_elo[df_elo["provider"].isin(vis)] if vis else df_elo
    elo_top = df_elo_vis.head(15).copy()
    elo_min = elo_top["elo"].min()
    elo_floor = round(elo_min * 0.95)
    elo_top["elo_offset"] = elo_top["elo"] - elo_floor
    fig_elo = px.bar(
        elo_top, x="elo_offset", y="model", color="provider",
        orientation="h", title="Top 15 by Elo",
        text="elo", custom_data=["elo"],
        color_discrete_map=PROVIDER_COLOURS,
    )
    fig_elo.update_traces(
        base=elo_floor, textposition="outside", textfont_size=10,
        hovertemplate="Elo Score=%{customdata[0]}<br>model=%{y}<extra></extra>",
    )
    fig_elo.update_layout(
        height=450,
        yaxis=dict(autorange="reversed"),
        xaxis=dict(title_text="Elo Score"),
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_elo, use_container_width=True)
else:
    st.info("Arena Elo data not yet loaded. Run /ai-research to populate.")

st.subheader("Human Preference Map")
explainer(
    what="Each dot is a model. X-axis: composite benchmark score (mean of GPQA, SWE-Bench, HLE, AIME-2025). Y-axis: Chatbot Arena Elo — human-rated preference from blind head-to-head votes. Hover for model name.",
    why="A model can ace benchmarks but rank poorly on human preference (e.g. too terse, poor formatting). The map shows whether labs are optimising for benchmark leaderboards or real-world usability, and which models are genuinely best by both measures.",
    source="Benchmark scores: api.zeroeval.com. Arena Elo: LMSYS Chatbot Arena — updated via /ai-research skill.",
)
if not df_elo.empty and not ze_df.empty and not df.empty:
    bench_score = df[["name", "organization"] + BENCH_COLS].copy()
    bench_score["composite"] = bench_score[BENCH_COLS].mean(axis=1, skipna=True).mul(100)
    bench_score = bench_score.dropna(subset=["composite"])
    bench_score["provider"] = bench_score["organization"].map(ORG_TO_PROVIDER).fillna(bench_score["organization"])

    def _norm_key(s: str) -> str:
        return "".join(c for c in str(s).lower() if c.isalnum())

    bench_score["_key"] = bench_score["name"].apply(_norm_key)
    elo_join = df_elo.copy()
    elo_join["_norm"] = elo_join["model"].apply(_norm_key)

    elo_lookup: dict[str, float] = {}
    for _, er in elo_join.iterrows():
        if pd.notna(er["elo"]):
            elo_lookup[er["_norm"]] = max(elo_lookup.get(er["_norm"], 0), float(er["elo"]))

    def _best_elo(bkey: str) -> float | None:
        if bkey in elo_lookup:
            return elo_lookup[bkey]
        hits = [v for k, v in elo_lookup.items() if k.startswith(bkey) or bkey.startswith(k)]
        return max(hits) if hits else None

    bench_score["elo"] = bench_score["_key"].apply(_best_elo)
    hp = bench_score.dropna(subset=["elo", "composite"])
    if not hp.empty:
        fig_hp = go.Figure()
        for prov in sorted(hp["provider"].unique()):
            sub = hp[hp["provider"] == prov]
            fig_hp.add_trace(go.Scatter(
                x=sub["composite"], y=sub["elo"], text=sub["name"],
                name=prov, mode="markers", showlegend=False,
                marker=dict(
                    color=PROVIDER_COLOURS.get(prov, "#6b7280"), size=9, opacity=0.85,
                    line=dict(width=1, color="rgba(255,255,255,0.3)"),
                ),
                hovertemplate="%{text}<br>Composite: %{x:.1f}%<br>Elo: %{y:,d}<extra></extra>",
            ))
        fig_hp.update_layout(
            xaxis_title="Composite Benchmark Score (%)",
            yaxis_title="Arena Elo (Human Preference)",
            height=480,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_hp, use_container_width=True)
        st.caption(ATTR + " · Arena Elo from LMSYS Chatbot Arena via /ai-research skill.")
    else:
        st.info("No model overlap between ZeroEval benchmarks and Arena Elo — run /ai-research to populate Arena Elo.")
else:
    st.info("Arena Elo data not yet loaded. Run /ai-research to populate.")

st.markdown("---")
st.caption(
    "Data sources: LLM Stats / api.zeroeval.com (benchmark scores) · "
    "LMSYS Chatbot Arena (Arena Elo). Benchmark scores are vendor-reported unless otherwise noted."
)
