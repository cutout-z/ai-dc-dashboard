"""Catalog the current AI/DC news feed into a durable event CSV.

The Streamlit page remains a live reader. This script is intended for the VPS
refresh lane, where changed `data/reference/news_catalog.csv` can be committed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.lib.news import fetch_news_buckets, flatten_news_buckets  # noqa: E402


CATALOG_PATH = PROJECT_ROOT / "data" / "reference" / "news_catalog.csv"
LOG_PATH = PROJECT_ROOT / "data" / "fetcher_log.json"

FIELDNAMES = [
    "catalog_key",
    "event_key",
    "first_seen_at",
    "last_seen_at",
    "seen_count",
    "last_bucket",
    "last_tier",
    "max_materiality_score",
    "title",
    "source",
    "url",
    "published",
    "summary",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = re.sub(r"<[^>]*$", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _read_catalog(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {row["catalog_key"]: row for row in csv.DictReader(f)}


def _write_catalog(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda row: row.get("last_seen_at", ""), reverse=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _write_log(status: str, count: int, notes: str = "") -> None:
    try:
        log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {}
    except Exception:
        log = {}
    log["catalog_news.py"] = {
        "last_run": _now_iso(),
        "status": status,
        "count": count,
        "notes": notes,
    }
    LOG_PATH.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


def catalog_news(max_per_bucket: int, include_low: bool, dry_run: bool) -> tuple[int, int, int]:
    news_data = fetch_news_buckets(max_per_bucket=max_per_bucket)
    current_items = flatten_news_buckets(news_data)
    current_items = [
        item for item in current_items
        if include_low or item.get("tier") in {"HIGH", "MEDIUM"}
    ]

    existing = _read_catalog(CATALOG_PATH)
    now = _now_iso()
    added = 0
    updated = 0

    for item in current_items:
        event_key = item.get("event_key") or ""
        catalog_key = event_key or item.get("url") or item.get("title", "")
        old = existing.get(catalog_key)
        old_max = float(old.get("max_materiality_score", 0) or 0) if old else 0.0
        score = float(item.get("materiality_score", 0) or 0)
        use_current_as_representative = old is None or score >= old_max

        if old is None:
            added += 1
            old = {field: "" for field in FIELDNAMES}
            old["catalog_key"] = catalog_key
            old["event_key"] = event_key
            old["first_seen_at"] = now
            old["seen_count"] = "0"
        else:
            updated += 1

        old["last_seen_at"] = now
        old["seen_count"] = str(int(old.get("seen_count") or 0) + 1)
        old["last_bucket"] = item.get("bucket", "")
        old["last_tier"] = item.get("tier", "")
        old["max_materiality_score"] = f"{max(old_max, score):.3f}"

        if use_current_as_representative:
            old["title"] = _clean_text(item.get("title"))
            old["source"] = _clean_text(item.get("source"))
            old["url"] = item.get("url", "")
            old["published"] = item.get("published") or ""
            old["summary"] = _clean_text(item.get("summary"))

        existing[catalog_key] = old

    if not dry_run:
        _write_catalog(CATALOG_PATH, list(existing.values()))
        _write_log(
            "ok",
            len(current_items),
            f"added={added}, updated={updated}, total_catalogued={len(existing)}",
        )

    return added, updated, len(existing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-per-bucket", type=int, default=50)
    parser.add_argument("--include-low", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    added, updated, total = catalog_news(
        max_per_bucket=args.max_per_bucket,
        include_low=args.include_low,
        dry_run=args.dry_run,
    )
    mode = "DRY RUN" if args.dry_run else "WROTE"
    print(f"{mode}: added={added} updated={updated} total_catalogued={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
