"""Refresh OpenRouter platform-wide token usage (datasets API, rankings-daily).

Fetches per-UTC-day total tokens for the top 50 models plus the aggregated
long-tail row, from the OpenRouter Datasets API, and merges the result into

    data/external/openrouter_rankings_daily.csv          (full history)
    data/external/openrouter_rankings_daily_meta.json    (provenance)

The dataset begins 2025-01-01. Incremental: resumes from the last date already
in the CSV, so re-runs are idempotent.

Auth: any OpenRouter API key authenticates the datasets endpoint. Resolution
order: $OPENROUTER_API_KEY, then macOS Keychain service "openrouter-api":
    security add-generic-password -a "$USER" -s openrouter-api -w '<KEY>'

Usage:
    python scripts/refresh_openrouter_usage.py            # incremental
    python scripts/refresh_openrouter_usage.py --full     # force full backfill
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = REPO_ROOT / "data" / "external" / "openrouter_rankings_daily.csv"
OUT_META = REPO_ROOT / "data" / "external" / "openrouter_rankings_daily_meta.json"

API_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily"
DATASET_FLOOR = dt.date(2025, 1, 1)  # dataset begins here
CSV_COLS = ["date", "model", "total_tokens", "source"]


def _get_api_key() -> str | None:
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key.strip()
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "openrouter-api", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _read_existing() -> dict[tuple[str, str], dict]:
    """Existing rows keyed by (date, model) -> row dict."""
    if not OUT_CSV.exists():
        return {}
    import csv as _csv
    with OUT_CSV.open(newline="") as f:
        rows = list(_csv.DictReader(f))
    return {(r["date"], r["model"]): r for r in rows if r.get("date")}


def _fetch_day_range(start: str, end: str, key: str) -> list[dict]:
    resp = requests.get(
        API_URL,
        params={"start_date": start, "end_date": end, "period": "day"},
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    )
    if resp.status_code == 401:
        sys.exit("ERROR: OpenRouter API key rejected (401). Check the key is valid.")
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("data", [])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="force full backfill from 2025-01-01")
    args = parser.parse_args()

    key = _get_api_key()
    if not key:
        print("ERROR: No OpenRouter API key found. Set OPENROUTER_API_KEY or store via:")
        print('  security add-generic-password -a "$USER" -s openrouter-api -w "KEY"')
        return

    # Determine window to fetch.
    yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    existing = _read_existing() if not args.full else {}
    existing_dates = sorted({d for (d, _m) in existing})
    if existing_dates:
        start = max(existing_dates[-1], DATASET_FLOOR.isoformat())
        start = (dt.date.fromisoformat(start) + dt.timedelta(days=1)).isoformat()
    else:
        start = DATASET_FLOOR.isoformat()
    end = yesterday.isoformat()

    if start > end:
        print(f"CSV already current through {end} — nothing to fetch.")
        print(f"Latest stored day: {existing_dates[-1] if existing_dates else '—'}")
        return

    print(f"Fetching rankings-daily {start} → {end} (UTC) ...")
    rows = _fetch_day_range(start, end, key)
    if not rows:
        print("  API returned no rows for the window.")
        return

    # Sanity: ~51 rows/day (top 50 + optional 'other' long-tail row).
    per_day: dict[str, int] = {}
    for r in rows:
        per_day[r["date"]] = per_day.get(r["date"], 0) + 1
    for d, n in sorted(per_day.items()):
        if n < 50:
            print(f"  WARN: {d} has only {n} rows (expected 50-51)")

    # Merge into existing history (idempotent upsert on date+model).
    merged = dict(existing)
    for r in rows:
        date = r["date"]
        slug = (r.get("model_permaslug") or "").strip()
        if not slug or not date:
            continue
        tokens = str(r.get("total_tokens", "0"))
        merged[(date, slug)] = {
            "date": date,
            "model": slug,
            "total_tokens": int(float(tokens)),
            "source": "OpenRouter Datasets API (rankings-daily)",
        }

    ordered = sorted(merged.values(), key=lambda r: (r["date"], r["model"]))
    csv_rows = [{k: r[k] for k in CSV_COLS} for r in ordered]

    import csv as _csv
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = _csv.DictWriter(f, fieldnames=CSV_COLS)
        writer.writeheader()
        writer.writerows(csv_rows)

    dates_sorted = sorted({r["date"] for r in ordered})
    meta = {
        "source": API_URL,
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data_start": dates_sorted[0] if dates_sorted else None,
        "data_end": dates_sorted[-1] if dates_sorted else None,
        "days": len(dates_sorted),
        "rows": len(csv_rows),
        "note": ("Top 50 public models per UTC day by total_tokens plus one aggregated 'other' "
                 "row for the long tail. Tokens = prompt + completion, native tokenizers. "
                 "Platform-wide OpenRouter traffic only; not spend."),
    }
    OUT_META.write_text(json.dumps(meta, indent=2))
    print(f"  Wrote {len(csv_rows)} rows ({meta['days']} days) → {OUT_CSV.name}")
    print(f"  Window now: {meta['data_start']} → {meta['data_end']}")


if __name__ == "__main__":
    main()
