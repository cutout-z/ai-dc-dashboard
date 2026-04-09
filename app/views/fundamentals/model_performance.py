"""Model Performance — AI model benchmarks, context windows, and capability milestones."""

import streamlit as st
import plotly.graph_objects as go

CHART_LAYOUT = dict(
    font=dict(family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12),
)

st.title("Model Performance")
st.caption("Frontier AI model benchmarks, context windows, and capability milestones.")

# ─── Provider colours (consistent across all charts) ───
PROVIDER_COLOURS = {
    "OpenAI": "#10b981",
    "Anthropic": "#f59e0b",
    "Google": "#3b82f6",
}

# ─── Context Window Expansion ───
CONTEXT_WINDOWS = [
    {"model": "GPT-3",           "date": "2020-06", "tokens": 4096,     "provider": "OpenAI"},
    {"model": "GPT-3.5",         "date": "2022-11", "tokens": 4096,     "provider": "OpenAI"},
    {"model": "Claude 1",        "date": "2023-03", "tokens": 9000,     "provider": "Anthropic"},
    {"model": "GPT-4",           "date": "2023-03", "tokens": 8192,     "provider": "OpenAI"},
    {"model": "GPT-4 32K",       "date": "2023-03", "tokens": 32768,    "provider": "OpenAI"},
    {"model": "Claude 2",        "date": "2023-07", "tokens": 100000,   "provider": "Anthropic"},
    {"model": "GPT-4 Turbo",     "date": "2023-11", "tokens": 128000,   "provider": "OpenAI"},
    {"model": "Gemini 1.5 Pro",  "date": "2024-02", "tokens": 1000000,  "provider": "Google"},
    {"model": "Claude 3",        "date": "2024-03", "tokens": 200000,   "provider": "Anthropic"},
    {"model": "GPT-4o",          "date": "2024-05", "tokens": 128000,   "provider": "OpenAI"},
    {"model": "Claude 3.5",      "date": "2024-06", "tokens": 200000,   "provider": "Anthropic"},
    {"model": "Gemini 2.0",      "date": "2024-12", "tokens": 1000000,  "provider": "Google"},
    {"model": "Claude Opus 4",   "date": "2025-05", "tokens": 1000000,  "provider": "Anthropic"},
]

# ─── Benchmark Performance ───
BENCHMARKS = {
    "MMLU": {
        "description": "Massive Multitask Language Understanding — 57 subjects, knowledge breadth",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4",           "date": "2023-03", "score": 86.4,  "provider": "OpenAI"},
            {"model": "Claude 2",        "date": "2023-07", "score": 78.5,  "provider": "Anthropic"},
            {"model": "Gemini Ultra",     "date": "2023-12", "score": 90.0,  "provider": "Google"},
            {"model": "Claude 3 Opus",   "date": "2024-03", "score": 86.8,  "provider": "Anthropic"},
            {"model": "GPT-4o",          "date": "2024-05", "score": 88.7,  "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet","date": "2024-06", "score": 88.7,  "provider": "Anthropic"},
            {"model": "Gemini 1.5 Pro",  "date": "2024-08", "score": 85.9,  "provider": "Google"},
            {"model": "o1",              "date": "2024-09", "score": 92.3,  "provider": "OpenAI"},
            {"model": "Claude 4 Opus",   "date": "2025-05", "score": 93.0,  "provider": "Anthropic"},
        ],
    },
    "MMLU-Pro": {
        "description": "Harder, more discriminating MMLU variant — 10-option MCQ, expert-level",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4o",          "date": "2024-05", "score": 72.6,  "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet","date": "2024-06", "score": 78.0,  "provider": "Anthropic"},
            {"model": "Gemini 1.5 Pro",  "date": "2024-08", "score": 69.1,  "provider": "Google"},
            {"model": "o1",              "date": "2024-09", "score": 80.3,  "provider": "OpenAI"},
            {"model": "Claude 4 Opus",   "date": "2025-05", "score": 84.0,  "provider": "Anthropic"},
        ],
    },
    "GPQA Diamond": {
        "description": "Graduate-level science QA — physics, chemistry, biology expert questions",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4",           "date": "2023-03", "score": 39.7,  "provider": "OpenAI"},
            {"model": "Claude 3 Opus",   "date": "2024-03", "score": 60.4,  "provider": "Anthropic"},
            {"model": "GPT-4o",          "date": "2024-05", "score": 53.6,  "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet","date": "2024-06", "score": 65.0,  "provider": "Anthropic"},
            {"model": "o1",              "date": "2024-09", "score": 78.0,  "provider": "OpenAI"},
            {"model": "Claude 4 Opus",   "date": "2025-05", "score": 75.0,  "provider": "Anthropic"},
        ],
    },
    "Humanity's Last Exam": {
        "description": "Extremely hard questions from domain experts — ceiling test for frontier models",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4o",          "date": "2024-05", "score": 3.3,   "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet","date": "2024-06", "score": 4.3,   "provider": "Anthropic"},
            {"model": "o1",              "date": "2024-09", "score": 9.1,   "provider": "OpenAI"},
            {"model": "o3",              "date": "2025-01", "score": 18.6,  "provider": "OpenAI"},
            {"model": "Gemini 2.5 Pro",  "date": "2025-03", "score": 18.8,  "provider": "Google"},
            {"model": "Claude 4 Opus",   "date": "2025-05", "score": 14.0,  "provider": "Anthropic"},
        ],
    },
    "SWE-Bench Verified": {
        "description": "Real-world GitHub issue resolution — end-to-end software engineering",
        "max_score": 100,
        "scores": [
            {"model": "GPT-4",           "date": "2023-03", "score": 1.7,   "provider": "OpenAI"},
            {"model": "Claude 3 Opus",   "date": "2024-03", "score": 4.7,   "provider": "Anthropic"},
            {"model": "Claude 3.5 Sonnet","date": "2024-06", "score": 49.0,  "provider": "Anthropic"},
            {"model": "o1",              "date": "2024-09", "score": 41.0,  "provider": "OpenAI"},
            {"model": "Claude 3.5 Sonnet (new)","date": "2024-10", "score": 53.6, "provider": "Anthropic"},
            {"model": "o3",              "date": "2025-01", "score": 71.7,  "provider": "OpenAI"},
            {"model": "Claude 4 Opus",   "date": "2025-05", "score": 72.5,  "provider": "Anthropic"},
        ],
    },
}

