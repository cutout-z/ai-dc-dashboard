"""Shared data, constants, and helpers for LLM Performance pages."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "reference"

PROVIDER_COLOURS: dict[str, str] = {
    "OpenAI":    "#10b981",
    "Anthropic": "#f59e0b",
    "Google":    "#3b82f6",
    "Meta":      "#8b5cf6",
    "xAI":       "#9ca3af",
    "DeepSeek":  "#ec4899",
    "Alibaba":   "#ef4444",
    "Mistral":   "#06b6d4",
}

ORG_TO_PROVIDER: dict[str, str] = {
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

BENCH_COLS: list[str] = ["gpqa_score", "swe_bench_verified_score", "hle_score", "aime_2025_score"]
_BENCH_COLS_FULL: list[str] = [
    "gpqa_score", "swe_bench_verified_score", "hle_score", "aime_2025_score", "mmmlu_score"
]

BENCH_MAP: dict[str, str] = {
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

ATTR = (
    "Data: [llm-stats.com/ai-trends](https://llm-stats.com/ai-trends) · "
    "[api.zeroeval.com](https://api.zeroeval.com)"
)

CONTEXT_WINDOWS: list[dict] = [
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

CAPABILITY_MILESTONES: list[dict] = [
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


@st.cache_data(ttl=3600)
def fetch_zeroeval_models() -> pd.DataFrame:
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


@st.cache_data(ttl=86400)
def load_token_prices() -> pd.DataFrame:
    csv = _DATA_DIR / "token_prices_history.csv"
    if not csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv)
    df["date"] = pd.to_datetime(df["date"])
    df["blended_usd_per_mtok"] = (3 * df["input_usd_per_mtok"] + df["output_usd_per_mtok"]) / 4
    return df


def load_arena_elo() -> pd.DataFrame:
    db_path = st.session_state.get("db_path", "")
    if not db_path:
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM llm_arena_elo ORDER BY elo DESC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def preprocess_ze(ze_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (df, df_specs). df has derived columns; df_specs has renamed columns for scatter plots."""
    if ze_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    import numpy as np  # noqa: F401

    df = ze_df.copy()
    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df = df.dropna(subset=["release_date"]).sort_values("release_date")
    df["quarter"] = df["release_date"].dt.to_period("Q").dt.start_time
    df["year"] = df["release_date"].dt.year.astype(int)
    df["month"] = df["release_date"].dt.month.astype(int)
    df["provider"] = df["organization"].map(ORG_TO_PROVIDER).fillna(df["organization"])
    df["is_open"] = df["license"].apply(lambda x: "Open Source" if x != "proprietary" else "Proprietary")
    df["country"] = df["organization_country"].fillna("Unknown")
    df["blended_price"] = (
        (3 * df["input_price"].fillna(0) + df["output_price"].fillna(0)) / 4
    ).replace(0, float("nan"))

    df_specs = ze_df.copy()
    df_specs["provider"] = df_specs["organization"].map(ORG_TO_PROVIDER).fillna(df_specs["organization"])
    df_specs["model"] = df_specs["name"]
    df_specs["input_price_per_m_tokens"] = df_specs["input_price"]
    df_specs["context_window"] = df_specs["context"]
    df_specs["intelligence_score"] = df_specs[_BENCH_COLS_FULL].mean(axis=1, skipna=True).mul(100)

    return df, df_specs


def chart_layout() -> dict:
    return dict(
        template=st.session_state.get("plotly_template", "plotly_dark"),
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        margin=dict(l=40, r=20, t=40, b=80),
        hoverlabel=dict(bgcolor=st.session_state.get("hoverlabel_bg", "#333"), font_size=12),
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
    )


def explainer(what: str, why: str, source: str) -> None:
    st.markdown(
        f"<small style='color:#888'>**What it shows.** {what} &nbsp;|&nbsp; "
        f"**Why it matters.** {why} &nbsp;|&nbsp; "
        f"**Source.** {source}</small>",
        unsafe_allow_html=True,
    )


def provider_traces(
    records: list[dict],
    x_key: str,
    y_key: str,
    sel_providers: list[str],
    text_key: str = "model",
    hover_fmt: str = "%{text}: %{y:.1f}",
) -> list[go.Scatter]:
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


def sota_prog(df: pd.DataFrame, score_col: str, group_col: str | None = None) -> pd.DataFrame:
    if group_col:
        rows: list[dict] = []
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
        sota, rows_list = -1.0, []
        for _, r in valid.iterrows():
            if r[score_col] > sota:
                sota = r[score_col]
                rows_list.append({"date": r["release_date"], "score": sota * 100, "model": r["name"]})
        return pd.DataFrame(rows_list)


def pareto_front(df: pd.DataFrame, x_col: str, y_col: str) -> pd.DataFrame:
    d = df.dropna(subset=[x_col, y_col]).sort_values(x_col)
    best_y, rows_list = -1e9, []
    for _, r in d.iterrows():
        if r[y_col] > best_y:
            best_y = r[y_col]
            rows_list.append(r)
    return pd.DataFrame(rows_list)


def provider_sidebar() -> list[str]:
    st.sidebar.header("Filters")
    all_providers = list(PROVIDER_COLOURS.keys())
    return st.sidebar.multiselect("Providers", all_providers, default=all_providers)
