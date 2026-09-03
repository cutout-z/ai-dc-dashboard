"""Shared data loading for the OpenRouter token-traffic page.

Reads the machine-generated dataset written by
``scripts/refresh_openrouter_usage.py``:

    data/external/openrouter_rankings_daily.csv
    data/external/openrouter_rankings_daily_meta.json

Dataset semantics (OpenRouter Datasets API — ``/api/v1/datasets/rankings-daily``):
per UTC day, the top 50 public models by total tokens (prompt + completion,
native tokenizer) plus one ``other`` row aggregating the long tail. Rows are
therefore platform-wide aggregate traffic routed through OpenRouter only —
NOT whole-market usage, NOT spend.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "external"
CSV_PATH = _DATA_DIR / "openrouter_rankings_daily.csv"
META_PATH = _DATA_DIR / "openrouter_rankings_daily_meta.json"

# Canonical display provider per OpenRouter org slug. Keys intentionally keep
# the llm_perf.PROVIDER_COLOURS set for the majors and add the orgs that show
# up on OpenRouter's own rankings (Z.ai, Tencent, NVIDIA, ...).
ORG_PROVIDER: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "google-deepmind": "Google",
    "google-paligemma": "Google",
    "meta": "Meta",
    "x-ai": "xAI",
    "deepseek": "DeepSeek",
    "qwen": "Alibaba",
    "mistralai": "Mistral",
    "z-ai": "Z.ai",
    "tencent": "Tencent",
    "xiaomi": "Xiaomi",
    "nvidia": "NVIDIA",
    "minimax": "MiniMax",
    "moonshotai": "Moonshot",
    "other": "Other (long tail)",
}

# Extra colours for orgs outside llm_perf.PROVIDER_COLOURS. Kept local so this
# module stays streamlit-free and trivially importable for tests.
EXTRA_PROVIDER_COLOURS: dict[str, str] = {
    "Z.ai": "#eab308",
    "Tencent": "#22c55e",
    "Xiaomi": "#f97316",
    "NVIDIA": "#76b900",
    "MiniMax": "#a855f7",
    "Moonshot": "#14b8a6",
    "Other (long tail)": "#6b7280",
}

# Stable fallback palette for any unrecognised org slug.
_FALLBACK_PALETTE = [
    "#0ea5e9", "#f43f5e", "#84cc16", "#6366f1", "#d946ef",
    "#fbbf24", "#10b981", "#3b82f6", "#ec4899", "#94a3b8",
]

PROVIDER_ORDER = [
    "OpenAI", "Anthropic", "Google", "DeepSeek", "Z.ai", "Meta", "xAI",
    "Alibaba", "Tencent", "Xiaomi", "NVIDIA", "Mistral", "MiniMax",
    "Moonshot", "Other (long tail)",
]


def org_to_provider(org_slug: str) -> str:
    """Map an OpenRouter org slug (model_permaslug first path segment) to a
    display provider. Unknown slugs pass through title-cased."""
    if org_slug in ORG_PROVIDER:
        return ORG_PROVIDER[org_slug]
    if not org_slug or org_slug == "other":
        return "Other (long tail)"
    return org_slug.replace("-", " ").title()


def provider_colour(provider: str) -> str:
    from app.lib.llm_perf import PROVIDER_COLOURS  # local import: keeps module st-free at top level
    if provider in PROVIDER_COLOURS:
        return PROVIDER_COLOURS[provider]
    if provider in EXTRA_PROVIDER_COLOURS:
        return EXTRA_PROVIDER_COLOURS[provider]
    return _FALLBACK_PALETTE[abs(hash(provider)) % len(_FALLBACK_PALETTE)]


def load_rankings_daily(path: Path | None = None) -> pd.DataFrame:
    """Return the full per-day/per-model dataset (or empty DataFrame)."""
    csv_path = Path(path) if path else CSV_PATH
    if not csv_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df["total_tokens"] = df["total_tokens"].astype("int64")
    df["org"] = df["model"].str.split("/", n=1).str[0]
    df["provider"] = df["org"].map(org_to_provider)
    return df.sort_values(["date", "model"]).reset_index(drop=True)


def load_usage_meta(path: Path | None = None) -> dict:
    meta_path = Path(path) if path else META_PATH
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def daily_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Total platform tokens per UTC day (top-50 + long-tail ``other`` rows)."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("date", as_index=False)["total_tokens"]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )


def provider_series(df: pd.DataFrame, top_n: int = 7) -> pd.DataFrame:
    """Per-day tokens by display provider.

    Keeps the ``top_n`` largest providers by cumulative tokens and folds the
    remainder (plus the API's own ``other`` long-tail row) into
    'Other (long tail)' so stacked views stay readable.
    """
    if df.empty:
        return pd.DataFrame()
    daily = df.groupby(["date", "provider"], as_index=False)["total_tokens"].sum()
    top_providers = (
        daily.groupby("provider")["total_tokens"].sum()
        .sort_values(ascending=False)
        .head(top_n).index.tolist()
    )
    daily["provider"] = daily["provider"].apply(
        lambda p: p if p in top_providers else "Other (long tail)"
    )
    return (
        daily.groupby(["date", "provider"], as_index=False)["total_tokens"].sum()
        .sort_values(["date", "provider"])
        .reset_index(drop=True)
    )


def fmt_tokens(value: float) -> str:
    """Human token formatting: 7_300_000_000_000 -> '7.3T'."""
    if value >= 1e12:
        return f"{value / 1e12:.2f}T"
    if value >= 1e9:
        return f"{value / 1e9:.1f}B"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    return f"{value:,.0f}"
