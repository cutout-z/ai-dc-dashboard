"""Prices and Value — API cost trends, price frontiers, and intelligence per dollar."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, PROVIDER_COLOURS,
    fetch_zeroeval_models, preprocess_ze, load_token_prices,
    chart_layout, explainer, pareto_front, provider_sidebar,
)

ze_df = fetch_zeroeval_models()
df, df_specs = preprocess_ze(ze_df)
token_df = load_token_prices()
CHART_LAYOUT = chart_layout()
sel_providers = provider_sidebar()

st.title("Prices and Value")
st.caption("How fast intelligence is getting cheaper, which models deliver the most value, and where prices differ.")

if not token_df.empty:
    st.subheader("Blended API Cost Over Time")
    explainer(
        what="API list price per million tokens for flagship frontier models at release, blended as (3×input + output)/4 to approximate a typical chat workload. Log scale.",
        why="Costs have fallen ~1000× since GPT-3 (2020). Epoch AI estimates 'price to match GPT-4 quality' has declined ~40× per year. This is the single most important variable in AI unit economics — it determines which applications are deployable and at what margin.",
        source="List prices from provider announcements & release blog posts. Open-weight models (Llama, Qwen) priced via major hosted providers (Together AI, DashScope). Snapshot at release — later price cuts not shown.",
    )
    fig_price = go.Figure()
    for provider in PROVIDER_COLOURS:
        if provider not in sel_providers:
            continue
        sub = token_df[token_df["provider"] == provider]
        if sub.empty:
            continue
        fig_price.add_trace(go.Scatter(
            x=sub["date"], y=sub["blended_usd_per_mtok"], text=sub["model"],
            customdata=sub[["input_usd_per_mtok", "output_usd_per_mtok"]].values,
            name=provider, mode="markers+lines",
            line=dict(color=PROVIDER_COLOURS[provider], width=1.2),
            marker=dict(size=8, color=PROVIDER_COLOURS[provider]),
            hovertemplate=(
                "%{text}<br>Blended: $%{y:.2f} / M tokens<br>"
                "Input: $%{customdata[0]:.2f}<br>"
                "Output: $%{customdata[1]:.2f}"
                f"<extra>{provider}</extra>"
            ),
        ))
    fig_price.update_layout(
        yaxis_title="$ per million tokens (blended 3×input + 1×output)",
        yaxis_type="log",
        xaxis_range=["2023-01-01", None],
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_price, use_container_width=True)

if not ze_df.empty and not df.empty:
    st.subheader("Price by Country")
    pd_ = df.dropna(subset=["input_price", "country"])
    pd_ = pd_[pd_["input_price"] > 0]
    if not pd_.empty:
        top4c = pd_["country"].value_counts().head(4).index.tolist()
        pd_top = pd_[pd_["country"].isin(top4c)]
        fig_pbc = go.Figure()
        for ctry in top4c:
            sub = pd_top[pd_top["country"] == ctry]
            fig_pbc.add_trace(go.Box(
                y=sub["input_price"], name=ctry, boxpoints="all", jitter=0.5,
                pointpos=0, marker_size=5,
                text=sub["name"].tolist(),
                hovertemplate="%{text}: $%{y:.3f}/M tokens<extra></extra>",
            ))
        fig_pbc.update_layout(
            yaxis_title="Input Price ($/1M tokens)",
            yaxis_type="log",
            showlegend=False,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_pbc, use_container_width=True)
        st.caption(ATTR)

    st.subheader("Price Frontiers")
    st.caption("Capability vs API cost — Pareto frontier shows the best value per dollar.")
    for sc, lb in [("gpqa_score", "GPQA"), ("swe_bench_verified_score", "SWE-Bench")]:
        pp = df.dropna(subset=[sc, "input_price"])
        pp = pp[pp["input_price"] > 0].copy()
        if pp.empty:
            continue
        pf = pareto_front(pp, "input_price", sc)
        fig_pp = go.Figure()
        for prov in sorted(pp["provider"].unique()):
            sub = pp[pp["provider"] == prov]
            fig_pp.add_trace(go.Scatter(
                x=sub["input_price"], y=sub[sc] * 100, text=sub["name"],
                name=prov, mode="markers",
                marker=dict(color=PROVIDER_COLOURS.get(prov, "#6b7280"), size=7, opacity=0.8),
                hovertemplate="%{text}<br>$%{x:.3f}/M · %{y:.1f}%<extra></extra>",
            ))
        if not pf.empty:
            fig_pp.add_trace(go.Scatter(
                x=pf["input_price"], y=pf[sc] * 100,
                mode="lines", name="Pareto front",
                line=dict(color="#ffffff", width=1.5, dash="dot", shape="hv"), showlegend=False,
            ))
        fig_pp.update_layout(
            title=f"{lb} vs Price",
            xaxis_title="Input Price ($/1M tokens)",
            yaxis_title=f"{lb} Score (%)",
            height=380,
            showlegend=False,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_pp, use_container_width=True)
    st.caption(ATTR)

    st.subheader("Intelligence vs Cost Frontier")
    explainer(
        what="Each model plotted at its list input price (x-axis) vs composite intelligence index (y-axis). The Pareto frontier moves left and up over time — models that were SOTA 12 months ago are now dominated on both axes.",
        why="As intelligence commoditises, can any provider maintain pricing power? This chart shows how fast the frontier is shifting — and whether there is still a capability moat at the top end that justifies premium pricing.",
        source="api.zeroeval.com — benchmark scores (GPQA, SWE-Bench, HLE, AIME-2025, MMMLU) averaged for composite intelligence index. Pricing from provider API list rates.",
    )
    if not df_specs.empty:
        df_plot = df_specs.dropna(subset=["intelligence_score", "input_price_per_m_tokens"])
        if not df_plot.empty:
            vis2 = [p for p in df_plot["provider"].unique() if p in sel_providers] if sel_providers else df_plot["provider"].unique().tolist()
            df_plot = df_plot[df_plot["provider"].isin(vis2)] if vis2 else df_plot
            fig_frontier = px.scatter(
                df_plot, x="input_price_per_m_tokens", y="intelligence_score",
                color="provider",
                title="Intelligence Index vs $/1M Input Tokens",
                labels={"input_price_per_m_tokens": "$/1M Input Tokens", "intelligence_score": "Intelligence Index"},
                color_discrete_map=PROVIDER_COLOURS,
                hover_data={"model": True, "provider": False},
            )
            fig_frontier.update_layout(height=450, showlegend=False, **CHART_LAYOUT)
            st.plotly_chart(fig_frontier, use_container_width=True)

    st.subheader("Value Evolution")
    st.caption("GPQA score per dollar by release quarter — the rising value of intelligence.")
    ve = df.dropna(subset=["gpqa_score", "input_price"])
    ve = ve[ve["input_price"] > 0].copy()
    ve["gpqa_per_dollar"] = (ve["gpqa_score"] * 100) / ve["input_price"]
    if not ve.empty:
        ve_q = ve.groupby(["quarter", "provider"])["gpqa_per_dollar"].median().reset_index()
        fig_ve = go.Figure()
        for prov in sorted(ve_q["provider"].unique()):
            sub = ve_q[ve_q["provider"] == prov]
            fig_ve.add_trace(go.Scatter(
                x=sub["quarter"], y=sub["gpqa_per_dollar"], name=prov,
                mode="lines+markers",
                line=dict(color=PROVIDER_COLOURS.get(prov, "#6b7280"), width=1.5),
                hovertemplate=f"{prov}: %{{y:.1f}} GPQA pts/$1M<extra></extra>",
            ))
        fig_ve.update_layout(yaxis_title="GPQA pts per $1M tokens", yaxis_type="log", **CHART_LAYOUT)
        st.plotly_chart(fig_ve, use_container_width=True)
        st.caption(ATTR)

    st.subheader("Cost Efficiency by Tier")
    st.caption("Cost per GPQA point across model size tiers.")
    ct = df.dropna(subset=["gpqa_score", "input_price", "params"])
    ct = ct[(ct["input_price"] > 0) & (ct["params"] > 0)].copy()
    if not ct.empty:
        import pandas as pd
        ct["tier"] = pd.cut(
            ct["params"],
            bins=[0, 10e9, 70e9, 200e9, float("inf")],
            labels=["Tiny (<10B)", "Small (10–70B)", "Large (70–200B)", "Frontier (200B+)"],
        )
        ct["cost_per_gpqa"] = ct["input_price"] / (ct["gpqa_score"] * 100)
        fig_ct = go.Figure()
        for typ, colour in [("Open Source", "#10b981"), ("Proprietary", "#f59e0b")]:
            sub = ct[ct["is_open"] == typ]
            if sub.empty:
                continue
            fig_ct.add_trace(go.Box(
                x=sub["tier"].astype(str), y=sub["cost_per_gpqa"], name=typ,
                boxpoints="all", jitter=0.5, pointpos=0, marker_size=5,
                marker_color=colour, text=sub["name"].tolist(),
                hovertemplate="%{text}: $%{y:.5f}/GPQA pt<extra></extra>",
            ))
        fig_ct.update_layout(
            yaxis_title="$/GPQA point (input price)",
            yaxis_type="log",
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_ct, use_container_width=True)
        st.caption(ATTR)
