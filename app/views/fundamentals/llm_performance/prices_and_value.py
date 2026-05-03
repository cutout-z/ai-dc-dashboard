"""Prices and Value — falling cost of intelligence, capability vs price, performance per dollar."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, PROVIDER_COLOURS,
    fetch_zeroeval_models, preprocess_ze,
    chart_layout,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()

st.title("Prices and Value")
st.caption(
    "How fast intelligence is getting cheaper, which models deliver the most value, and where prices differ."
)
st.caption(
    "**GPQA** = Graduate-level science questions (physics, chemistry, biology) testing deep reasoning. "
    "**SWE-Bench** = Real GitHub issues — models must write code patches that pass the test suite. "
    "**SOTA** = State of the Art — the highest score any model has achieved on a benchmark."
)

if ze_df.empty or df.empty:
    st.info("Live data unavailable — ZeroEval API offline.")
else:
    # --- Shared filtered data ---
    priced = df.dropna(subset=["gpqa_score", "blended_price"])
    priced = priced[priced["blended_price"] > 0].copy()
    priced["gpqa_pct"] = priced["gpqa_score"] * 100
    priced["cost_per_gpqa"] = priced["blended_price"] / priced["gpqa_pct"]

    # ═══════════════════════════════════════════════════════════════
    # Charts 1 & 2 — side by side
    # ═══════════════════════════════════════════════════════════════
    col1, col2 = st.columns(2)

    # --- Chart 1: The Price of Intelligence ---
    with col1:
        st.subheader("The Price of Intelligence")
        st.caption(
            "Cost per GPQA point over time across quality tiers "
            "— each line tracks the cheapest model"
        )

        _TIERS = [
            (50, "#8b5cf6", "50%+ GPQA"),
            (75, "#3b82f6", "75%+ GPQA"),
            (85, "#ef4444", "85%+ GPQA"),
        ]

        fig1 = go.Figure()
        # Background: all models as faded dots
        fig1.add_trace(go.Scatter(
            x=priced["release_date"], y=priced["cost_per_gpqa"],
            mode="markers",
            marker=dict(size=4, color="#6b7280", opacity=0.25),
            text=priced["name"],
            hovertemplate="%{text}<br>$%{y:.4f}/GPQA pt<extra></extra>",
            showlegend=False,
        ))

        _tier_stats: dict[int, tuple[float, float]] = {}
        for threshold, colour, label in _TIERS:
            tier_df = priced[priced["gpqa_pct"] >= threshold].sort_values("release_date")
            if tier_df.empty:
                continue
            dates, mins, names = [], [], []
            running_min = float("inf")
            for _, row in tier_df.iterrows():
                if row["cost_per_gpqa"] < running_min:
                    running_min = row["cost_per_gpqa"]
                    dates.append(row["release_date"])
                    mins.append(running_min)
                    names.append(row["name"])
            if dates:
                _tier_stats[threshold] = (mins[0], mins[-1])
                dates.append(priced["release_date"].max())
                mins.append(mins[-1])
                names.append("")
            fig1.add_trace(go.Scatter(
                x=dates, y=mins, name=label,
                mode="lines",
                line=dict(color=colour, width=2, shape="hv"),
                text=names,
                hovertemplate=(
                    f"{label}<br>%{{text}}<br>${{y:.4f}}/GPQA pt<extra></extra>"
                ),
            ))

        fig1.update_layout(
            yaxis_title="$ per GPQA point",
            yaxis_type="log",
            height=420,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig1, use_container_width=True)

        if 75 in _tier_stats:
            first, last = _tier_stats[75]
            pct = (1 - last / first) * 100
            st.caption(
                f"75%+ tier: {pct:.0f}% cheaper — "
                f"${first:.3f} → ${last:.4f} per GPQA point"
            )

    # --- Chart 2: Cheapest 75%+ GPQA Model ---
    with col2:
        st.subheader("Cheapest 75%+ GPQA Model")
        st.caption(
            "The falling cost of frontier-level intelligence "
            "— every dot is a qualifying model"
        )

        cheap = priced[priced["gpqa_pct"] >= 75].copy().sort_values("release_date")
        if not cheap.empty:
            fig2 = go.Figure()
            # All qualifying models as faded dots
            fig2.add_trace(go.Scatter(
                x=cheap["release_date"], y=cheap["blended_price"],
                mode="markers",
                marker=dict(size=5, color="#6b7280", opacity=0.3),
                text=cheap["name"],
                hovertemplate="%{text}<br>$%{y:.2f}/M tokens<extra></extra>",
                showlegend=False,
            ))

            # Running minimum step-line with model labels
            dates, prices, names = [], [], []
            running_min = float("inf")
            for _, row in cheap.iterrows():
                if row["blended_price"] < running_min:
                    running_min = row["blended_price"]
                    dates.append(row["release_date"])
                    prices.append(running_min)
                    names.append(row["name"])

            first_p = prices[0] if prices else 0
            last_p = prices[-1] if prices else 0

            if dates:
                dates.append(cheap["release_date"].max())
                prices.append(prices[-1])
                names.append("")

                fig2.add_trace(go.Scatter(
                    x=dates, y=prices,
                    mode="lines+markers+text",
                    line=dict(color="#10b981", width=2, shape="hv"),
                    marker=dict(size=7, color="#10b981"),
                    text=names,
                    textposition="top left",
                    textfont=dict(size=10, color="#e5e7eb"),
                    hovertemplate="%{text}<br>$%{y:.2f}/M tokens<extra></extra>",
                    showlegend=False,
                ))

            fig2.update_layout(
                yaxis_title="$ per 1M tokens (blended)",
                yaxis_type="log",
                height=420,
                **CHART_LAYOUT,
            )
            st.plotly_chart(fig2, use_container_width=True)

            if first_p > 0 and last_p > 0 and first_p != last_p:
                pct_drop = (1 - last_p / first_p) * 100
                st.caption(
                    f"{pct_drop:.0f}% cheaper: ${first_p:.2f} → "
                    f"${last_p:.2f} per 1M tokens · Models with 75%+ GPQA"
                )
        else:
            st.info("No models with 75%+ GPQA and pricing data.")

    st.caption(ATTR)

    # ═══════════════════════════════════════════════════════════════
    # Chart 3: Capability vs Price
    # ═══════════════════════════════════════════════════════════════
    st.subheader("Capability vs Price")
    st.caption("SWE-Bench SOTA (line) vs average model price (bars) over time")

    cap = df[df["blended_price"] > 0].dropna(subset=["blended_price"]).copy()
    swe = df.dropna(subset=["swe_bench_verified_score"]).copy()

    if not cap.empty:
        avg_price = cap.groupby("quarter")["blended_price"].mean().reset_index()
        avg_price.columns = ["quarter", "avg_price"]
        avg_price["q_label"] = avg_price["quarter"].apply(
            lambda d: f"Q{(d.month - 1) // 3 + 1} {d.year}"
        )

        # SWE-Bench SOTA progression by quarter
        sota_rows = []
        running_sota = 0.0
        for q in sorted(df["quarter"].dropna().unique()):
            q_scores = swe[swe["quarter"] <= q]["swe_bench_verified_score"]
            if not q_scores.empty:
                best = q_scores.max() * 100
                running_sota = max(running_sota, best)
            if running_sota > 0:
                sota_rows.append({"quarter": q, "sota": running_sota})
        sota_df = pd.DataFrame(sota_rows) if sota_rows else pd.DataFrame()

        if not sota_df.empty:
            sota_df["q_label"] = sota_df["quarter"].apply(
                lambda d: f"Q{(d.month - 1) // 3 + 1} {d.year}"
            )
            merged = avg_price.merge(sota_df[["q_label", "sota"]], on="q_label", how="left")
        else:
            merged = avg_price.copy()
            merged["sota"] = None

        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=merged["q_label"], y=merged["avg_price"],
            marker_color="#9ca3af", opacity=0.6,
            name="Avg Price ($/M tokens)",
            hovertemplate="%{x}<br>Avg: $%{y:.2f}/M tokens<extra></extra>",
        ))
        if merged["sota"].notna().any():
            fig3.add_trace(go.Scatter(
                x=merged["q_label"], y=merged["sota"],
                mode="lines+markers", name="SWE-Bench SOTA (%)",
                line=dict(color="#10b981", width=2.5),
                marker=dict(size=7, color="#10b981"),
                hovertemplate="SWE-Bench SOTA: %{y:.1f}%<extra></extra>",
                yaxis="y2",
            ))

        layout3 = {**CHART_LAYOUT}
        layout3["margin"] = dict(l=40, r=60, t=40, b=80)
        fig3.update_layout(
            yaxis=dict(title="Avg Price ($/M tokens)", tickprefix="$"),
            yaxis2=dict(
                title="SWE-Bench SOTA (%)",
                overlaying="y", side="right",
                range=[0, 105], ticksuffix="%",
            ),
            height=450,
            **layout3,
        )
        st.plotly_chart(fig3, use_container_width=True)
        st.caption(ATTR)

    # ═══════════════════════════════════════════════════════════════
    # Chart 4: Performance vs Price
    # ═══════════════════════════════════════════════════════════════
    st.subheader("Performance vs Price")
    st.caption("GPQA score vs cost per million tokens")

    if not priced.empty:
        _MAJOR = set(PROVIDER_COLOURS.keys())
        perf = priced.copy()
        perf["chart_provider"] = perf["provider"].apply(
            lambda p: p if p in _MAJOR else "Others"
        )
        _ALL_COLOURS = {**PROVIDER_COLOURS, "Others": "#6b7280"}

        fig4 = go.Figure()
        for prov in list(PROVIDER_COLOURS.keys()) + ["Others"]:
            sub = perf[perf["chart_provider"] == prov]
            if sub.empty:
                continue
            fig4.add_trace(go.Scatter(
                x=sub["blended_price"], y=sub["gpqa_pct"],
                mode="markers", name=prov,
                marker=dict(size=8, color=_ALL_COLOURS[prov], opacity=0.8),
                text=sub["name"],
                hovertemplate=(
                    "%{text}<br>$%{x:.2f}/M tokens<br>"
                    "GPQA: %{y:.1f}%<extra></extra>"
                ),
            ))

        fig4.update_layout(
            xaxis_title="Price ($/M tokens)", xaxis_type="log",
            yaxis_title="GPQA Score (%)", yaxis_range=[0, 105],
            height=500,
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig4, use_container_width=True)
        st.caption(ATTR)

    # ═══════════════════════════════════════════════════════════════
    # Cost Efficiency by Tier (existing)
    # ═══════════════════════════════════════════════════════════════
    st.subheader("Cost Efficiency by Tier")
    st.caption("Cost per GPQA point across model size tiers.")
    ct = df.dropna(subset=["gpqa_score", "input_price", "params"])
    ct = ct[(ct["input_price"] > 0) & (ct["params"] > 0)].copy()
    if not ct.empty:
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
