"""LLM Performance Analysis — AI model benchmarks, context windows, pricing, and live leaderboard."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st


def _chart_layout():
    return dict(
        template=st.session_state.get("plotly_template", "plotly_dark"),
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        margin=dict(l=40, r=20, t=40, b=40),
        hoverlabel=dict(bgcolor=st.session_state.get("hoverlabel_bg", "#333"), font_size=12),
    )

CHART_LAYOUT = _chart_layout()

st.title("LLM Performance Analysis")
st.caption("Frontier AI model benchmarks, context windows, API pricing, and live leaderboard.")

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"
DB_PATH = st.session_state["db_path"]

# ═════════════════════════════════════════════════════════════════════════
# LLM LEADERBOARD — live from api.zeroeval.com
# ═════════════════════════════════════════════════════════════════════════

_BENCH_COLS = ["gpqa_score", "swe_bench_verified_score", "hle_score", "aime_2025_score"]

_ORG_TO_PROVIDER = {
    "Anthropic": "Anthropic",
    "OpenAI": "OpenAI",
    "Google": "Google",
    "Google DeepMind": "Google",
    "Meta": "Meta",
    "Meta AI": "Meta",
    "xAI": "xAI",
    "DeepSeek": "DeepSeek",
    "Mistral AI": "Mistral",
    "Mistral": "Mistral",
    "Alibaba Cloud": "Alibaba",
    "Alibaba Cloud/Qwen Team": "Alibaba",
    "Qwen Team": "Alibaba",
}


@st.cache_data(ttl=3600)
def _fetch_zeroeval_models() -> pd.DataFrame:
    """Fetch live model data from api.zeroeval.com. Cached for 1 hour."""
    try:
        resp = requests.get(
            "https://api.zeroeval.com/leaderboard/models/full",
            params={"justCanonicals": "true"},
            timeout=15,
        )
        resp.raise_for_status()
        return pd.DataFrame(resp.json())
    except Exception as e:
        st.warning(f"ZeroEval API unavailable: {e}")
        return pd.DataFrame()


_ze_df = _fetch_zeroeval_models()

if not _ze_df.empty:
    st.header("LLM Leaderboard")
    st.caption(
        "Frontier models ranked by composite benchmark score (mean of GPQA, SWE-Bench Verified, HLE, AIME-2025). "
        "Live data from [llm-stats.com](https://llm-stats.com) · updated hourly."
    )

    _lb = _ze_df.copy()
    _lb["composite_score"] = _lb[_BENCH_COLS].mean(axis=1, skipna=True).mul(100).round(1)
    _lb = _lb.dropna(subset=["composite_score"])
    _lb = _lb.sort_values("composite_score", ascending=False).reset_index(drop=True)
    _lb["rank"] = range(1, len(_lb) + 1)
    _lb["type"] = _lb["license"].apply(lambda x: "Closed" if x == "proprietary" else "Open")
    _lb["context_k"] = (_lb["context"].fillna(0) / 1000).round(0)

    _display = pd.DataFrame({
        "#": _lb["rank"],
        "Model": _lb["name"],
        "Org": _lb["organization"],
        "Type": _lb["type"],
        "Score": _lb["composite_score"],
        "GPQA": (_lb["gpqa_score"] * 100).round(1),
        "AIME '25": (_lb["aime_2025_score"] * 100).round(1),
        "SWE-Bench": (_lb["swe_bench_verified_score"] * 100).round(1),
        "HLE": (_lb["hle_score"] * 100).round(1),
        "In $/M": _lb["input_price"],
        "Out $/M": _lb["output_price"],
        "Ctx (K)": _lb["context_k"],
        "Speed": _lb["throughput"],
    })

    st.dataframe(
        _display,
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Model": st.column_config.TextColumn(width="medium"),
            "Org": st.column_config.TextColumn(width="small"),
            "Type": st.column_config.TextColumn(width="small"),
            "Score": st.column_config.NumberColumn(format="%.1f", width="small"),
            "GPQA": st.column_config.NumberColumn(format="%.1f%%"),
            "AIME '25": st.column_config.NumberColumn(format="%.1f%%"),
            "SWE-Bench": st.column_config.NumberColumn(format="%.1f%%"),
            "HLE": st.column_config.NumberColumn(format="%.1f%%"),
            "In $/M": st.column_config.NumberColumn(format="$%.2f"),
            "Out $/M": st.column_config.NumberColumn(format="$%.2f"),
            "Ctx (K)": st.column_config.NumberColumn(format="%dK"),
            "Speed": st.column_config.NumberColumn(format="%d tok/s"),
        },
    )
    st.caption(
        f"api.zeroeval.com · {len(_lb)} models · Score = mean(GPQA, SWE-Bench, HLE, AIME-2025) as %. "
        "Blanks = no published score. Speed in tokens/sec."
    )
    st.markdown("")


# ─── Provider colours (consistent across all charts) ───
PROVIDER_COLOURS = {
    "OpenAI":    "#10b981",  # green
    "Anthropic": "#f59e0b",  # orange
    "Google":    "#3b82f6",  # blue
    "Meta":      "#8b5cf6",  # purple
    "xAI":       "#9ca3af",  # grey
    "DeepSeek":  "#ec4899",  # pink
    "Alibaba":   "#ef4444",  # red
    "Mistral":   "#06b6d4",  # cyan
}

# ═════════════════════════════════════════════════════════════════════════
# DATA — Context windows
# ═════════════════════════════════════════════════════════════════════════
CONTEXT_WINDOWS = [
    {"model": "GPT-3",            "date": "2020-06", "tokens": 4096,     "provider": "OpenAI"},
    {"model": "GPT-3.5",          "date": "2022-11", "tokens": 4096,     "provider": "OpenAI"},
    {"model": "Claude 1",         "date": "2023-03", "tokens": 9000,     "provider": "Anthropic"},
    {"model": "GPT-4",            "date": "2023-03", "tokens": 8192,     "provider": "OpenAI"},
    {"model": "GPT-4 32K",        "date": "2023-03", "tokens": 32768,    "provider": "OpenAI"},
    {"model": "Claude 2",         "date": "2023-07", "tokens": 100000,   "provider": "Anthropic"},
    {"model": "GPT-4 Turbo",      "date": "2023-11", "tokens": 128000,   "provider": "OpenAI"},
    {"model": "Gemini 1.5 Pro",   "date": "2024-02", "tokens": 1000000,  "provider": "Google"},
    {"model": "Claude 3",         "date": "2024-03", "tokens": 200000,   "provider": "Anthropic"},
    {"model": "Llama 3 70B",      "date": "2024-04", "tokens": 8000,     "provider": "Meta"},
    {"model": "GPT-4o",           "date": "2024-05", "tokens": 128000,   "provider": "OpenAI"},
    {"model": "Claude 3.5",       "date": "2024-06", "tokens": 200000,   "provider": "Anthropic"},
    {"model": "Llama 3.1 405B",   "date": "2024-07", "tokens": 128000,   "provider": "Meta"},
    {"model": "DeepSeek V3",      "date": "2024-12", "tokens": 128000,   "provider": "DeepSeek"},
    {"model": "Gemini 2.0",       "date": "2024-12", "tokens": 1000000,  "provider": "Google"},
    {"model": "Grok 3",           "date": "2025-02", "tokens": 131000,   "provider": "xAI"},
    {"model": "Gemini 2.5 Pro",   "date": "2025-03", "tokens": 1000000,  "provider": "Google"},
    {"model": "Llama 4 Maverick", "date": "2025-04", "tokens": 10000000, "provider": "Meta"},
    {"model": "Claude Opus 4",    "date": "2025-05", "tokens": 1000000,  "provider": "Anthropic"},
    {"model": "GPT-5",            "date": "2025-08", "tokens": 400000,   "provider": "OpenAI"},
    {"model": "Claude Sonnet 4.5","date": "2025-09", "tokens": 200000,   "provider": "Anthropic"},
    {"model": "Gemini 3 Pro",     "date": "2025-11", "tokens": 1000000,  "provider": "Google"},
    {"model": "GPT-5.2",          "date": "2025-12", "tokens": 400000,   "provider": "OpenAI"},
    {"model": "Gemini 3 Flash",   "date": "2025-12", "tokens": 1000000,  "provider": "Google"},
    {"model": "Claude Opus 4.6",  "date": "2026-02", "tokens": 1000000,  "provider": "Anthropic"},
    {"model": "Gemini 3.1 Pro",   "date": "2026-02", "tokens": 1048576,  "provider": "Google"},
    {"model": "GPT-5.4",          "date": "2026-03", "tokens": 1000000,  "provider": "OpenAI"},
]

# ═════════════════════════════════════════════════════════════════════════
# DATA — Task complexity milestones (no provider dimension)
# ═════════════════════════════════════════════════════════════════════════
CAPABILITY_MILESTONES = [
    {"date": "2020-06", "event": "GPT-3: few-shot learning",            "complexity": 1},
    {"date": "2022-11", "event": "ChatGPT: conversational AI",           "complexity": 2},
    {"date": "2023-03", "event": "GPT-4: multimodal, reasoning",         "complexity": 3},
    {"date": "2023-07", "event": "Claude 2: 100K context",              "complexity": 3.5},
    {"date": "2023-11", "event": "GPT-4 Turbo: 128K, function calling", "complexity": 4},
    {"date": "2024-02", "event": "Gemini 1.5: 1M context",             "complexity": 4.5},
    {"date": "2024-03", "event": "Claude 3: tool use, vision",         "complexity": 5},
    {"date": "2024-06", "event": "Claude 3.5: artifacts, coding",       "complexity": 6},
    {"date": "2024-09", "event": "o1: chain-of-thought reasoning",      "complexity": 7},
    {"date": "2024-10", "event": "Claude computer use",                 "complexity": 7.5},
    {"date": "2025-01", "event": "o3/R1: advanced reasoning, open",     "complexity": 8},
    {"date": "2025-02", "event": "Claude Code: autonomous coding",      "complexity": 8.5},
    {"date": "2025-05", "event": "Claude 4: extended thinking, agents", "complexity": 9},
    {"date": "2025-07", "event": "Grok 4: frontier reasoning",          "complexity": 9.3},
    {"date": "2025-08", "event": "GPT-5: multi-step tool use",          "complexity": 9.5},
    {"date": "2025-11", "event": "Gemini 3: multi-modal reasoning",     "complexity": 9.6},
    {"date": "2026-02", "event": "Claude 4.6: 1M ctx, 91% GPQA",       "complexity": 9.8},
    {"date": "2026-02", "event": "Gemini 3.1: 94% GPQA SOTA",          "complexity": 9.9},
]


# ═════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════
def _compute_y_range(scores: list[float], max_score: float = 100.0, floor: float = 0.0) -> tuple[float, float]:
    """Auto-scale y-axis with 10% padding below lowest value.

    Returns (y_min, y_max). y_min is 10% below the lowest score but not below `floor`.
    y_max is 5% above the highest score but not above `max_score`.
    """
    if not scores:
        return (floor, max_score)
    lo = min(scores)
    hi = max(scores)
    y_min = max(floor, lo - lo * 0.10)
    y_max = min(max_score, hi + hi * 0.05)
    if y_max <= y_min:
        y_max = y_min + 1
    return (y_min, y_max)


def _explainer(what: str, why: str, source: str) -> None:
    """Render a collapsible explainer for a chart."""
    with st.expander("About this chart"):
        st.markdown(f"**What it shows.** {what}")
        st.markdown(f"**Why it matters.** {why}")
        st.markdown(f"**Source.** {source}")


def _provider_traces(records: list[dict], x_key: str, y_key: str,
                     sel_providers: list[str],
                     text_key: str = "model", hover_fmt: str = "%{text}: %{y:.1f}") -> list[go.Scatter]:
    """Build one go.Scatter trace per provider."""
    providers: dict[str, dict] = {}
    for r in records:
        p = r["provider"]
        if p not in sel_providers:
            continue
        providers.setdefault(p, {"x": [], "y": [], "text": []})
        providers[p]["x"].append(r[x_key])
        providers[p]["y"].append(r[y_key])
        providers[p]["text"].append(r[text_key])

    traces = []
    # Preserve PROVIDER_COLOURS ordering for consistent legend
    for p in PROVIDER_COLOURS:
        if p not in providers:
            continue
        d = providers[p]
        traces.append(go.Scatter(
            x=d["x"], y=d["y"], text=d["text"],
            name=p, mode="markers+lines",
            line=dict(color=PROVIDER_COLOURS[p], width=1.5),
            marker=dict(size=8, color=PROVIDER_COLOURS[p]),
            hovertemplate=hover_fmt + f"<extra>{p}</extra>",
        ))
    return traces


# ═════════════════════════════════════════════════════════════════════════
# SIDEBAR — filters
# ═════════════════════════════════════════════════════════════════════════
st.sidebar.header("Filters")
all_providers = list(PROVIDER_COLOURS.keys())
sel_providers = st.sidebar.multiselect("Providers", all_providers, default=all_providers)


# ═════════════════════════════════════════════════════════════════════════
# SECTION 1 — Capability Progression
# ═════════════════════════════════════════════════════════════════════════
st.header("Capability Progression")

# ─── Task Complexity Over Time ───
st.subheader("Task Complexity Over Time")
_explainer(
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
    **CHART_LAYOUT,
)
st.plotly_chart(fig_complexity, use_container_width=True)

# ─── Context Window Expansion ───
st.subheader("Context Window Expansion")
_explainer(
    what="Maximum prompt size each frontier model can process in a single call, plotted on a log scale. From 4K tokens (GPT-3) to 10M tokens (Llama 4 Maverick) — a ~2500x expansion in five years.",
    why="Context window is a hard constraint on what applications are possible. Long-context unlocks RAG-free codebases, whole-book summarisation, and multi-hour agent loops. The 'memory wall' has been the hardest architectural constraint to break.",
    source="Provider announcements and model cards. Context sizes are quoted maximums — effective context (where recall stays high) is often shorter.",
)

fig_ctx = go.Figure()
for trace in _provider_traces(
    CONTEXT_WINDOWS, x_key="date", y_key="tokens",
    sel_providers=sel_providers,
    hover_fmt="%{text}<br>%{y:,.0f} tokens",
):
    fig_ctx.add_trace(trace)

fig_ctx.update_layout(
    yaxis_title="Context Window (tokens)",
    yaxis_type="log",
    **CHART_LAYOUT,
)
st.plotly_chart(fig_ctx, use_container_width=True)


# ─── Load Arena Elo early (used in Human Preference Map + Live Leaderboard) ───
_conn = sqlite3.connect(DB_PATH)
df_elo = pd.read_sql("SELECT * FROM llm_arena_elo ORDER BY elo DESC", _conn)
_conn.close()

# ═════════════════════════════════════════════════════════════════════════
# SECTIONS 2–9 — Live charts (llm-stats.com/ai-trends via api.zeroeval.com)
# ═════════════════════════════════════════════════════════════════════════

if not _ze_df.empty:
    import numpy as np

    _df = _ze_df.copy()
    _df["release_date"] = pd.to_datetime(_df["release_date"], errors="coerce")
    _df = _df.dropna(subset=["release_date"]).sort_values("release_date")
    _df["quarter"] = _df["release_date"].dt.to_period("Q").dt.start_time
    _df["year"] = _df["release_date"].dt.year.astype(int)
    _df["month"] = _df["release_date"].dt.month.astype(int)
    _df["provider"] = _df["organization"].map(_ORG_TO_PROVIDER).fillna(_df["organization"])
    _df["is_open"] = _df["license"].apply(lambda x: "Open Source" if x != "proprietary" else "Proprietary")
    _df["country"] = _df["organization_country"].fillna("Unknown")
    _df["blended_price"] = ((3 * _df["input_price"].fillna(0) + _df["output_price"].fillna(0)) / 4).replace(0, float("nan"))

    _BENCH_MAP = {
        "gpqa_score":               "GPQA",
        "swe_bench_verified_score": "SWE-Bench",
        "hle_score":                "HLE",
        "aime_2025_score":          "AIME 2025",
        "mmmlu_score":              "MMMLU",
        "simpleqa_score":           "SimpleQA",
        "browsecomp_score":         "BrowseComp",
        "terminal_bench_score":     "Terminal Bench",
        "mrcr_v2_score":            "MRCR v2",
        "scicode_score":            "SciCode",
    }

    _ATTR = "Data: [llm-stats.com/ai-trends](https://llm-stats.com/ai-trends) · [api.zeroeval.com](https://api.zeroeval.com)"

    def _sota_prog(df, score_col, group_col=None):
        """SOTA step-function progression. Returns df with date, score, model."""
        if group_col:
            rows = []
            for grp, sub in df.groupby(group_col):
                sub = sub.dropna(subset=[score_col]).sort_values("release_date")
                sota = -1.0
                for _, r in sub.iterrows():
                    if r[score_col] > sota:
                        sota = r[score_col]
                        rows.append({"date": r["release_date"], "score": sota * 100, "model": r["name"], group_col: grp})
            return pd.DataFrame(rows)
        else:
            valid = df.dropna(subset=[score_col]).sort_values("release_date")
            sota, rows = -1.0, []
            for _, r in valid.iterrows():
                if r[score_col] > sota:
                    sota = r[score_col]
                    rows.append({"date": r["release_date"], "score": sota * 100, "model": r["name"]})
            return pd.DataFrame(rows)

    def _pareto_front(df, x_col, y_col):
        """Pareto-optimal points: max y at increasing x."""
        d = df.dropna(subset=[x_col, y_col]).sort_values(x_col)
        best_y, rows = -1e9, []
        for _, r in d.iterrows():
            if r[y_col] > best_y:
                best_y = r[y_col]
                rows.append(r)
        return pd.DataFrame(rows)

    st.caption(
        "Sections 2–9 replicate the analysis from "
        "[llm-stats.com/ai-trends](https://llm-stats.com/ai-trends) "
        "using live data from api.zeroeval.com. "
        "Please visit the original for the full interactive experience."
    )

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 2 — Benchmark Performance
    # ═══════════════════════════════════════════════════════════════════
    st.header("Benchmark Performance")
    st.caption("How quickly frontier capability is improving, and how tightly packed the leaders have become.")

    # Benchmark Saturation
    st.subheader("Benchmark Saturation")
    st.caption("SOTA score progression over time — each step is a new best model.")
    _BENCH_COLOURS = px.colors.qualitative.Dark24
    fig_sat = go.Figure()
    for i, (col, label) in enumerate(_BENCH_MAP.items()):
        _prog = _sota_prog(_df, col)
        if _prog.empty:
            continue
        colour = _BENCH_COLOURS[i % len(_BENCH_COLOURS)]
        _prog_ext = pd.concat([_prog, pd.DataFrame([{"date": _df["release_date"].max(), "score": _prog["score"].iloc[-1], "model": ""}])], ignore_index=True)
        fig_sat.add_trace(go.Scatter(
            x=_prog_ext["date"], y=_prog_ext["score"],
            name=label, mode="lines",
            line=dict(color=colour, width=1.5, shape="hv"),
            hovertemplate=f"{label}: %{{y:.1f}}%<br>%{{x|%b %Y}}<extra></extra>",
        ))
    fig_sat.update_layout(yaxis_title="SOTA Score (%)", yaxis_range=[0, 105], **CHART_LAYOUT)
    st.plotly_chart(fig_sat, use_container_width=True)
    st.caption(_ATTR)

    # The Convergence
    st.subheader("The Convergence")
    st.caption("The gap between the #1 and #10 GPQA score — the frontier is getting crowded.")
    _gpqa_valid = _df.dropna(subset=["gpqa_score"]).sort_values("release_date")
    _conv_rows = []
    for dt in _gpqa_valid["release_date"].unique():
        pool = _gpqa_valid[_gpqa_valid["release_date"] <= dt]["gpqa_score"].sort_values(ascending=False)
        if len(pool) >= 10:
            _conv_rows.append({"date": dt, "rank": "#1",  "score": pool.iloc[0] * 100})
            _conv_rows.append({"date": dt, "rank": "#10", "score": pool.iloc[9] * 100})
    if _conv_rows:
        _conv_df = pd.DataFrame(_conv_rows)
        fig_conv = go.Figure()
        for rank, colour in [("#1", "#3b82f6"), ("#10", "#8b5cf6")]:
            sub = _conv_df[_conv_df["rank"] == rank]
            fig_conv.add_trace(go.Scatter(
                x=sub["date"], y=sub["score"], name=rank,
                mode="lines+markers", line=dict(color=colour, width=2, shape="hv"),
                hovertemplate=f"{rank} GPQA: %{{y:.1f}}%<extra></extra>",
            ))
        fig_conv.update_layout(yaxis_title="GPQA Score (%)", **CHART_LAYOUT)
        st.plotly_chart(fig_conv, use_container_width=True)
        st.caption(_ATTR)

    # Lab Progress
    st.subheader("Lab Progress")
    st.caption("Best GPQA and SWE-Bench score per organisation over the last 12 months.")
    _col1, _col2 = st.columns(2)
    for _col_ui, _score_col, _label in [(_col1, "gpqa_score", "GPQA"), (_col2, "swe_bench_verified_score", "SWE-Bench")]:
        _lab = (_df.dropna(subset=[_score_col])
                   .groupby("organization")[_score_col].max()
                   .mul(100).reset_index()
                   .rename(columns={_score_col: "score", "organization": "org"})
                   .sort_values("score").tail(12))
        _lab["colour"] = _lab["org"].map(_ORG_TO_PROVIDER).map(PROVIDER_COLOURS).fillna("#6b7280")
        fig_lab = go.Figure(go.Bar(
            x=_lab["score"], y=_lab["org"], orientation="h",
            marker_color=_lab["colour"].tolist(),
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
        ))
        fig_lab.update_layout(title=f"Best {_label} by Org", xaxis_title=f"{_label} Score (%)", height=380, **CHART_LAYOUT)
        _col_ui.plotly_chart(fig_lab, use_container_width=True)
    st.caption(_ATTR)

    # Organisation SOTA Progress
    st.subheader("Organization Progress")
    st.caption("Best GPQA score per organisation over time.")
    _top_orgs = (_df.dropna(subset=["gpqa_score"]).groupby("organization")["gpqa_score"].max()
                    .sort_values(ascending=False).head(8).index.tolist())
    fig_org = go.Figure()
    for org in _top_orgs:
        _prog = _sota_prog(_df[_df["organization"] == org], "gpqa_score")
        if _prog.empty:
            continue
        colour = PROVIDER_COLOURS.get(_ORG_TO_PROVIDER.get(org, ""), "#6b7280")
        _prog_ext = pd.concat([_prog, pd.DataFrame([{"date": _df["release_date"].max(), "score": _prog["score"].iloc[-1], "model": ""}])], ignore_index=True)
        fig_org.add_trace(go.Scatter(
            x=_prog_ext["date"], y=_prog_ext["score"], name=org,
            mode="lines", line=dict(color=colour, width=2, shape="hv"),
            hovertemplate=f"{org}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_org.update_layout(yaxis_title="GPQA Score (%)", **CHART_LAYOUT)
    st.plotly_chart(fig_org, use_container_width=True)
    st.caption(_ATTR)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 3 — Labs and Countries
    # ═══════════════════════════════════════════════════════════════════
    st.header("Labs and Countries")
    st.caption("Who is leading, who is shipping the most, and how the balance of power is shifting.")

    _col1, _col2 = st.columns(2)
    # Country totals bar
    _ctry_counts = _df["country"].value_counts().reset_index()
    _ctry_counts.columns = ["country", "count"]
    fig_ctry = go.Figure(go.Bar(
        x=_ctry_counts["count"], y=_ctry_counts["country"], orientation="h",
        marker_color="#3b82f6",
        hovertemplate="%{y}: %{x} models<extra></extra>",
    ))
    fig_ctry.update_layout(title="Cumulative Releases by Country", xaxis_title="Models", yaxis=dict(autorange="reversed"), height=300, **CHART_LAYOUT)
    _col1.plotly_chart(fig_ctry, use_container_width=True)

    # Release heatmap
    _hm = _df.groupby(["year", "month"]).size().reset_index(name="count")
    _hm_piv = _hm.pivot(index="year", columns="month", values="count").fillna(0)
    _month_abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    _hm_piv.columns = [_month_abbr[c - 1] for c in _hm_piv.columns]
    fig_hm = go.Figure(go.Heatmap(
        z=_hm_piv.values, x=_hm_piv.columns.tolist(), y=_hm_piv.index.tolist(),
        colorscale="Blues", text=_hm_piv.values.astype(int), texttemplate="%{text}",
        hovertemplate="Year: %{y} · %{x}: %{z} releases<extra></extra>",
    ))
    fig_hm.update_layout(title="Release Heatmap", height=300, **CHART_LAYOUT)
    _col2.plotly_chart(fig_hm, use_container_width=True)

    _col1, _col2 = st.columns(2)
    # Country share over time
    _top5c = _df["country"].value_counts().head(5).index.tolist()
    _df["country_grp"] = _df["country"].apply(lambda c: c if c in _top5c else "Other")
    _qc = _df.groupby(["quarter", "country_grp"]).size().reset_index(name="count")
    _qc["pct"] = _qc.groupby("quarter")["count"].transform(lambda x: x / x.sum() * 100)
    _ctry_clrs = {"US": "#3b82f6", "CN": "#ef4444", "FR": "#10b981",
                  "GB": "#f59e0b", "IL": "#8b5cf6", "KR": "#ec4899",
                  "IN": "#06b6d4", "CA": "#a78bfa", "Other": "#6b7280"}
    _ctry_labels = {"US": "United States", "CN": "China", "FR": "France",
                    "GB": "United Kingdom", "IL": "Israel", "KR": "South Korea",
                    "IN": "India", "CA": "Canada", "Other": "Other"}
    fig_ctry_area = go.Figure()
    for ctry in _top5c + ["Other"]:
        colour = _ctry_clrs.get(ctry, "#6b7280")
        label = _ctry_labels.get(ctry, ctry)
        sub = _qc[_qc["country_grp"] == ctry]
        if sub.empty:
            continue
        fig_ctry_area.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["pct"], name=label, stackgroup="one",
            line=dict(color=colour, width=0),
            fillcolor=colour,
            hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_ctry_area.update_layout(title="Model Releases by Country (% share)", yaxis_title="Share (%)", height=320, **CHART_LAYOUT)
    _col1.plotly_chart(fig_ctry_area, use_container_width=True)

    # Cumulative releases by lab
    _top8labs = _df["organization"].value_counts().head(8).index.tolist()
    _total = len(_df)
    fig_labs = go.Figure()
    for org in _top8labs:
        sub = _df[_df["organization"] == org].groupby("quarter").size().reset_index(name="n")
        sub = sub.sort_values("quarter")
        sub["cum_pct"] = sub["n"].cumsum() / _total * 100
        colour = PROVIDER_COLOURS.get(_ORG_TO_PROVIDER.get(org, ""), "#6b7280")
        fig_labs.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["cum_pct"], name=org,
            mode="lines", line=dict(color=colour, width=1.5),
            hovertemplate=f"{org}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_labs.update_layout(title="Cumulative Releases by Lab (% of total)", yaxis_title="Cumulative Share (%)", height=320, **CHART_LAYOUT)
    _col2.plotly_chart(fig_labs, use_container_width=True)
    st.caption(_ATTR)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 4 — Open Models
    # ═══════════════════════════════════════════════════════════════════
    st.header("Open Models")
    st.caption("How open-weight models are growing, how close they are to proprietary systems, and where the open race is happening.")

    _col1, _col2 = st.columns(2)
    # Open vs Proprietary share
    _ql = _df.groupby(["quarter", "is_open"]).size().reset_index(name="count")
    _ql["pct"] = _ql.groupby("quarter")["count"].transform(lambda x: x / x.sum() * 100)
    fig_open = go.Figure()
    for lic, colour in [("Open Source", "#10b981"), ("Proprietary", "#f59e0b")]:
        sub = _ql[_ql["is_open"] == lic]
        fig_open.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["pct"], name=lic,
            mode="lines+markers", line=dict(color=colour, width=2),
            hovertemplate=f"{lic}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_open.update_layout(title="Open vs Proprietary Releases (%)", yaxis_title="Share (%)", height=320, **CHART_LAYOUT)
    _col1.plotly_chart(fig_open, use_container_width=True)

    # Closing gap: closed vs open SOTA GPQA
    fig_gap = go.Figure()
    for grp, colour in [("Proprietary", "#f59e0b"), ("Open Source", "#10b981")]:
        _prog = _sota_prog(_df[_df["is_open"] == grp], "gpqa_score")
        if _prog.empty:
            continue
        _prog_ext = pd.concat([_prog, pd.DataFrame([{"date": _df["release_date"].max(), "score": _prog["score"].iloc[-1], "model": ""}])], ignore_index=True)
        fig_gap.add_trace(go.Scatter(
            x=_prog_ext["date"], y=_prog_ext["score"], name=grp,
            mode="lines", line=dict(color=colour, width=2, shape="hv"),
            hovertemplate=f"{grp} SOTA: %{{y:.1f}}%<extra></extra>",
        ))
    fig_gap.update_layout(title="The Closing Gap — GPQA SOTA", yaxis_title="GPQA Score (%)", height=320, **CHART_LAYOUT)
    _col2.plotly_chart(fig_gap, use_container_width=True)

    # US vs China: open vs closed race
    _df["race_grp"] = _df.apply(
        lambda r: f"{'US' if r['country'] == 'US' else 'CN'} {r['is_open']}"
        if r["country"] in ("US", "CN") else None, axis=1)
    fig_race = go.Figure()
    for grp, colour in [("US Open Source", "#10b981"), ("US Proprietary", "#3b82f6"),
                         ("CN Open Source", "#f59e0b"), ("CN Proprietary", "#ef4444")]:
        mask = _df["race_grp"] == grp
        if not mask.any():
            continue
        _prog = _sota_prog(_df[mask], "gpqa_score")
        if _prog.empty:
            continue
        _prog_ext = pd.concat([_prog, pd.DataFrame([{"date": _df["release_date"].max(), "score": _prog["score"].iloc[-1], "model": ""}])], ignore_index=True)
        fig_race.add_trace(go.Scatter(
            x=_prog_ext["date"], y=_prog_ext["score"], name=grp,
            mode="lines", line=dict(color=colour, width=2, shape="hv"),
            hovertemplate=f"{grp}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_race.update_layout(title="Open Weights Race: US vs China (GPQA SOTA)",
        yaxis_title="GPQA Score (%)", yaxis_range=[0, 105], **CHART_LAYOUT)
    st.plotly_chart(fig_race, use_container_width=True)
    st.caption(_ATTR)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 5 — Model Capabilities
    # ═══════════════════════════════════════════════════════════════════
    st.header("Model Capabilities")
    st.caption("What kinds of models are being released, from multimodal systems to MoE-based open models.")

    _col1, _col2 = st.columns(2)
    # Multimodal shift
    _qmm = (_df.groupby("quarter").apply(
        lambda g: pd.Series({
            "Multimodal": (g["multimodal"] == True).sum() / len(g) * 100,  # noqa: E712
            "Text-only":  (g["multimodal"] != True).sum() / len(g) * 100,  # noqa: E712
        })).reset_index().melt(id_vars="quarter", var_name="type", value_name="pct"))
    fig_mm = go.Figure()
    for typ, colour in [("Multimodal", "#8b5cf6"), ("Text-only", "#3b82f6")]:
        sub = _qmm[_qmm["type"] == typ]
        fig_mm.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["pct"], name=typ,
            mode="lines+markers", line=dict(color=colour, width=2),
            hovertemplate=f"{typ}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_mm.update_layout(title="The Multimodal Shift", yaxis_title="% of New Releases", height=320, **CHART_LAYOUT)
    _col1.plotly_chart(fig_mm, use_container_width=True)

    # MoE adoption scatter (open models)
    _moe_df = _df[_df["is_open"] == "Open Source"].dropna(subset=["gpqa_score"]).copy()
    if not _moe_df.empty:
        _moe_df["arch"] = _moe_df["is_moe"].apply(lambda x: "MoE" if x is True else "Dense")
        fig_moe = go.Figure()
        for arch, colour in [("MoE", "#10b981"), ("Dense", "#6b7280")]:
            sub = _moe_df[_moe_df["arch"] == arch]
            fig_moe.add_trace(go.Scatter(
                x=sub["release_date"], y=sub["gpqa_score"] * 100, text=sub["name"],
                name=arch, mode="markers",
                marker=dict(color=colour, size=8, opacity=0.8),
                hovertemplate="%{text}: %{y:.1f}%<extra></extra>",
            ))
        fig_moe.update_layout(title="MoE Adoption — Open Models", xaxis_title="Release Date", yaxis_title="GPQA Score (%)", height=320, **CHART_LAYOUT)
        _col2.plotly_chart(fig_moe, use_container_width=True)
    st.caption(_ATTR)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 6 — Prices and Value
    # ═══════════════════════════════════════════════════════════════════
    st.header("Prices and Value")
    st.caption("How fast intelligence is getting cheaper, which models deliver the most value, and where prices differ.")

    # Price by country strip/box
    st.subheader("Price by Country")
    _pd = _df.dropna(subset=["input_price", "country"])
    _pd = _pd[_pd["input_price"] > 0]
    if not _pd.empty:
        _top4c = _pd["country"].value_counts().head(4).index.tolist()
        _pd_top = _pd[_pd["country"].isin(_top4c)]
        fig_pbc = go.Figure()
        for ctry in _top4c:
            sub = _pd_top[_pd_top["country"] == ctry]
            fig_pbc.add_trace(go.Box(
                y=sub["input_price"], name=ctry, boxpoints="all", jitter=0.5,
                pointpos=0, marker_size=5,
                text=sub["name"].tolist(),
                hovertemplate="%{text}: $%{y:.3f}/M tokens<extra></extra>",
            ))
        fig_pbc.update_layout(yaxis_title="Input Price ($/1M tokens)", yaxis_type="log", **CHART_LAYOUT)
        st.plotly_chart(fig_pbc, use_container_width=True)
        st.caption(_ATTR)

    # Performance vs Price — GPQA and SWE-Bench Pareto frontiers
    st.subheader("Price Frontiers")
    st.caption("Capability vs API cost — Pareto frontier shows the best value per dollar.")
    _col1, _col2 = st.columns(2)
    for _col_ui, _sc, _lb in [(_col1, "gpqa_score", "GPQA"), (_col2, "swe_bench_verified_score", "SWE-Bench")]:
        _pp = _df.dropna(subset=[_sc, "input_price"])
        _pp = _pp[_pp["input_price"] > 0].copy()
        if _pp.empty:
            continue
        _pf = _pareto_front(_pp, "input_price", _sc)
        fig_pp = go.Figure()
        for prov in sorted(_pp["provider"].unique()):
            sub = _pp[_pp["provider"] == prov]
            fig_pp.add_trace(go.Scatter(
                x=sub["input_price"], y=sub[_sc] * 100, text=sub["name"],
                name=prov, mode="markers",
                marker=dict(color=PROVIDER_COLOURS.get(prov, "#6b7280"), size=7, opacity=0.8),
                hovertemplate="%{text}<br>$%{x:.3f}/M · %{y:.1f}%<extra></extra>",
            ))
        if not _pf.empty:
            fig_pp.add_trace(go.Scatter(
                x=_pf["input_price"], y=_pf[_sc] * 100,
                mode="lines", name="Pareto front",
                line=dict(color="#ffffff", width=1.5, dash="dot", shape="hv"), showlegend=False,
            ))
        fig_pp.update_layout(title=f"{_lb} vs Price", xaxis_title="Input Price ($/1M tokens)",
            yaxis_title=f"{_lb} Score (%)", height=380, showlegend=False, **CHART_LAYOUT)
        _col_ui.plotly_chart(fig_pp, use_container_width=True)
    st.caption(_ATTR)

    # Value Evolution
    st.subheader("Value Evolution")
    st.caption("GPQA score per dollar by release quarter — the rising value of intelligence.")
    _ve = _df.dropna(subset=["gpqa_score", "input_price"])
    _ve = _ve[_ve["input_price"] > 0].copy()
    _ve["gpqa_per_dollar"] = (_ve["gpqa_score"] * 100) / _ve["input_price"]
    if not _ve.empty:
        _ve_q = _ve.groupby(["quarter", "provider"])["gpqa_per_dollar"].median().reset_index()
        fig_ve = go.Figure()
        for prov in sorted(_ve_q["provider"].unique()):
            sub = _ve_q[_ve_q["provider"] == prov]
            fig_ve.add_trace(go.Scatter(
                x=sub["quarter"], y=sub["gpqa_per_dollar"], name=prov,
                mode="lines+markers",
                line=dict(color=PROVIDER_COLOURS.get(prov, "#6b7280"), width=1.5),
                hovertemplate=f"{prov}: %{{y:.1f}} GPQA pts/$1M<extra></extra>",
            ))
        fig_ve.update_layout(yaxis_title="GPQA pts per $1M tokens", yaxis_type="log", **CHART_LAYOUT)
        st.plotly_chart(fig_ve, use_container_width=True)
        st.caption(_ATTR)

    # Cost Efficiency by Tier
    st.subheader("Cost Efficiency by Tier")
    st.caption("Cost per GPQA point across model size tiers.")
    _ct = _df.dropna(subset=["gpqa_score", "input_price", "params"])
    _ct = _ct[(_ct["input_price"] > 0) & (_ct["params"] > 0)].copy()
    if not _ct.empty:
        _ct["tier"] = pd.cut(_ct["params"],
            bins=[0, 10e9, 70e9, 200e9, float("inf")],
            labels=["Tiny (<10B)", "Small (10–70B)", "Large (70–200B)", "Frontier (200B+)"])
        _ct["cost_per_gpqa"] = _ct["input_price"] / (_ct["gpqa_score"] * 100)
        fig_ct = go.Figure()
        for typ, colour in [("Open Source", "#10b981"), ("Proprietary", "#f59e0b")]:
            sub = _ct[_ct["is_open"] == typ]
            if sub.empty:
                continue
            fig_ct.add_trace(go.Box(
                x=sub["tier"].astype(str), y=sub["cost_per_gpqa"], name=typ,
                boxpoints="all", jitter=0.5, pointpos=0, marker_size=5,
                marker_color=colour, text=sub["name"].tolist(),
                hovertemplate="%{text}: $%{y:.5f}/GPQA pt<extra></extra>",
            ))
        fig_ct.update_layout(yaxis_title="$/GPQA point (input price)", yaxis_type="log", **CHART_LAYOUT)
        st.plotly_chart(fig_ct, use_container_width=True)
        st.caption(_ATTR)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 7 — Efficiency and Scale
    # ═══════════════════════════════════════════════════════════════════
    st.header("Efficiency and Scale")
    st.caption("How architecture, parameters, and training scale affect capability.")

    _col1, _col2 = st.columns(2)
    # Performance vs Price by MoE
    _mp = _df.dropna(subset=["gpqa_score", "blended_price"])
    _mp = _mp[_mp["blended_price"] > 0].copy()
    if not _mp.empty:
        _mp["arch"] = _mp["is_moe"].apply(lambda x: "MoE" if x is True else "Dense")
        fig_moe_p = go.Figure()
        for arch, colour in [("MoE", "#10b981"), ("Dense", "#6b7280")]:
            sub = _mp[_mp["arch"] == arch]
            fig_moe_p.add_trace(go.Scatter(
                x=sub["blended_price"], y=sub["gpqa_score"] * 100, text=sub["name"],
                name=arch, mode="markers",
                marker=dict(color=colour, size=7, opacity=0.8),
                hovertemplate="%{text}<br>$%{x:.3f}/M · %{y:.1f}%<extra></extra>",
            ))
        fig_moe_p.update_layout(title="Performance vs Price by Architecture (MoE vs Dense)",
            xaxis_title="Blended Price ($/1M tokens)", xaxis_type="log",
            yaxis_title="GPQA Score (%)", height=360, **CHART_LAYOUT)
        _col1.plotly_chart(fig_moe_p, use_container_width=True)

    # GPQA by model size tier
    _t2 = _df.dropna(subset=["gpqa_score", "params"])
    _t2 = _t2[_t2["params"] > 0].copy()
    if not _t2.empty:
        _t2["tier"] = pd.cut(_t2["params"],
            bins=[0, 10e9, 70e9, 200e9, float("inf")],
            labels=["Tiny (<10B)", "Small (10–70B)", "Large (70–200B)", "Frontier (200B+)"])
        fig_t2 = go.Figure()
        for tier_lbl, colour in [("Tiny (<10B)", "#6b7280"), ("Small (10–70B)", "#3b82f6"),
                                  ("Large (70–200B)", "#f59e0b"), ("Frontier (200B+)", "#ef4444")]:
            sub = _t2[_t2["tier"].astype(str) == tier_lbl]
            if sub.empty:
                continue
            fig_t2.add_trace(go.Box(
                x=sub["tier"].astype(str), y=sub["gpqa_score"] * 100, name=tier_lbl,
                boxpoints="all", jitter=0.5, pointpos=0,
                marker_color=colour, marker_size=5,
                text=sub["name"].tolist(),
                hovertemplate="%{text}: %{y:.1f}%<extra></extra>",
            ))
        fig_t2.update_layout(title="GPQA Score by Model Size Tier",
            xaxis_title="Model Tier", yaxis_title="GPQA Score (%)",
            showlegend=False, height=360, **CHART_LAYOUT)
        _col2.plotly_chart(fig_t2, use_container_width=True)

    # The Efficiency Curve
    st.subheader("The Efficiency Curve")
    st.caption("Smallest model to reach each GPQA threshold — intelligence is getting smaller.")
    _eff = _df.dropna(subset=["gpqa_score", "params"])
    _eff = _eff[_eff["params"] > 0].sort_values("release_date")
    if not _eff.empty:
        fig_eff = go.Figure()
        for thresh, colour in [(0.4, "#6b7280"), (0.5, "#3b82f6"), (0.6, "#10b981"), (0.7, "#f59e0b"), (0.8, "#ef4444")]:
            _above = _eff[_eff["gpqa_score"] >= thresh]
            if _above.empty:
                continue
            rows, min_p = [], float("inf")
            for _, r in _above.iterrows():
                if r["params"] < min_p:
                    min_p = r["params"]
                    rows.append({"date": r["release_date"], "params": min_p, "model": r["name"]})
            if not rows:
                continue
            _ep = pd.DataFrame(rows)
            _ep_ext = pd.concat([_ep, pd.DataFrame([{"date": _df["release_date"].max(), "params": _ep["params"].iloc[-1], "model": ""}])], ignore_index=True)
            fig_eff.add_trace(go.Scatter(
                x=_ep_ext["date"], y=_ep_ext["params"],
                name=f"{int(thresh*100)}% GPQA", mode="lines",
                line=dict(color=colour, width=2, shape="hv"),
                hovertemplate=f"{int(thresh*100)}% GPQA: %{{y:.2e}} params<extra></extra>",
            ))
        fig_eff.update_layout(yaxis_title="Parameters", yaxis_type="log", **CHART_LAYOUT)
        st.plotly_chart(fig_eff, use_container_width=True)
    st.caption(_ATTR)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 8 — Speed and Context
    # ═══════════════════════════════════════════════════════════════════
    st.header("Speed and Context")
    st.caption("What you trade off when deploying models: throughput, context length, and how speed costs capability.")

    _col1, _col2 = st.columns(2)
    # Speed Tax: GPQA vs throughput
    _sp = _df.dropna(subset=["gpqa_score", "throughput"])
    _sp = _sp[_sp["throughput"] > 0].copy()
    if not _sp.empty:
        _pf_sp = _pareto_front(_sp, "throughput", "gpqa_score")
        fig_sp = go.Figure()
        for typ, colour, sym in [("Open Source", "#10b981", "circle"), ("Proprietary", "#f59e0b", "diamond")]:
            sub = _sp[_sp["is_open"] == typ]
            fig_sp.add_trace(go.Scatter(
                x=sub["throughput"], y=sub["gpqa_score"] * 100, text=sub["name"],
                name=typ, mode="markers",
                marker=dict(color=colour, size=7, opacity=0.8, symbol=sym),
                hovertemplate="%{text}<br>%{x:.0f} tok/s · %{y:.1f}%<extra></extra>",
            ))
        if not _pf_sp.empty:
            fig_sp.add_trace(go.Scatter(
                x=_pf_sp["throughput"], y=_pf_sp["gpqa_score"] * 100,
                mode="lines", showlegend=False,
                line=dict(color="#ffffff", width=1.5, dash="dot"),
            ))
        fig_sp.update_layout(title="The Speed Tax — GPQA vs Throughput",
            xaxis_title="Throughput (tok/s)", yaxis_title="GPQA Score (%)", height=360, **CHART_LAYOUT)
        _col1.plotly_chart(fig_sp, use_container_width=True)

    # SWE-Bench vs throughput
    _ss = _df.dropna(subset=["swe_bench_verified_score", "throughput"])
    _ss = _ss[_ss["throughput"] > 0].copy()
    if not _ss.empty:
        _pf_ss = _pareto_front(_ss, "throughput", "swe_bench_verified_score")
        fig_ss = go.Figure()
        for typ, colour in [("Open Source", "#10b981"), ("Proprietary", "#f59e0b")]:
            sub = _ss[_ss["is_open"] == typ]
            fig_ss.add_trace(go.Scatter(
                x=sub["throughput"], y=sub["swe_bench_verified_score"] * 100, text=sub["name"],
                name=typ, mode="markers",
                marker=dict(color=colour, size=7, opacity=0.8),
                hovertemplate="%{text}<br>%{x:.0f} tok/s · %{y:.1f}%<extra></extra>",
            ))
        if not _pf_ss.empty:
            fig_ss.add_trace(go.Scatter(
                x=_pf_ss["throughput"], y=_pf_ss["swe_bench_verified_score"] * 100,
                mode="lines", showlegend=False,
                line=dict(color="#ffffff", width=1.5, dash="dot"),
            ))
        fig_ss.update_layout(title="SWE-Bench vs Throughput",
            xaxis_title="Throughput (tok/s)", yaxis_title="SWE-Bench Score (%)", height=360, **CHART_LAYOUT)
        _col2.plotly_chart(fig_ss, use_container_width=True)
    st.caption(_ATTR)

    # ═══════════════════════════════════════════════════════════════════
    # SECTION 9 — Human Preference Map
    # ═══════════════════════════════════════════════════════════════════
    st.header("Human Preference")
    st.caption("How models rank when humans judge them head-to-head, vs. how they score on automated benchmarks.")

    st.subheader("Human Preference Map")
    _explainer(
        what="Each dot is a model. X-axis: composite benchmark score (mean of GPQA, SWE-Bench, HLE, AIME-2025). Y-axis: Chatbot Arena Elo — human-rated preference from blind head-to-head votes. Hover for model name.",
        why="A model can ace benchmarks but rank poorly on human preference (e.g. too terse, poor formatting). The map shows whether labs are optimising for benchmark leaderboards or real-world usability, and which models are genuinely best by both measures.",
        source="Benchmark scores: api.zeroeval.com. Arena Elo: LMSYS Chatbot Arena — updated via /ai-research skill.",
    )
    if not df_elo.empty:
        _bench_score = _df[["name", "organization"] + _BENCH_COLS].copy()
        _bench_score["composite"] = _bench_score[_BENCH_COLS].mean(axis=1, skipna=True).mul(100)
        _bench_score = _bench_score.dropna(subset=["composite"])
        _bench_score["provider"] = _bench_score["organization"].map(_ORG_TO_PROVIDER).fillna(_bench_score["organization"])

        # Fuzzy join: lowercase strip both sides
        _bench_score["_key"] = _bench_score["name"].str.lower().str.strip()
        _elo_join = df_elo.copy()
        _elo_join["_key"] = _elo_join["model"].str.lower().str.strip()
        _hp = _bench_score.merge(_elo_join[["_key", "elo"]], on="_key", how="inner")

        if not _hp.empty:
            fig_hp = go.Figure()
            for prov in sorted(_hp["provider"].unique()):
                sub = _hp[_hp["provider"] == prov]
                fig_hp.add_trace(go.Scatter(
                    x=sub["composite"], y=sub["elo"], text=sub["name"],
                    name=prov, mode="markers", showlegend=False,
                    marker=dict(color=PROVIDER_COLOURS.get(prov, "#6b7280"), size=9, opacity=0.85,
                                line=dict(width=1, color="rgba(255,255,255,0.3)")),
                    hovertemplate="%{text}<br>Composite: %{x:.1f}%<br>Elo: %{y:,d}<extra></extra>",
                ))
            fig_hp.update_layout(
                xaxis_title="Composite Benchmark Score (%)",
                yaxis_title="Arena Elo (Human Preference)",
                height=480, **CHART_LAYOUT,
            )
            st.plotly_chart(fig_hp, use_container_width=True)
            st.caption(_ATTR + " · Arena Elo from LMSYS Chatbot Arena via /ai-research skill.")
        else:
            st.info("No model overlap between ZeroEval benchmarks and Arena Elo — run /ai-research to populate Arena Elo.")
    else:
        st.info("Arena Elo data not yet loaded. Run /ai-research to populate.")


# ═════════════════════════════════════════════════════════════════════════
# SECTION 10 — API Pricing Over Time
# ═════════════════════════════════════════════════════════════════════════
st.header("API Pricing (Historical)")


@st.cache_data(ttl=86400)
def load_token_prices() -> pd.DataFrame:
    csv = DATA_DIR / "token_prices_history.csv"
    if not csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv)
    df["date"] = pd.to_datetime(df["date"])
    df["blended_usd_per_mtok"] = (3 * df["input_usd_per_mtok"] + df["output_usd_per_mtok"]) / 4
    return df


token_df = load_token_prices()

if token_df.empty:
    st.warning("Token price history CSV missing. Expected at data/reference/token_prices_history.csv")
else:
    st.subheader("Blended API Cost Over Time")
    _explainer(
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
            x=sub["date"],
            y=sub["blended_usd_per_mtok"],
            text=sub["model"],
            customdata=sub[["input_usd_per_mtok", "output_usd_per_mtok"]].values,
            name=provider,
            mode="markers+lines",
            line=dict(color=PROVIDER_COLOURS[provider], width=1.2),
            marker=dict(size=8, color=PROVIDER_COLOURS[provider]),
            hovertemplate=(
                "%{text}<br>"
                "Blended: $%{y:.2f} / M tokens<br>"
                "Input: $%{customdata[0]:.2f}<br>"
                "Output: $%{customdata[1]:.2f}"
                f"<extra>{provider}</extra>"
            ),
        ))

    fig_price.update_layout(
        yaxis_title="$ per million tokens (blended 3×input + 1×output)",
        yaxis_type="log",
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_price, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════
# SECTION 4 — Live Leaderboard
# ═════════════════════════════════════════════════════════════════════════
st.header("Live Leaderboard")
st.caption("Arena Elo ratings, intelligence-vs-cost frontier, and context window leaders.")

# Build df_specs from live ZeroEval data
if not _ze_df.empty:
    df_specs = _ze_df.copy()
    df_specs["provider"] = df_specs["organization"].map(_ORG_TO_PROVIDER).fillna(df_specs["organization"])
    df_specs["model"] = df_specs["name"]
    df_specs["input_price_per_m_tokens"] = df_specs["input_price"]
    df_specs["context_window"] = df_specs["context"]
    _bench_cols_full = ["gpqa_score", "swe_bench_verified_score", "hle_score", "aime_2025_score", "mmmlu_score"]
    df_specs["intelligence_score"] = df_specs[_bench_cols_full].mean(axis=1, skipna=True).mul(100)
else:
    df_specs = pd.DataFrame()

st.subheader("Arena Elo Ratings")
_explainer(
    what="Chatbot Arena (lmsys.org) Elo scores — a head-to-head blind preference tournament where humans choose between model responses. Elo is computed from win rates across millions of votes.",
    why="Human preference Elo is the most neutral capability signal available. It has no benchmark contamination problem and aligns with what users actually prefer. It's the one metric all providers accept as credible.",
    source="LMSYS Chatbot Arena leaderboard (chat.lmsys.org). Updated via /ai-research skill.",
)
if not df_elo.empty:
    _vis = [p for p in df_elo["provider"].unique() if p in sel_providers] if sel_providers else df_elo["provider"].unique().tolist()
    df_elo_vis = df_elo[df_elo["provider"].isin(_vis)] if _vis else df_elo
    _elo_top = df_elo_vis.head(15).copy()
    _elo_min = _elo_top["elo"].min()
    _elo_floor = round(_elo_min * 0.95)  # 5% below worst score
    _elo_top["elo_offset"] = _elo_top["elo"] - _elo_floor
    fig_elo = px.bar(
        _elo_top, x="elo_offset", y="model", color="provider",
        orientation="h", title="Top 15 by Elo",
        text="elo", custom_data=["elo"],
        color_discrete_map=PROVIDER_COLOURS,
    )
    fig_elo.update_traces(base=_elo_floor, textposition="outside", textfont_size=10,
                          hovertemplate="Elo Score=%{customdata[0]}<br>model=%{y}<extra></extra>")
    fig_elo.update_layout(height=450, yaxis=dict(autorange="reversed"), xaxis=dict(title_text="Elo Score"), **CHART_LAYOUT)
    st.plotly_chart(fig_elo, use_container_width=True)

st.subheader("Intelligence vs Cost Frontier")
_explainer(
    what="Each model plotted at its list input price (x-axis) vs composite intelligence index (y-axis). The Pareto frontier moves left and up over time — models that were SOTA 12 months ago are now dominated on both axes.",
    why="As intelligence commoditises, can any provider maintain pricing power? This chart shows how fast the frontier is shifting — and whether there is still a capability moat at the top end that justifies premium pricing.",
    source="api.zeroeval.com — benchmark scores (GPQA, SWE-Bench, HLE, AIME-2025, MMMLU) averaged for composite intelligence index. Pricing from provider API list rates.",
)
if not df_specs.empty:
    df_plot = df_specs.dropna(subset=["intelligence_score", "input_price_per_m_tokens"])
    if not df_plot.empty:
        _vis2 = [p for p in df_plot["provider"].unique() if p in sel_providers] if sel_providers else df_plot["provider"].unique().tolist()
        df_plot = df_plot[df_plot["provider"].isin(_vis2)] if _vis2 else df_plot
        fig_frontier = px.scatter(
            df_plot, x="input_price_per_m_tokens", y="intelligence_score",
            text="model", color="provider",
            title="Intelligence Index vs $/1M Input Tokens",
            labels={"input_price_per_m_tokens": "$/1M Input Tokens", "intelligence_score": "Intelligence Index"},
            color_discrete_map=PROVIDER_COLOURS,
        )
        fig_frontier.update_traces(textposition="top center", textfont_size=9)
        fig_frontier.update_layout(height=450, **CHART_LAYOUT)
        st.plotly_chart(fig_frontier, use_container_width=True)

if not df_specs.empty:
    df_ctx = df_specs.dropna(subset=["context_window"]).sort_values("context_window", ascending=False)
    df_ctx = df_ctx[~df_ctx["model"].str.contains("Llama 4 Scout", case=False, na=False)]
    if not df_ctx.empty:
        st.subheader("Context Window Leaders")
        _explainer(
            what="Current snapshot: the 10 models with the largest maximum context windows, in thousands of tokens. Companion to the Context Window Expansion time-series above.",
            why="Context window is a hard application constraint. Models that can ingest entire codebases or documents without chunking enable qualitatively different workflows. The jump from 4K → 1M+ tokens represents a category shift, not just a spec improvement.",
            source="api.zeroeval.com — context window from model metadata, updated hourly.",
        )
        df_ctx = df_ctx.copy()
        df_ctx["ctx_k"] = df_ctx["context_window"] / 1000
        _vis3 = [p for p in df_ctx["provider"].unique() if p in sel_providers] if sel_providers else df_ctx["provider"].unique().tolist()
        df_ctx_vis = df_ctx[df_ctx["provider"].isin(_vis3)] if _vis3 else df_ctx
        fig_ctx = px.bar(
            df_ctx_vis.head(10), x="ctx_k", y="model", orientation="h",
            title="Top 10 by Context Window (K tokens)",
            labels={"ctx_k": "Context Window (K tokens)"}, color="provider",
            color_discrete_map=PROVIDER_COLOURS,
        )
        fig_ctx.update_layout(height=350, yaxis=dict(autorange="reversed"), **CHART_LAYOUT)
        st.plotly_chart(fig_ctx, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════
# FOOTER — attribution
# ═════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption(
    "Data sources: LLM Stats (llm-stats.com) · Epoch AI (ML Hardware dataset, CC-BY) · Silicon Data (H100 Rental Index blog) · "
    "provider model cards & release announcements. Benchmark scores are vendor-reported unless otherwise noted."
)
