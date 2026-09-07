"""Shared data, constants, and helpers for LLM Performance pages.

Data chain (Astra S2-12 / C14): the committed snapshots under
``data/reference/`` are the default source of truth — a full-field model
snapshot (``llm_leaderboard.json``) plus separately-identified TrueSkill index
data (``llm_indexes.json``), both validated by ``app/lib/llm_snapshot.py``.
Pages read the committed snapshot with a visible as-of; a sidebar toggle
(``llm_use_live``, set in Home.py) opts into a live ZeroEval fetch, which falls
back to the snapshot on any failure. A reader never fabricates a rank offline:
index columns only ever come from the published index artifact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from app.lib import llm_snapshot

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "reference"

# session_state keys used by the reader layer
_LLM_LIVE_KEY = "llm_use_live"
_PROV_KEY = "_llm_data_provenance"

_PROV_DEFAULT = {"mode": "snapshot", "asof": None, "note": ""}

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

ATTR = "Data: [LLM Stats](https://llm-stats.com) · [api.zeroeval.com](https://api.zeroeval.com)"

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
    {"model": "Llama 4 Scout",    "date": "2025-04", "tokens": 10000000, "provider": "Meta"},
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


def _zeroeval_api_key() -> str | None:
    """Return the ZeroEval API key from Streamlit secrets or macOS Keychain."""
    # Streamlit Cloud: add ZEROEVAL_API_KEY to app secrets
    # Only access st.secrets if a secrets.toml file exists on disk,
    # otherwise Streamlit shows a persistent warning banner.
    _secrets_candidates = [
        Path.home() / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml",
    ]
    if any(p.is_file() for p in _secrets_candidates):
        try:
            key = st.secrets.get("ZEROEVAL_API_KEY") or st.secrets.get("zeroeval_api_key")
            if key:
                return key
        except Exception:
            pass
    # Local: macOS Keychain
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "llm-stats-api", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


# ────────────────────────────────────────────────────────────────────────────
# Reader layer — committed snapshot by default, optional live override
# (S2-12: readers default to validated snapshots; never fabricate ranks offline)
# ────────────────────────────────────────────────────────────────────────────
def _live_wanted() -> bool:
    """True when the Home.py sidebar 'use live ZeroEval data' toggle is on."""
    try:
        return bool(st.session_state.get(_LLM_LIVE_KEY, False))
    except Exception:
        return False


def _set_provenance(prov: dict) -> None:
    try:
        st.session_state[_PROV_KEY] = prov
    except Exception:
        pass


def _fetch_live_models_uncached() -> pd.DataFrame:
    """Hit the live ZeroEval models endpoint. Raises on any failure."""
    api_key = _zeroeval_api_key()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = requests.get(
        llm_snapshot.MODELS_SOURCE_URL,
        params={"justCanonicals": "true"},
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise ValueError("unexpected response shape (expected a non-empty list)")
    return pd.DataFrame(data)


def _fetch_live_indexes_uncached() -> dict[str, pd.DataFrame]:
    """Hit the live ZeroEval indexes endpoint; contract-validate before use."""
    api_key = _zeroeval_api_key()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = requests.get(llm_snapshot.INDEXES_SOURCE_URL, headers=headers, timeout=20)
    resp.raise_for_status()
    payload = llm_snapshot.build_indexes_payload(resp.json())
    errors = llm_snapshot.validate_indexes_payload(payload)
    if errors:
        raise ValueError(f"live index response failed the shared contract ({len(errors)} issue(s))")
    return llm_snapshot.indexes_to_frames(payload["indexes"])


@st.cache_data(ttl=1800, show_spinner=False)
def _live_models_cached() -> pd.DataFrame:
    return _fetch_live_models_uncached()


@st.cache_data(ttl=1800, show_spinner=False)
def _live_indexes_cached() -> dict[str, pd.DataFrame]:
    return _fetch_live_indexes_uncached()


@st.cache_data(ttl=300, show_spinner=False)
def _committed_models_payload() -> dict:
    """Validated committed models snapshot.

    Raises FileNotFoundError when absent and ContractError when malformed —
    the caller decides how to surface it, never a silent empty frame.
    """
    return llm_snapshot.load_models_payload(llm_snapshot.models_path(_DATA_DIR))


@st.cache_data(ttl=300, show_spinner=False)
def _committed_indexes_payload() -> dict:
    return llm_snapshot.load_indexes_payload(llm_snapshot.indexes_path(_DATA_DIR))


def fetch_zeroeval_models() -> pd.DataFrame:
    """Model frame for the LLM pages.

    Defaults to the validated committed full-field snapshot with a visible
    as-of. Live ZeroEval data is fetched only when the sidebar toggle is on,
    and any live failure falls back to the snapshot with a provenance note.
    An empty frame is returned ONLY when no committed snapshot exists AND live
    data is unavailable — callers then show the no-data state.
    """
    if _live_wanted():
        try:
            df = _live_models_cached()
            if df is not None and not df.empty:
                _set_provenance({
                    "mode": "live",
                    "asof": None,
                    "note": f"live api.zeroeval.com fetch, "
                            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
                })
                return df
        except Exception as exc:  # live failure -> snapshot fallback
            _set_provenance({
                "mode": "snapshot", "asof": None,
                "note": f"live fetch failed ({exc.__class__.__name__}) — showing committed snapshot",
            })
    try:
        payload = _committed_models_payload()
    except FileNotFoundError:
        _set_provenance({
            "mode": "none", "asof": None,
            "note": "no committed snapshot (data/reference/llm_leaderboard.json) and live data unavailable",
        })
        return pd.DataFrame()
    except llm_snapshot.ContractError as exc:
        _set_provenance({
            "mode": "none", "asof": None,
            "note": f"committed snapshot failed validation: {exc}",
        })
        return pd.DataFrame()
    _set_provenance({"mode": "snapshot", "asof": payload["_meta"].get("updated"), "note": ""})
    return pd.DataFrame(payload["models"])


def fetch_zeroeval_indexes() -> dict[str, pd.DataFrame]:
    """TrueSkill index frames keyed by category (e.g. 'reasoning', 'code').

    Defaults to the committed llm_indexes.json artifact. Missing/unavailable
    index data yields {} — categories simply render unavailable; ranks are
    never fabricated. Live override follows the same sidebar toggle and also
    falls back to the committed artifact on failure.
    """
    if _live_wanted():
        try:
            frames = _live_indexes_cached()
            if frames:
                return frames
        except Exception:
            pass  # fall through to committed artifact
    try:
        payload = _committed_indexes_payload()
    except (FileNotFoundError, llm_snapshot.ContractError):
        return {}
    return llm_snapshot.indexes_to_frames(payload["indexes"])


def order_leaderboard(
    models_df: pd.DataFrame,
    index_frames: dict[str, pd.DataFrame],
    index_cols: list[str],
    primary: str = "reasoning",
) -> tuple[pd.DataFrame, str, list[str]]:
    """Order the leaderboard model frame for display (shared snapshot helper).

    Returns ``(ordered_df, sort_key, missing_categories)`` where ``sort_key`` is
    ``'reasoning_index'`` (published ZeroEval TrueSkill reasoning index) or
    ``'benchmark_mean'`` (labelled reader-side mean of headline benchmarks when
    the reasoning index is unavailable) — the caller renders that label
    honestly, so a missing index can never masquerade as a TrueSkill ranking.
    """
    return llm_snapshot.leaderboard_order(models_df, index_frames, index_cols, primary)


def llm_data_status() -> str:
    """One-line visible as-of / mode caption for LLM pages (markdown text).

    Records which data the page is actually showing and when it was captured,
    so committed evidence is never mistaken for a live read.
    """
    try:
        prov = dict(st.session_state.get(_PROV_KEY, _PROV_DEFAULT))
    except Exception:
        prov = dict(_PROV_DEFAULT)
    mode = prov.get("mode", "snapshot")
    note = prov.get("note") or ""
    if mode == "live":
        return f"Data: live from api.zeroeval.com — {note}"
    if mode == "none":
        return "Data: unavailable — " + note
    asof = prov.get("asof") or "unknown"
    text = f"Data: committed ZeroEval snapshot · as-of {asof}"
    if note:
        text += f" · {note}"
    return text


def llm_no_data_message() -> str:
    """Message for pages whose model frame is empty (no snapshot, live down)."""
    try:
        note = (st.session_state.get(_PROV_KEY, {}) or {}).get("note")
    except Exception:
        note = None
    if not note:
        note = "committed snapshot missing and live fetch unavailable"
    return (
        "No LLM benchmark data available — " + note
        + ". Restore data/reference/llm_leaderboard.json (or run "
        + "scripts/refresh_llm_leaderboard.py) or enable live data in the sidebar."
    )


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
