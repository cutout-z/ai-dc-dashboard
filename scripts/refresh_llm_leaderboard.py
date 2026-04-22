"""Refresh llm_leaderboard.json from api.zeroeval.com.

Fetches /leaderboard/models/full, filters to models with composite benchmark
scores, and writes top 30 to data/reference/llm_leaderboard.json.

Replaces the old Playwright/llm-stats.com scraper.

Usage:
    python scripts/refresh_llm_leaderboard.py
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

import requests

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "llm_leaderboard.json"

API_URL = "https://api.zeroeval.com/leaderboard/models/full"
BENCH_COLS = ["gpqa_score", "swe_bench_verified_score", "hle_score", "aime_2025_score"]


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


def _score(model: dict) -> float | None:
    scores = [model.get(c) for c in BENCH_COLS if model.get(c) is not None]
    if not scores:
        return None
    return sum(scores) / len(scores) * 100


def main() -> None:
    api_key = _get_api_key()
    if not api_key:
        print("ERROR: No API key found. Store via:")
        print('  security add-generic-password -a "llm-stats" -s "llm-stats-api" -w "KEY"')
        return

    print("Fetching from api.zeroeval.com/leaderboard/models/full ...")
    resp = requests.get(
        API_URL,
        params={"justCanonicals": "true"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    print(f"  {len(raw)} models returned")

    # Score and filter
    scored = []
    for m in raw:
        composite = _score(m)
        if composite is None:
            continue
        scored.append({
            "name":            m.get("name", ""),
            "org":             m.get("organization", ""),
            "source_board":    "api",
            "composite_score": round(composite, 1),
            "context_k":       round((m.get("context") or 0) / 1000, 0),
            "input_price":     m.get("input_price"),
            "output_price":    m.get("output_price"),
            "speed_cps":       m.get("throughput"),
            "gpqa":            round(m["gpqa_score"] * 100, 1) if m.get("gpqa_score") else None,
            "aime_2025":       round(m["aime_2025_score"] * 100, 1) if m.get("aime_2025_score") else None,
            "swe_bench":       round(m["swe_bench_verified_score"] * 100, 1) if m.get("swe_bench_verified_score") else None,
            "hle":             round(m["hle_score"] * 100, 1) if m.get("hle_score") else None,
            "license":         m.get("license", ""),
            "release_date":    m.get("release_date", ""),
        })

    top30 = sorted(scored, key=lambda x: x["composite_score"], reverse=True)[:30]
    for i, m in enumerate(top30, 1):
        m["rank"] = i

    payload = {
        "_meta": {
            "source": API_URL,
            "updated": datetime.date.today().isoformat(),
            "model_count_total": len(raw),
            "model_count_scored": len(scored),
            "note": "Top 30 models with composite benchmark score (mean GPQA/SWE-Bench/HLE/AIME-2025).",
        },
        "models": top30,
    }

    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"  {len(top30)} scored models written to {OUT_PATH}")
    print()
    for m in top30:
        print(
            f"  {m['rank']:2d}. {m['name']:<40} ({m['org']}) "
            f"score={m['composite_score']:.1f} gpqa={m['gpqa']} hle={m['hle']}"
        )


if __name__ == "__main__":
    main()
