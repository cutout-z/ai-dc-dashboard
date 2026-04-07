"""
Fetch LLM capability data from public sources.
Tracks: Arena Elo, context windows, pricing, speed, benchmark scores.
Sources: Artificial Analysis API, LMSYS/Arena leaderboard.
"""

import sqlite3
import json
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"

# Artificial Analysis has a public API endpoint for model data
AA_MODELS_URL = "https://artificialanalysis.ai/api/models"
AA_LEADERBOARD_URL = "https://artificialanalysis.ai/api/leaderboard"

# Arena leaderboard (public JSON endpoint)
ARENA_LEADERBOARD_URL = "https://arena.ai/api/v1/leaderboard"


def fetch_artificial_analysis():
    """Fetch model specs from Artificial Analysis."""
    print("  Fetching Artificial Analysis data...")
    records = []

    try:
        # Try the public leaderboard page data
        resp = requests.get(
            "https://artificialanalysis.ai/leaderboards/models",
            headers={"Accept": "text/html"},
            timeout=30,
        )
        # The actual data comes from their API - try known endpoints
        for endpoint in [
            "https://artificialanalysis.ai/api/models",
            "https://artificialanalysis.ai/api/v1/models",
        ]:
            try:
                r = requests.get(endpoint, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        for m in data:
                            records.append({
                                "model": m.get("name", m.get("model_name", "")),
                                "provider": m.get("provider", m.get("organization", "")),
                                "context_window": m.get("context_window"),
                                "input_price_per_m": m.get("input_price", m.get("price_input")),
                                "output_price_per_m": m.get("output_price", m.get("price_output")),
                                "tokens_per_sec": m.get("speed", m.get("output_speed")),
                                "intelligence_score": m.get("intelligence", m.get("quality_index")),
                            })
                    break
            except Exception:
                continue
    except Exception as e:
        print(f"    Warning: Artificial Analysis fetch failed: {e}")

    return records


def fetch_arena_leaderboard():
    """Fetch Arena Elo ratings."""
    print("  Fetching Arena leaderboard...")
    records = []

    # Try multiple known API endpoints
    endpoints = [
        "https://arena.ai/api/v1/leaderboard",
        "https://arena.ai/api/leaderboard",
    ]

    for endpoint in endpoints:
        try:
            r = requests.get(endpoint, timeout=15, headers={"Accept": "application/json"})
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", data.get("models", []))
                for m in items:
                    records.append({
                        "model": m.get("name", m.get("model", "")),
                        "provider": m.get("organization", m.get("provider", "")),
                        "elo_overall": m.get("score", m.get("elo", m.get("rating"))),
                        "category": "overall",
                    })
                break
        except Exception:
            continue

    return records


def build_snapshot_from_known_data():
    """
    Build a capability snapshot from the data we've already verified exists.
    This serves as the seed + fallback when APIs aren't directly accessible.
    Updated via web scraping in future runs.
    """
    now = datetime.now().isoformat()

    # Arena Elo data (from verified web fetch)
    arena_data = [
        ("claude-opus-4-6-thinking", "Anthropic", 1504),
        ("claude-opus-4-6", "Anthropic", 1499),
        ("gemini-3.1-pro-preview", "Google", 1494),
        ("grok-4.20-beta1", "xAI", 1491),
        ("gemini-3-pro", "Google", 1486),
        ("gpt-5.4-high", "OpenAI", 1484),
        ("grok-4.20-beta-0309-reasoning", "xAI", 1481),
        ("gpt-5.2-chat-latest", "OpenAI", 1478),
        ("gemini-3-flash", "Google", 1474),
        ("grok-4.20-multi-agent-beta", "xAI", 1474),
    ]

    # Model specs (from verified Artificial Analysis fetch)
    model_specs = [
        {"model": "Gemini 3.1 Pro Preview", "provider": "Google", "intelligence": 57, "context_window": 1000000, "input_price_per_m": 4.50, "output_speed_tps": 125},
        {"model": "GPT-5.4", "provider": "OpenAI", "intelligence": 57, "context_window": 1050000, "input_price_per_m": 5.63, "output_speed_tps": 74},
        {"model": "GPT-5.3 Codex", "provider": "OpenAI", "intelligence": 54, "context_window": 400000, "input_price_per_m": 4.81, "output_speed_tps": 84},
        {"model": "Claude Opus 4.6", "provider": "Anthropic", "intelligence": 53, "context_window": 1000000, "input_price_per_m": 10.00, "output_speed_tps": 48},
        {"model": "Claude Sonnet 4.6", "provider": "Anthropic", "intelligence": 52, "context_window": 1000000, "input_price_per_m": 6.00, "output_speed_tps": 64},
        {"model": "GPT-5.2", "provider": "OpenAI", "intelligence": 51, "context_window": 400000, "input_price_per_m": 4.81, "output_speed_tps": 77},
        {"model": "GLM-5", "provider": "Zhipu", "intelligence": 50, "context_window": 200000, "input_price_per_m": 1.55, "output_speed_tps": 72},
        {"model": "Claude Opus 4.5", "provider": "Anthropic", "intelligence": 50, "context_window": 200000, "input_price_per_m": 10.00, "output_speed_tps": 55},
        {"model": "MiniMax-M2.7", "provider": "MiniMax", "intelligence": 50, "context_window": 205000, "input_price_per_m": 0.53, "output_speed_tps": 54},
        {"model": "MiMo-V2-Pro", "provider": "Xiaomi", "intelligence": 49, "context_window": 1000000, "input_price_per_m": 1.50, "output_speed_tps": None},
        # Notable for speed/cost frontier
        {"model": "Mercury 2", "provider": "Inception", "intelligence": None, "context_window": None, "input_price_per_m": None, "output_speed_tps": 890},
        {"model": "Qwen3.5 0.8B", "provider": "Alibaba", "intelligence": None, "context_window": None, "input_price_per_m": 0.02, "output_speed_tps": None},
        {"model": "Llama 4 Scout", "provider": "Meta", "intelligence": None, "context_window": 10000000, "input_price_per_m": None, "output_speed_tps": None},
    ]

    return arena_data, model_specs


def run():
    print("Fetching LLM capability data...")
    snapshot_date = datetime.now().strftime("%Y-%m-%d")

    # Try live APIs first
    aa_records = fetch_artificial_analysis()
    arena_records = fetch_arena_leaderboard()

    # Fall back to verified snapshot if APIs didn't return data
    if not aa_records or not arena_records:
        print("  Using verified snapshot data (APIs may require browser access)...")
        arena_seed, specs_seed = build_snapshot_from_known_data()
    else:
        arena_seed, specs_seed = [], []

    conn = sqlite3.connect(DB_PATH)

    # Store Arena Elo ratings
    elo_records = []
    if arena_records:
        for r in arena_records:
            elo_records.append({
                "snapshot_date": snapshot_date,
                "model": r["model"],
                "provider": r["provider"],
                "elo": r.get("elo_overall"),
                "category": "overall",
            })
    else:
        for model, provider, elo in arena_seed:
            elo_records.append({
                "snapshot_date": snapshot_date,
                "model": model,
                "provider": provider,
                "elo": elo,
                "category": "overall",
            })

    df_elo = pd.DataFrame(elo_records)
    if not df_elo.empty:
        df_elo.to_sql("llm_arena_elo", conn, if_exists="replace", index=False)
        print(f"  Arena Elo: {len(df_elo)} models")

    # Store model specs
    spec_records = []
    source_data = aa_records if aa_records else specs_seed
    for m in source_data:
        spec_records.append({
            "snapshot_date": snapshot_date,
            "model": m.get("model", ""),
            "provider": m.get("provider", ""),
            "intelligence_score": m.get("intelligence", m.get("intelligence_score")),
            "context_window": m.get("context_window"),
            "input_price_per_m_tokens": m.get("input_price_per_m"),
            "output_speed_tps": m.get("output_speed_tps", m.get("tokens_per_sec")),
        })

    df_specs = pd.DataFrame(spec_records)
    if not df_specs.empty:
        df_specs.to_sql("llm_model_specs", conn, if_exists="replace", index=False)
        print(f"  Model specs: {len(df_specs)} models")

    conn.commit()
    conn.close()
    print(f"Written to {DB_PATH}")


if __name__ == "__main__":
    run()
