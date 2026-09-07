"""Refresh the committed LLM benchmark snapshot + TrueSkill index artifacts.

Single producer for the LLM-performance data chain (Astra S2-12 / C14):

  data/reference/llm_leaderboard.json  — source-faithful FULL-FIELD model snapshot
                                         (every row of /leaderboard/models/full,
                                         verbatim)
  data/reference/llm_indexes.json      — ZeroEval TrueSkill index data, separately
                                         identified (/leaderboard/indexes/all)

Both artifacts are schema-validated against the shared reader contract
(app/lib/llm_snapshot.py) BEFORE anything is written; a schema-change or a
malformed response fails the run with exit code 2 and leaves the committed
artifacts untouched. The publisher never stores a rank or composite score —
readers derive displayed scores or read published TrueSkill values.

Replaces the old Playwright/llm-stats.com scraper AND the redundant
fetch_llm_benchmarks.py SQLite writer (composite-as-"elo" fabrication removed).

Usage:
    python scripts/refresh_llm_leaderboard.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.lib import llm_snapshot  # noqa: E402

MODELS_OUT = llm_snapshot.models_path()
INDEXES_OUT = llm_snapshot.indexes_path()


def _get_api_key() -> str | None:
    env_key = os.environ.get("ZEROEVAL_API_KEY") or os.environ.get("LLM_STATS_API_KEY")
    if env_key:
        return env_key.strip()
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


def _headers() -> dict[str, str]:
    key = _get_api_key()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def main() -> int:
    headers = _headers()
    print("Fetching ZeroEval models (full-field canonical rows) ...")
    try:
        models_resp = requests.get(
            llm_snapshot.MODELS_SOURCE_URL,
            params={"justCanonicals": "true"},
            headers=headers,
            timeout=45,
        )
        models_resp.raise_for_status()
        raw_models = models_resp.json()
        if not isinstance(raw_models, list) or not raw_models:
            raise ValueError(f"expected a non-empty list, got {type(raw_models).__name__}")
    except Exception as exc:  # network or shape failure -> nothing written
        print(f"ERROR: models fetch failed: {exc}", file=sys.stderr)
        return 2
    print(f"  {len(raw_models)} models returned")

    print("Fetching ZeroEval TrueSkill indexes ...")
    try:
        idx_resp = requests.get(llm_snapshot.INDEXES_SOURCE_URL, headers=headers, timeout=60)
        idx_resp.raise_for_status()
        raw_indexes = idx_resp.json()
        if not isinstance(raw_indexes, dict) or not raw_indexes:
            raise ValueError(f"expected a non-empty dict, got {type(raw_indexes).__name__}")
    except Exception as exc:
        print(f"ERROR: indexes fetch failed: {exc}", file=sys.stderr)
        return 2
    print(f"  {len(raw_indexes)} index categories returned")

    # ── Build + validate BOTH payloads before any write (schema-change gate) ──
    models_payload = llm_snapshot.build_models_payload(raw_models)
    indexes_payload = llm_snapshot.build_indexes_payload(raw_indexes)
    for payload, which, out in (
        (models_payload, "models", MODELS_OUT),
        (indexes_payload, "indexes", INDEXES_OUT),
    ):
        errors = (
            llm_snapshot.validate_models_payload(payload)
            if which == "models"
            else llm_snapshot.validate_indexes_payload(payload)
        )
        if errors:
            print(f"ERROR: {which} payload failed contract validation — nothing written:", file=sys.stderr)
            for err in errors[:25]:
                print(f"  - {err}", file=sys.stderr)
            return 2

    fetched_at = models_payload["_meta"]["fetched_at"]
    _atomic_write(MODELS_OUT, json.dumps(models_payload, indent=2))
    _atomic_write(INDEXES_OUT, json.dumps(indexes_payload, indent=2))

    print(f"  models snapshot  -> {MODELS_OUT} "
          f"({models_payload['_meta']['model_count']} models)")
    print(f"  indexes snapshot -> {INDEXES_OUT} "
          f"({indexes_payload['_meta']['index_count']} categories, "
          f"{indexes_payload['_meta']['model_entry_count']} entries)")
    print(f"  as-of (updated): {models_payload['_meta']['updated']} · fetched {fetched_at}")
    print("  Both artifacts contract-validated before write; committed data unchanged on any failure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
