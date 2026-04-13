"""LLM Performance Analysis — AI model benchmarks, context windows, pricing, and live leaderboard."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


CHART_LAYOUT = dict(
    font=dict(family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12),
)

st.title("LLM Performance Analysis")
st.caption("Frontier AI model benchmarks, context windows, API pricing, and live leaderboard.")

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"
DB_PATH = st.session_state["db_path"]

# ═════════════════════════════════════════════════════════════════════════
# LLM LEADERBOARD — top 30 models from llm-stats.com
# ═════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400)
def _load_leaderboard() -> pd.DataFrame:
    path = DATA_DIR / "llm_leaderboard.json"
    if not path.exists():
        return pd.DataFrame()
    with open(path) as f:
        data = json.load(f)
    return pd.DataFrame(data["models"])


_lb_df = _load_leaderboard()

if not _lb_df.empty:
    st.header("LLM Leaderboard")
    st.caption("Top 30 frontier models ranked by composite score — sourced from [llm-stats.com](https://llm-stats.com/leaderboards/llm-leaderboard).")

    # Build display table
    _display = _lb_df.rename(columns={
        "rank": "#",
        "name": "Model",
        "org": "Org",
        "gpqa": "GPQA",
        "aime_2025": "AIME '25",
        "swe_bench": "SWE-Bench",
        "hle": "HLE",
        "input_price": "In $/M",
        "output_price": "Out $/M",
        "context_k": "Ctx (K)",
        "speed_cps": "Speed",
    })
    _display = _display[["#", "Model", "Org", "GPQA", "AIME '25", "SWE-Bench", "HLE",
                          "In $/M", "Out $/M", "Ctx (K)", "Speed"]]

    st.dataframe(
        _display,
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Model": st.column_config.TextColumn(width="medium"),
            "Org": st.column_config.TextColumn(width="small"),
            "GPQA": st.column_config.NumberColumn(format="%.1f%%"),
            "AIME '25": st.column_config.NumberColumn(format="%.1f%%"),
            "SWE-Bench": st.column_config.NumberColumn(format="%.1f%%"),
            "HLE": st.column_config.NumberColumn(format="%.1f%%"),
            "In $/M": st.column_config.NumberColumn(format="$%.2f"),
            "Out $/M": st.column_config.NumberColumn(format="$%.2f"),
            "Ctx (K)": st.column_config.NumberColumn(format="%d"),
            "Speed": st.column_config.NumberColumn(format="%d c/s"),
        },
    )
    with open(DATA_DIR / "llm_leaderboard.json") as _f:
        _lb_meta = json.load(_f)["_meta"]
    st.caption(f"Last updated: {_lb_meta['updated']}. "
               "Scores as percentages. Speed in characters/second. Awaiting LLM Stats API for live updates.")
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
            {"model": "Gemini 3 Pro",        "date": "2025-11", "score": 81.0, "provider": "Google"},
            {"model": "GPT-5.2",             "date": "2025-12", "score": 79.5, "provider": "OpenAI"},
            {"model": "Gemini 3 Flash",      "date": "2025-12", "score": 81.2, "provider": "Google"},
            {"model": "Gemini 3.1 Pro",      "date": "2026-02", "score": 80.5, "provider": "Google"},
            {"model": "GPT-5.4",             "date": "2026-03", "score": 81.2, "provider": "OpenAI"},
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
            {"model": "Claude Sonnet 4.5",   "date": "2025-09", "score": 83.4, "provider": "Anthropic"},
            {"model": "Claude Opus 4.1",     "date": "2025-10", "score": 80.9, "provider": "Anthropic"},
            {"model": "Gemini 3 Pro",        "date": "2025-11", "score": 91.9, "provider": "Google"},
            {"model": "GPT-5.2",             "date": "2025-12", "score": 92.4, "provider": "OpenAI"},
            {"model": "Gemini 3 Flash",      "date": "2025-12", "score": 90.4, "provider": "Google"},
            {"model": "Claude Opus 4.6",     "date": "2026-02", "score": 91.3, "provider": "Anthropic"},
            {"model": "Claude Sonnet 4.6",   "date": "2026-02", "score": 89.9, "provider": "Anthropic"},
            {"model": "Gemini 3.1 Pro",      "date": "2026-02", "score": 94.3, "provider": "Google"},
            {"model": "GPT-5.4",             "date": "2026-03", "score": 92.8, "provider": "OpenAI"},
        ],
    },
    "Humanity's Last Exam": {
        "description": "Extremely hard questions from domain experts — ceiling test for frontier models. Current SOTA ~53%.",
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
            {"model": "Gemini 3 Pro",        "date": "2025-11", "score": 45.8, "provider": "Google"},
            {"model": "GPT-5.2",             "date": "2025-12", "score": 34.5, "provider": "OpenAI"},
            {"model": "Gemini 3 Flash",      "date": "2025-12", "score": 43.5, "provider": "Google"},
            {"model": "Claude Opus 4.6",     "date": "2026-02", "score": 53.1, "provider": "Anthropic"},
            {"model": "Claude Sonnet 4.6",   "date": "2026-02", "score": 49.0, "provider": "Anthropic"},
            {"model": "Gemini 3.1 Pro",      "date": "2026-02", "score": 51.4, "provider": "Google"},
            {"model": "GPT-5.4",             "date": "2026-03", "score": 39.8, "provider": "OpenAI"},
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
            {"model": "Claude Opus 4.1",        "date": "2025-10", "score": 74.5, "provider": "Anthropic"},
            {"model": "Gemini 3 Pro",            "date": "2025-11", "score": 76.2, "provider": "Google"},
            {"model": "GPT-5.2",                 "date": "2025-12", "score": 80.0, "provider": "OpenAI"},
            {"model": "Gemini 3 Flash",          "date": "2025-12", "score": 78.0, "provider": "Google"},
            {"model": "Claude Opus 4.6",         "date": "2026-02", "score": 80.8, "provider": "Anthropic"},
            {"model": "Claude Sonnet 4.6",       "date": "2026-02", "score": 79.6, "provider": "Anthropic"},
            {"model": "Gemini 3.1 Pro",          "date": "2026-02", "score": 80.6, "provider": "Google"},
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


# ═════════════════════════════════════════════════════════════════════════
# SECTION 2 — Benchmark Performance
# ═════════════════════════════════════════════════════════════════════════
st.header("Benchmark Performance")
st.caption("Five benchmarks spanning general knowledge (MMLU, MMLU-Pro), reasoning (GPQA), frontier (HLE), and agentic coding (SWE-Bench).")

for bench_name, bench_data in BENCHMARKS.items():
    st.subheader(bench_name)
    st.caption(bench_data["description"])
    _explainer(
        what=bench_data["description"],
        why=bench_data["why"],
        source=bench_data["source"],
    )

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
st.caption("Arena Elo ratings, intelligence-vs-cost frontier, and context window leaders — updated via /ai-research skill.")

_conn = sqlite3.connect(DB_PATH)
df_elo = pd.read_sql("SELECT * FROM llm_arena_elo ORDER BY elo DESC", _conn)
df_specs = pd.read_sql("SELECT * FROM llm_model_specs ORDER BY intelligence_score DESC NULLS LAST", _conn)
_conn.close()

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
    source="Artificial Analysis intelligence index + provider list pricing. Updated via /ai-research skill.",
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
            source="Model cards and provider announcements. Updated via /ai-research skill.",
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
