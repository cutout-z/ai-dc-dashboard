"""Fetch LLM benchmark data from api.zeroeval.com and store in SQLite.

Populates:
  - llm_model_specs: model metadata, pricing, context, benchmark scores
  - llm_arena_elo: composite benchmark score used as a ranking proxy
    (true LMSYS Arena ELO isn't available via API; benchmark composite is a
     reasonable substitute for ranking purposes)

Usage:
    python scripts/fetch_llm_benchmarks.py
"""

from __future__ import annotations

import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"
API_URL = "https://api.zeroeval.com/leaderboard/models/full"

BENCH_COLS = [
    "gpqa_score",
    "swe_bench_verified_score",
    "hle_score",
    "aime_2025_score",
    "mmmlu_score",
]

ORG_TO_PROVIDER = {
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
    "Alibaba Cloud / Qwen Team": "Alibaba",
    "Qwen Team": "Alibaba",
}


def _get_api_key() -> str | None:
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


def run() -> None:
    api_key = _get_api_key()
    if not api_key:
        print("ERROR: No API key. Store via Keychain (service: llm-stats-api).")
        return

    print("Fetching from api.zeroeval.com ...")
    resp = requests.get(
        API_URL,
        params={"justCanonicals": "true"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    print(f"  {len(raw)} models returned")

    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)

    # ── llm_model_specs ────────────────────────────────────────────────────
    spec_rows = []
    for m in raw:
        bench_vals = [m[c] for c in BENCH_COLS if m.get(c) is not None]
        intel_score = sum(bench_vals) / len(bench_vals) * 100 if bench_vals else None
        provider = ORG_TO_PROVIDER.get(m.get("organization", ""), m.get("organization", ""))
        spec_rows.append({
            "snapshot_date":          snapshot_date,
            "model":                  m.get("name", ""),
            "provider":               provider,
            "intelligence_score":     round(intel_score, 2) if intel_score else None,
            "context_window":         m.get("context"),
            "input_price_per_m_tokens": m.get("input_price"),
            "output_speed_tps":       m.get("throughput"),
            # Extra cols for richer analysis
            "output_price_per_m_tokens": m.get("output_price"),
            "license":                m.get("license"),
            "release_date":           m.get("release_date"),
            "gpqa_score":             m.get("gpqa_score"),
            "swe_bench_verified_score": m.get("swe_bench_verified_score"),
            "hle_score":              m.get("hle_score"),
            "aime_2025_score":        m.get("aime_2025_score"),
            "mmmlu_score":            m.get("mmmlu_score"),
        })

    df_specs = pd.DataFrame(spec_rows)
    df_specs.to_sql("llm_model_specs", conn, if_exists="replace", index=False)
    print(f"  llm_model_specs: {len(df_specs)} rows")

    # ── llm_arena_elo (benchmark composite as ranking proxy) ───────────────
    elo_rows = []
    for m in raw:
        bench_vals = [m[c] for c in BENCH_COLS[:4] if m.get(c) is not None]
        if not bench_vals:
            continue
        composite = sum(bench_vals) / len(bench_vals) * 100
        provider = ORG_TO_PROVIDER.get(m.get("organization", ""), m.get("organization", ""))
        elo_rows.append({
            "snapshot_date": snapshot_date,
            "model":         m.get("name", ""),
            "provider":      provider,
            "elo":           round(composite, 1),
            "category":      "benchmark_composite",
        })

    df_elo = pd.DataFrame(elo_rows).sort_values("elo", ascending=False)
    df_elo.to_sql("llm_arena_elo", conn, if_exists="replace", index=False)
    print(f"  llm_arena_elo:   {len(df_elo)} rows (benchmark composite as elo proxy)")

    conn.commit()
    conn.close()
    print(f"Written to {DB_PATH}")


if __name__ == "__main__":
    run()