# ─── Task Complexity / Capability Milestones ───
CAPABILITY_MILESTONES = [
    {"date": "2020-06", "event": "GPT-3: few-shot learning",           "complexity": 1},
    {"date": "2022-11", "event": "ChatGPT: conversational AI",         "complexity": 2},
    {"date": "2023-03", "event": "GPT-4: multimodal, reasoning",       "complexity": 3},
    {"date": "2023-07", "event": "Claude 2: 100K context",             "complexity": 3.5},
    {"date": "2023-11", "event": "GPT-4 Turbo: 128K, function calling","complexity": 4},
    {"date": "2024-02", "event": "Gemini 1.5: 1M context",            "complexity": 4.5},
    {"date": "2024-03", "event": "Claude 3: tool use, vision",        "complexity": 5},
    {"date": "2024-06", "event": "Claude 3.5: artifacts, coding",      "complexity": 6},
    {"date": "2024-09", "event": "o1: chain-of-thought reasoning",     "complexity": 7},
    {"date": "2024-10", "event": "Claude computer use",                "complexity": 7.5},
    {"date": "2025-01", "event": "o3: advanced reasoning, ARC-AGI",    "complexity": 8},
    {"date": "2025-02", "event": "Claude Code: autonomous coding",     "complexity": 8.5},
    {"date": "2025-05", "event": "Claude 4: extended thinking, agents","complexity": 9},
]


# =========================================================================
# Sidebar — provider filter
# =========================================================================
st.sidebar.header("Filters")
all_providers = sorted(PROVIDER_COLOURS.keys())
sel_providers = st.sidebar.multiselect("Providers", all_providers, default=all_providers)


# =========================================================================
# Helper — build provider-grouped traces for scatter charts
# =========================================================================
def _provider_traces(records: list[dict], x_key: str, y_key: str,
                     text_key: str = "model", log_y: bool = False,
                     hover_fmt: str = "%{text}: %{y:.1f}") -> list[go.Scatter]:
    providers: dict[str, dict] = {}
    for r in records:
        p = r["provider"]
        if p not in sel_providers:
            continue
        if p not in providers:
            providers[p] = {"x": [], "y": [], "text": []}
        providers[p]["x"].append(r[x_key])
        providers[p]["y"].append(r[y_key])
        providers[p]["text"].append(r[text_key])

    traces = []
    for p, d in providers.items():
        traces.append(go.Scatter(
            x=d["x"], y=d["y"], text=d["text"],
            name=p, mode="markers+lines",
            line=dict(color=PROVIDER_COLOURS.get(p, "#6b7280"), width=1.5),
            marker=dict(size=7, color=PROVIDER_COLOURS.get(p, "#6b7280")),
            hovertemplate=hover_fmt + f"<extra>{p}</extra>",
        ))
    return traces


# =========================================================================
# 1 — Task Complexity Over Time
# =========================================================================
st.subheader("Task Complexity Over Time")

filtered_milestones = [m for m in CAPABILITY_MILESTONES]  # no provider filter for milestones
fig_complexity = go.Figure()
fig_complexity.add_trace(go.Scatter(
    x=[m["date"] for m in filtered_milestones],
    y=[m["complexity"] for m in filtered_milestones],
    text=[m["event"] for m in filtered_milestones],
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
st.caption("Qualitative capability progression — from few-shot learning to autonomous agents.")


# =========================================================================
# 2 — Context Window Expansion
# =========================================================================
st.subheader("Context Window Expansion")

fig_ctx = go.Figure()
for trace in _provider_traces(
    CONTEXT_WINDOWS, x_key="date", y_key="tokens",
    hover_fmt="%{text}<br>%{y:,.0f} tokens",
):
    trace.marker.size = 8
    fig_ctx.add_trace(trace)

fig_ctx.update_layout(
    yaxis_title="Context Window (tokens)",
    yaxis_type="log",
    **CHART_LAYOUT,
)
st.plotly_chart(fig_ctx, use_container_width=True)
st.caption("Log scale. From 4K tokens (GPT-3) to 1M tokens (Gemini 1.5 / Claude Opus 4).")


# =========================================================================
# 3 — Benchmark Performance
# =========================================================================
st.subheader("Benchmark Performance")

for bench_name, bench_data in BENCHMARKS.items():
    with st.container():
        st.markdown(f"**{bench_name}**")
        st.caption(bench_data["description"])

        fig_bench = go.Figure()
        for trace in _provider_traces(
            bench_data["scores"], x_key="date", y_key="score",
            hover_fmt="%{text}: %{y:.1f}%",
        ):
            fig_bench.add_trace(trace)

        fig_bench.update_layout(
            yaxis_title="Score (%)",
            yaxis_range=[0, bench_data["max_score"]],
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig_bench, use_container_width=True)
