"""Model Performance — AI model benchmarks, context windows, pricing, and compute hardware."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.lib.hardware import ARCH_COLOURS, ARCH_ORDER, flagship_per_generation, load_nvidia_dc_gpus

CHART_LAYOUT = dict(
    font=dict(family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12),
)

st.title("Model Performance")
st.caption("Frontier AI model benchmarks, context windows, API pricing, and compute hardware.")

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"

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
]

# ═════════════════════════════════════════════════════════════════════════
# DATA — Benchmarks
# ═════════════════════════════════════════════════════════════════════════
BENCHMARKS = {
    "MMLU": {
        "description": "Massive Multitask Language Understanding — 57 subjects, knowledge breadth. Now largely saturated above ~90%.",
        "why": "The 'SAT for LLMs' — first benchmark to demonstrate broad general knowledge. Now saturated; newer benchmarks (MMLU-Pro, GPQA) have replaced it as frontier signal.",
        "source": "Hendrycks et al. 2020 (arXiv:2009.03300); scores from model cards & papers.",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4",              "date": "2023-03", "score": 86.4, "provider": "OpenAI"},
            {"model": "Claude 2",           "date": "2023-07", "score": 78.5, "provider": "Anthropic"},
            {"model": "Gemini Ultra",       "date": "2023-12", "score": 90.0, "provider": "Google"},
            {"model": "Mixtral 8x22B",      "date": "2024-04", "score": 77.8, "provider": "Mistral"},
            {"model": "Llama 3 70B",        "date": "2024-04", "score": 82.0, "provider": "Meta"},
            {"model": "DeepSeek V2",        "date": "2024-05", "score": 78.5, "provider": "DeepSeek"},
            {"model": "GPT-4o",             "date": "2024-05", "score": 88.7, "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet",  "date": "2024-06", "score": 88.7, "provider": "Anthropic"},
            {"model": "Llama 3.1 405B",     "date": "2024-07", "score": 87.3, "provider": "Meta"},
            {"model": "Mistral Large 2",    "date": "2024-07", "score": 84.0, "provider": "Mistral"},
            {"model": "Grok 2",             "date": "2024-08", "score": 87.5, "provider": "xAI"},
            {"model": "Gemini 1.5 Pro",     "date": "2024-08", "score": 85.9, "provider": "Google"},
            {"model": "Qwen 2.5 72B",       "date": "2024-09", "score": 85.0, "provider": "Alibaba"},
            {"model": "o1",                 "date": "2024-09", "score": 92.3, "provider": "OpenAI"},
            {"model": "DeepSeek V3",        "date": "2024-12", "score": 88.5, "provider": "DeepSeek"},
            {"model": "Llama 3.3 70B",      "date": "2024-12", "score": 86.0, "provider": "Meta"},
            {"model": "DeepSeek R1",        "date": "2025-01", "score": 90.8, "provider": "DeepSeek"},
            {"model": "Claude 4 Opus",      "date": "2025-05", "score": 93.0, "provider": "Anthropic"},
        ],
    },
    "MMLU-Pro": {
        "description": "Harder, more discriminating MMLU variant — 10-option MCQ, expert-level questions. Top frontier models now sit ~80-87%.",
        "why": "MMLU became saturated in 2024; MMLU-Pro re-opens headroom with harder questions and more distractor options. Good current proxy for 'general-purpose intelligence'.",
        "source": "TIGER-Lab MMLU-Pro paper (2024); scores from model cards & Artificial Analysis.",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4o",              "date": "2024-05", "score": 72.6, "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet",   "date": "2024-06", "score": 78.0, "provider": "Anthropic"},
            {"model": "Llama 3.1 405B",      "date": "2024-07", "score": 73.4, "provider": "Meta"},
            {"model": "Mistral Large 2",     "date": "2024-07", "score": 68.4, "provider": "Mistral"},
            {"model": "Gemini 1.5 Pro",      "date": "2024-08", "score": 75.8, "provider": "Google"},
            {"model": "Qwen 2.5 72B",        "date": "2024-09", "score": 71.1, "provider": "Alibaba"},
            {"model": "o1",                  "date": "2024-09", "score": 80.3, "provider": "OpenAI"},
            {"model": "Llama 3.3 70B",       "date": "2024-12", "score": 68.9, "provider": "Meta"},
            {"model": "DeepSeek V3",         "date": "2024-12", "score": 75.9, "provider": "DeepSeek"},
            {"model": "Gemini 2.0 Flash",    "date": "2024-12", "score": 77.6, "provider": "Google"},
            {"model": "DeepSeek R1",         "date": "2025-01", "score": 84.0, "provider": "DeepSeek"},
            {"model": "Qwen 2.5 Max",        "date": "2025-01", "score": 76.1, "provider": "Alibaba"},
            {"model": "Grok 3",              "date": "2025-02", "score": 79.9, "provider": "xAI"},
            {"model": "Gemini 2.5 Pro",      "date": "2025-03", "score": 86.0, "provider": "Google"},
            {"model": "Llama 4 Maverick",    "date": "2025-04", "score": 80.5, "provider": "Meta"},
            {"model": "Llama 4 Behemoth",    "date": "2025-04", "score": 82.2, "provider": "Meta"},
            {"model": "Claude 4 Opus",       "date": "2025-05", "score": 84.0, "provider": "Anthropic"},
            {"model": "Mistral Medium 3",    "date": "2025-05", "score": 77.2, "provider": "Mistral"},
            {"model": "Grok 4",              "date": "2025-07", "score": 86.6, "provider": "xAI"},
            {"model": "Qwen3-235B Thinking", "date": "2025-07", "score": 84.4, "provider": "Alibaba"},
        ],
    },
    "GPQA Diamond": {
        "description": "Graduate-level science QA — physics, chemistry, biology expert questions (diamond subset is the hardest).",
        "why": "Tests reasoning at PhD-level science — 'Google-proof' questions that can't be answered by search. One of the clearest signals of reasoning capability.",
        "source": "Rein et al. 2023 (arXiv:2311.12022); scores from model cards & provider blogs.",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4",               "date": "2023-03", "score": 39.7, "provider": "OpenAI"},
            {"model": "Claude 3 Opus",       "date": "2024-03", "score": 60.4, "provider": "Anthropic"},
            {"model": "GPT-4o",              "date": "2024-05", "score": 53.6, "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet",   "date": "2024-06", "score": 65.0, "provider": "Anthropic"},
            {"model": "Llama 3.1 405B",      "date": "2024-07", "score": 50.7, "provider": "Meta"},
            {"model": "Grok 2",              "date": "2024-08", "score": 56.0, "provider": "xAI"},
            {"model": "Gemini 1.5 Pro",      "date": "2024-08", "score": 59.1, "provider": "Google"},
            {"model": "Qwen 2.5 72B",        "date": "2024-09", "score": 49.0, "provider": "Alibaba"},
            {"model": "o1",                  "date": "2024-09", "score": 78.0, "provider": "OpenAI"},
            {"model": "Llama 3.3 70B",       "date": "2024-12", "score": 50.5, "provider": "Meta"},
            {"model": "DeepSeek V3",         "date": "2024-12", "score": 59.1, "provider": "DeepSeek"},
            {"model": "Gemini 2.0 Flash",    "date": "2024-12", "score": 60.1, "provider": "Google"},
            {"model": "DeepSeek R1",         "date": "2025-01", "score": 71.5, "provider": "DeepSeek"},
            {"model": "Qwen 2.5 Max",        "date": "2025-01", "score": 60.1, "provider": "Alibaba"},
            {"model": "Grok 3 (Think)",      "date": "2025-02", "score": 84.6, "provider": "xAI"},
            {"model": "Gemini 2.5 Pro",      "date": "2025-03", "score": 84.0, "provider": "Google"},
            {"model": "Llama 4 Maverick",    "date": "2025-04", "score": 69.8, "provider": "Meta"},
            {"model": "Llama 4 Behemoth",    "date": "2025-04", "score": 73.7, "provider": "Meta"},
            {"model": "Claude 4 Opus",       "date": "2025-05", "score": 75.0, "provider": "Anthropic"},
            {"model": "Mistral Medium 3",    "date": "2025-05", "score": 57.1, "provider": "Mistral"},
            {"model": "DeepSeek R1-0528",    "date": "2025-05", "score": 81.0, "provider": "DeepSeek"},
            {"model": "Grok 4",              "date": "2025-07", "score": 88.0, "provider": "xAI"},
            {"model": "Qwen3-235B Thinking", "date": "2025-07", "score": 81.1, "provider": "Alibaba"},
        ],
    },
    "Humanity's Last Exam": {
        "description": "Extremely hard questions from domain experts — ceiling test for frontier models. Current SOTA ~24%.",
        "why": "Designed to be the 'last' benchmark humans can beat frontier models on. Scores near zero for all pre-2025 models, starting to climb now — watched closely as a capability ceiling indicator.",
        "source": "Scale AI & Center for AI Safety (agi.safe.ai); scores from HLE leaderboard.",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4o",              "date": "2024-05", "score": 3.3,  "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet",   "date": "2024-06", "score": 4.3,  "provider": "Anthropic"},
            {"model": "o1",                  "date": "2024-09", "score": 9.1,  "provider": "OpenAI"},
            {"model": "Gemini 2.0 Flash",    "date": "2024-12", "score": 6.2,  "provider": "Google"},
            {"model": "DeepSeek R1",         "date": "2025-01", "score": 9.4,  "provider": "DeepSeek"},
            {"model": "o3",                  "date": "2025-01", "score": 18.6, "provider": "OpenAI"},
            {"model": "Grok 3",              "date": "2025-02", "score": 14.0, "provider": "xAI"},
            {"model": "Gemini 2.5 Pro",      "date": "2025-03", "score": 18.8, "provider": "Google"},
            {"model": "Claude 4 Opus",       "date": "2025-05", "score": 14.0, "provider": "Anthropic"},
            {"model": "DeepSeek R1-0528",    "date": "2025-05", "score": 17.7, "provider": "DeepSeek"},
            {"model": "Grok 4",              "date": "2025-07", "score": 24.0, "provider": "xAI"},
            {"model": "Qwen3-235B Thinking", "date": "2025-07", "score": 18.2, "provider": "Alibaba"},
        ],
    },
    "SWE-Bench Verified": {
        "description": "Real-world GitHub issue resolution — end-to-end software engineering. Verified subset (500 tasks) is human-reviewed for tractability.",
        "why": "Most direct measure of frontier models' ability to do useful agentic coding work. Jumped from 1% to 70%+ in under 2 years — the single most dramatic capability gain.",
        "source": "Princeton NLP SWE-Bench (swebench.com) + Verified subset (OpenAI, 2024). Scores vary by scaffold.",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4",                  "date": "2023-03", "score": 1.7,  "provider": "OpenAI"},
            {"model": "Claude 3 Opus",          "date": "2024-03", "score": 4.7,  "provider": "Anthropic"},
            {"model": "Claude 3.5 Sonnet",      "date": "2024-06", "score": 49.0, "provider": "Anthropic"},
            {"model": "o1",                     "date": "2024-09", "score": 41.0, "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet (new)","date": "2024-10", "score": 53.6, "provider": "Anthropic"},
            {"model": "DeepSeek V3",            "date": "2024-12", "score": 42.0, "provider": "DeepSeek"},
            {"model": "Gemini 2.0 Flash",       "date": "2024-12", "score": 51.8, "provider": "Google"},
            {"model": "DeepSeek R1",            "date": "2025-01", "score": 49.2, "provider": "DeepSeek"},
            {"model": "o3",                     "date": "2025-01", "score": 71.7, "provider": "OpenAI"},
            {"model": "Grok 3",                 "date": "2025-02", "score": 63.8, "provider": "xAI"},
            {"model": "Gemini 2.5 Pro",         "date": "2025-03", "score": 63.8, "provider": "Google"},
            {"model": "Llama 4 Maverick",       "date": "2025-04", "score": 70.3, "provider": "Meta"},
            {"model": "Claude 4 Opus",          "date": "2025-05", "score": 72.5, "provider": "Anthropic"},
            {"model": "DeepSeek R1-0528",       "date": "2025-05", "score": 57.6, "provider": "DeepSeek"},
            {"model": "Grok 4",                 "date": "2025-07", "score": 72.0, "provider": "xAI"},
        ],
    },
}

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
    with st.expander("ℹ️ About this chart"):
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
_explainer(
    what="Qualitative capability progression of frontier AI systems, from few-shot learning (GPT-3, 2020) to autonomous reasoning agents (Claude 4, Grok 4). Each point marks a distinct capability milestone.",
    why="Benchmark scores plateau and reset; capability steps do not. This chart answers 'what can models *do* now that they couldn't 12 months ago?' — the question investors actually care about.",
    source="Hand-curated from provider release announcements. Complexity levels are qualitative, not a measured metric.",
)

# ─── Context Window Expansion ───
st.subheader("Context Window Expansion")

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
_explainer(
    what="Maximum prompt size each frontier model can process in a single call, plotted on a log scale. From 4K tokens (GPT-3) to 10M tokens (Llama 4 Maverick) — a ~2500x expansion in five years.",
    why="Context window is a hard constraint on what applications are possible. Long-context unlocks RAG-free codebases, whole-book summarisation, and multi-hour agent loops. The 'memory wall' has been the hardest architectural constraint to break.",
    source="Provider announcements and model cards. Context sizes are quoted maximums — effective context (where recall stays high) is often shorter.",
)


# ═════════════════════════════════════════════════════════════════════════
# SECTION 2 — Benchmark Performance
# ═════════════════════════════════════════════════════════════════════════
st.header("Benchmark Performance")
st.caption("Five benchmarks spanning general knowledge (MMLU, MMLU-Pro), reasoning (GPQA), frontier (HLE), and agentic coding (SWE-Bench).")

for bench_name, bench_data in BENCHMARKS.items():
    st.subheader(bench_name)
    st.caption(bench_data["description"])

    # Filter scores to selected providers
    visible_scores = [s for s in bench_data["scores"] if s["provider"] in sel_providers]
    visible_vals = [s["score"] for s in visible_scores]
    y_min, y_max = _compute_y_range(visible_vals, max_score=bench_data["max_score"])

    fig_bench = go.Figure()
    for trace in _provider_traces(
        bench_data["scores"], x_key="date", y_key="score",
        sel_providers=sel_providers,
        hover_fmt="%{text}: %{y:.1f}%",
    ):
        fig_bench.add_trace(trace)

    fig_bench.update_layout(
        yaxis_title="Score (%)",
        yaxis_range=[y_min, y_max],
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_bench, use_container_width=True)
    _explainer(
        what=bench_data["description"],
        why=bench_data["why"],
        source=bench_data["source"],
    )
    st.markdown("")  # spacer


# ═════════════════════════════════════════════════════════════════════════
# SECTION 3 — API Pricing Over Time
# ═════════════════════════════════════════════════════════════════════════
st.header("API Pricing")


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
    _explainer(
        what="API list price per million tokens for flagship frontier models at release, blended as (3×input + output)/4 to approximate a typical chat workload. Log scale.",
        why="Costs have fallen ~1000× since GPT-3 (2020). Epoch AI estimates 'price to match GPT-4 quality' has declined ~40× per year. This is the single most important variable in AI unit economics — it determines which applications are deployable and at what margin.",
        source="List prices from provider announcements & release blog posts. Open-weight models (Llama, Qwen) priced via major hosted providers (Together AI, DashScope). Snapshot at release — later price cuts not shown.",
    )


# ═════════════════════════════════════════════════════════════════════════
# SECTION 4 — Compute & Hardware
# ═════════════════════════════════════════════════════════════════════════
st.header("Compute & Hardware")

gpu_df = load_nvidia_dc_gpus()

if gpu_df.empty:
    st.warning(
        "NVIDIA hardware data missing. Expected at data/external/ml_hardware.csv "
        "(sourced from https://epoch.ai/data/ml_hardware.csv). Run `/ai-research` to refresh."
    )
else:
    # ─── 4a. NVIDIA GPU Performance Over Time ───
    st.subheader("NVIDIA Data-Centre GPU Performance")

    fig_gpu = go.Figure()
    for arch in ARCH_ORDER:
        sub = gpu_df[gpu_df["arch"] == arch]
        if sub.empty:
            continue
        hbm_txt = sub["hbm_gb"].map(lambda v: f"{v:.0f} GB HBM" if pd.notna(v) else "HBM —")
        bw_txt = sub["mem_bw_gb_s"].map(lambda v: f"{v:,.0f} GB/s" if pd.notna(v) else "bw —")
        price_txt = sub["price_usd"].map(lambda v: f"${v:,.0f}" if pd.notna(v) else "price —")
        custom = list(zip(sub["tdp_w"].fillna(0), hbm_txt, bw_txt, price_txt))
        fig_gpu.add_trace(go.Scatter(
            x=sub["release_date"],
            y=sub["tflops_tensor_fp16"],
            text=sub["name"],
            customdata=custom,
            name=arch,
            mode="markers",
            marker=dict(size=10, color=ARCH_COLOURS[arch], line=dict(width=1, color="#1f2937")),
            hovertemplate=(
                "%{text}<br>"
                "%{y:,.0f} TFLOPS (Tensor FP16/BF16)<br>"
                "TDP: %{customdata[0]:.0f} W<br>"
                "%{customdata[1]}<br>"
                "%{customdata[2]}<br>"
                "%{customdata[3]}"
                f"<extra>{arch}</extra>"
            ),
        ))

    fig_gpu.update_layout(
        yaxis_title="Tensor-FP16/BF16 Performance (TFLOPS)",
        yaxis_type="log",
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_gpu, use_container_width=True)
    _explainer(
        what="Peak dense Tensor-FP16/BF16 throughput for each NVIDIA data-centre GPU SKU, plotted against release date. Log scale. Coloured by architecture family (Volta → Ampere → Hopper → Blackwell). Each dot is one SKU — multiple dots per generation reflect PCIe/SXM/memory variants.",
        why="Training FLOPS per chip has grown ~20× in 8 years (125 TFLOPS V100 → 2500 TFLOPS GB300). Combined with cluster scaling, this is what enables each new frontier-model generation. The 'memory wall' narrative lives on the memory bandwidth column — inspect via hover.",
        source="Epoch AI — *Machine Learning Hardware* dataset (epoch.ai/data/machine-learning-hardware), CC-BY licence. Cached locally at data/external/ml_hardware.csv.",
    )

    # ─── 4b. Perf per Watt (flagship line) ───
    st.subheader("Performance per Watt — Flagship Line")

    flagships = flagship_per_generation(gpu_df)
    flagships = flagships[flagships["tdp_w"].notna()]
    flagships["perf_per_watt"] = flagships["tflops_tensor_fp16"] / flagships["tdp_w"]

    fig_ppw = go.Figure()
    fig_ppw.add_trace(go.Scatter(
        x=flagships["release_date"],
        y=flagships["perf_per_watt"],
        text=flagships["name"] + " (" + flagships["arch"] + ")",
        mode="lines+markers",
        line=dict(color="#10b981", width=2),
        marker=dict(size=10, color="#10b981"),
        hovertemplate="%{text}<br>%{y:.2f} TFLOPS/W<extra></extra>",
    ))

    y_min, y_max = _compute_y_range(flagships["perf_per_watt"].tolist(), max_score=10, floor=0.1)
    fig_ppw.update_layout(
        yaxis_title="Tensor FP16 TFLOPS per Watt",
        yaxis_range=[y_min, y_max],
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_ppw, use_container_width=True)
    _explainer(
        what="Tensor-FP16 TFLOPS divided by TDP (W) for the flagship SKU of each NVIDIA data-centre generation. One dot per architecture: V100 → A100 → H100 → Blackwell.",
        why="Power (not silicon) is the binding constraint on hyperscale training clusters. Data-centre deals are negotiated in MW, not $. Perf-per-watt is the 'Moore's law for AI' metric — it determines whether the next cluster can be built inside a given power envelope.",
        source="Derived from Epoch AI ML Hardware dataset. Flagship = highest-TFLOPS SKU per architecture family.",
    )

    # ─── 4c. H100 Rental Prices ───
    st.subheader("H100 Rental Prices")

    @st.cache_data(ttl=86400)
    def load_h100_prices() -> pd.DataFrame:
        csv = DATA_DIR / "h100_rental_prices.csv"
        if not csv.exists():
            return pd.DataFrame()
        df = pd.read_csv(csv)
        df["month"] = pd.to_datetime(df["month"])
        return df

    h100_df = load_h100_prices()
    if h100_df.empty:
        st.warning("H100 rental price CSV missing.")
    else:
        tier_colours = {
            "Hyperscaler": "#3b82f6",
            "Neocloud":    "#a855f7",
            "Marketplace": "#10b981",
        }

        fig_h100 = go.Figure()
        for tier in ["Hyperscaler", "Neocloud", "Marketplace"]:
            sub = h100_df[h100_df["tier"] == tier].sort_values("month")
            if sub.empty:
                continue
            fig_h100.add_trace(go.Scatter(
                x=sub["month"],
                y=sub["price_usd_per_gpu_hr"],
                name=tier,
                mode="lines+markers",
                line=dict(color=tier_colours[tier], width=2),
                marker=dict(size=6, color=tier_colours[tier]),
                hovertemplate=f"{tier}<br>%{{x|%b %Y}}: $%{{y:.2f}}/GPU-hr<extra></extra>",
            ))

        y_min, y_max = _compute_y_range(
            h100_df["price_usd_per_gpu_hr"].tolist(), max_score=12, floor=0.5
        )
        fig_h100.update_layout(
            yaxis_title="$ per GPU-hour",
            yaxis_range=[y_min, y_max],
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_h100, use_container_width=True)
        _explainer(
            what="Monthly median H100 rental price in $/GPU-hour, broken out by provider tier. Hyperscaler = AWS/Azure/GCP list prices. Neocloud = CoreWeave, Lambda, Crusoe, etc. Marketplace = GPU marketplaces monetising underutilised reserved capacity (Vast.ai, SF Compute, etc.).",
            why="H100 lease rates are the cleanest public proxy for GPU depreciation and chip obsolescence. The gap between tiers (hyperscaler ~3× marketplace) reveals how much of cloud AI gross margin is 'convenience tax' vs. compute cost. Sharp 2025 declines are the story: Blackwell supply came online, H100 residual value fell ~30% in 90 days.",
            source="Silicon Data — *H100 Rental Index* public blog (silicondata.com/blog/h100-rental-price-over-time). Manually transcribed, refreshed quarterly. Paid API with daily data available via Bloomberg (ticker SDH100RT).",
        )


# ═════════════════════════════════════════════════════════════════════════
# FOOTER — attribution
# ═════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption(
    "Data sources: Epoch AI (ML Hardware dataset, CC-BY) · Silicon Data (H100 Rental Index blog) · "
    "provider model cards & release announcements. Benchmark scores are vendor-reported unless otherwise noted."
)
