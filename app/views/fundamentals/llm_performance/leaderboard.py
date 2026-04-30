"""LLM Leaderboard — frontier models ranked by performance, price, and speed."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.lib.llm_perf import fetch_zeroeval_models, fetch_zeroeval_indexes, chart_layout  # noqa: F401

# Country code → flag emoji
_FLAG = {
    "US": "\U0001f1fa\U0001f1f8", "CN": "\U0001f1e8\U0001f1f3",
    "FR": "\U0001f1eb\U0001f1f7", "CA": "\U0001f1e8\U0001f1e6",
    "UK": "\U0001f1ec\U0001f1e7", "GB": "\U0001f1ec\U0001f1e7",
    "IL": "\U0001f1ee\U0001f1f1", "KR": "\U0001f1f0\U0001f1f7",
    "AE": "\U0001f1e6\U0001f1ea", "DE": "\U0001f1e9\U0001f1ea",
    "IN": "\U0001f1ee\U0001f1f3", "JP": "\U0001f1ef\U0001f1f5",
    "SG": "\U0001f1f8\U0001f1ec", "SE": "\U0001f1f8\U0001f1ea",
}

# Index categories to display (matching llm-stats.com columns)
_INDEX_COLS = ["reasoning", "math", "coding", "agents", "search", "knowledge"]
_INDEX_LABELS = {
    "reasoning": "Reasoning",
    "math": "Math",
    "coding": "Coding",
    "agents": "Agent",
    "search": "Search",
    "knowledge": "Knowledge",
}

ze_df = fetch_zeroeval_models()
indexes = fetch_zeroeval_indexes()

st.title("LLM Leaderboard")
st.caption(
    "Ranking the best LLMs by performance, price, and speed. "
    "Live data from [LLM Stats](https://llm-stats.com) · updated hourly."
)

if ze_df.empty:
    st.info("Live data unavailable — ZeroEval API offline.")
else:
    lb = ze_df.copy()

    # --- Merge TrueSkill index scores ---
    for cat in _INDEX_COLS:
        col = f"idx_{cat}"
        if cat in indexes:
            idx_df = indexes[cat][["model_id", "conservative"]].rename(
                columns={"conservative": col}
            )
            lb = lb.merge(idx_df, on="model_id", how="left")
        else:
            lb[col] = None

    # Sort by Reasoning index (matching llm-stats.com default)
    sort_col = "idx_reasoning"
    lb = lb.dropna(subset=[sort_col])
    lb = lb.sort_values(sort_col, ascending=False).reset_index(drop=True)

    # Country flag
    lb["country"] = lb.get("organization_country", pd.Series(dtype=str)).apply(
        lambda x: _FLAG.get(str(x).strip().upper(), "") if pd.notna(x) else ""
    )

    # License
    lb["license_label"] = lb["license"].apply(
        lambda x: "Closed" if x == "proprietary" else "Open"
    )

    # Context — format as K or M
    def _fmt_ctx(v):
        if pd.isna(v) or v is None or v == 0:
            return "-"
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if v >= 1_000:
            fk = v / 1_000
            return f"{fk:.1f}K" if fk != int(fk) else f"{int(fk)}K"
        return str(int(v))

    lb["ctx_fmt"] = lb["context"].apply(_fmt_ctx)

    # Speed
    lb["speed_fmt"] = lb["throughput"].apply(
        lambda v: f"{int(v)} c/s" if pd.notna(v) and v > 0 else "-"
    )

    # Pricing
    lb["in_price_fmt"] = lb["input_price"].apply(
        lambda v: f"${v:.2f}" if pd.notna(v) else "-"
    )
    lb["out_price_fmt"] = lb["output_price"].apply(
        lambda v: f"${v:.2f}" if pd.notna(v) else "-"
    )

    # Build display dict
    display_data = {
        "Model": lb["name"],
        "Country": lb["country"],
        "License": lb["license_label"],
        "Context": lb["ctx_fmt"],
        "Input $/M": lb["in_price_fmt"],
        "Output $/M": lb["out_price_fmt"],
        "Speed": lb["speed_fmt"],
    }
    col_config = {
        "Model": st.column_config.TextColumn(width="medium"),
        "Country": st.column_config.TextColumn(width="small", help="Organization headquarters country"),
        "License": st.column_config.TextColumn(width="small", help="Proprietary (closed) or open-source/open-weight"),
        "Context": st.column_config.TextColumn(width="small", help="Maximum input context length in tokens"),
        "Input $/M": st.column_config.TextColumn(width="small", help="Cost per 1 million input tokens (average across providers)"),
        "Output $/M": st.column_config.TextColumn(width="small", help="Cost per 1 million output tokens (average across providers)"),
        "Speed": st.column_config.TextColumn(width="small", help="Output throughput in characters per second"),
    }

    _INDEX_HELP = {
        "reasoning": "Reasoning Index — TrueSkill conservative rating across reasoning benchmarks (logic, planning, multi-step problem solving)",
        "math": "Math Index — TrueSkill conservative rating across math benchmarks (competition math, formal proofs, quantitative reasoning)",
        "coding": "Coding Index — TrueSkill conservative rating across coding benchmarks (generation, debugging, software engineering)",
        "agents": "Agent Index — TrueSkill conservative rating across agent benchmarks (long-horizon planning, tool orchestration)",
        "search": "Search Index — TrueSkill conservative rating across search & retrieval benchmarks",
        "knowledge": "Knowledge Index — TrueSkill conservative rating across knowledge benchmarks (factual recall, world knowledge)",
    }

    # Add index columns
    for cat in _INDEX_COLS:
        label = _INDEX_LABELS.get(cat, cat.title())
        col = f"idx_{cat}"
        display_data[label] = pd.to_numeric(lb[col], errors="coerce").round(1)
        col_config[label] = st.column_config.NumberColumn(
            format="%.1f",
            help=_INDEX_HELP.get(cat, ""),
        )

    display = pd.DataFrame(display_data)
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=700,
        column_config=col_config,
    )
    st.caption(
        f"[LLM Stats](https://llm-stats.com) / api.zeroeval.com · {len(lb)} models · "
        "Sorted by Reasoning index (TrueSkill conservative rating). "
        "Speed in characters/sec."
    )

    # --- Performance Index bar chart ---
    st.markdown("---")
    st.subheader("Performance Index")
    st.caption("Composite TrueSkill ratings across published benchmarks")

    # Tabs for metric selection — pick the categories with meaningful model counts
    _CHART_CATS = [
        ("Reasoning", "reasoning"), ("Coding", "code"), ("Math", "math"),
        ("Vision", "vision"), ("Writing", "writing"), ("Agents", "agents"),
        ("Tool use", "tool_calling"), ("Long context", "long_context"),
        ("Search", "search"), ("Multimodal", "multimodal"),
        ("Frontend", "frontend_development"), ("Factuality", "factuality"),
    ]
    tab_labels = [label for label, _ in _CHART_CATS]
    tabs = st.tabs(tab_labels)

    _ORG_COLOURS = {
        "Anthropic": "#f59e0b", "OpenAI": "#10b981", "Google": "#3b82f6",
        "Google DeepMind": "#3b82f6", "Meta": "#8b5cf6", "xAI": "#9ca3af",
        "DeepSeek": "#ec4899", "Alibaba Cloud / Qwen Team": "#ef4444",
        "Mistral AI": "#06b6d4", "ByteDance": "#f97316", "Zhipu AI": "#a3e635",
        "Moonshot AI": "#67e8f9", "MiniMax": "#c084fc", "StepFun": "#fbbf24",
    }
    _DEFAULT_COLOUR = "#6b7280"

    import plotly.graph_objects as go

    for tab, (label, cat_key) in zip(tabs, _CHART_CATS):
        with tab:
            if cat_key not in indexes or indexes[cat_key].empty:
                st.info(f"No index data for {label}.")
                continue

            idx_df = indexes[cat_key].copy()
            idx_df = idx_df.sort_values("conservative", ascending=False).head(15).reset_index(drop=True)

            # Merge org names from main model data
            idx_df = idx_df.merge(
                ze_df[["model_id", "name", "organization"]].drop_duplicates("model_id"),
                on="model_id", how="left",
            )
            idx_df["display_name"] = idx_df["name"].fillna(idx_df["model_id"])
            idx_df["org"] = idx_df["organization"].fillna("")
            idx_df["colour"] = idx_df["org"].map(
                lambda o: _ORG_COLOURS.get(o, _DEFAULT_COLOUR)
            )

            # Reverse for plotly (bottom-to-top)
            idx_df = idx_df.iloc[::-1].reset_index(drop=True)

            # Rank labels (01, 02, ...)
            n = len(idx_df)
            rank_labels = [f"{n - i:02d}" for i in range(n)]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=idx_df["conservative"],
                y=[f"{rank}  {name}" for rank, name in zip(rank_labels, idx_df["display_name"])],
                orientation="h",
                marker_color=idx_df["colour"].tolist(),
                text=idx_df["conservative"].round(1),
                textposition="outside",
                textfont=dict(size=13, color="#e5e7eb"),
                hovertemplate="%{y}<br>Score: %{x:.1f}<extra></extra>",
            ))
            fig.update_layout(
                height=max(400, n * 45),
                margin=dict(l=10, r=50, t=10, b=10),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e5e7eb", size=13),
                xaxis=dict(visible=False, range=[0, idx_df["conservative"].max() * 1.15]),
                yaxis=dict(tickfont=dict(size=13), automargin=True),
                showlegend=False,
                bargap=0.35,
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("")
    st.caption(
        "Charts on the other LLM Performance pages use live data from "
        "[LLM Stats](https://llm-stats.com) via api.zeroeval.com."
    )
