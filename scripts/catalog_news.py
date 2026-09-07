"""Catalog the current AI/DC news feed into a durable event CSV.

The Streamlit page remains a live reader. This script is intended for the VPS
refresh lane, where changed `data/reference/news_catalog.csv` can be committed.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.lib.news import (  # noqa: E402
    _fetch_news_buckets_uncached,
    fetch_stats_summary,
    flatten_news_buckets,
)
from app.lib.run_result import final_status, now_iso, write_log_record  # noqa: E402


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


def _merge_items(
    existing: dict[str, dict],
    current_items: list[dict],
    *,
    seen_at: str,
    include_low: bool,
) -> tuple[int, int]:
    current_items = [
        item for item in current_items
        if include_low or item.get("tier") in {"HIGH", "MEDIUM"}
    ]

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
            old["first_seen_at"] = seen_at
            old["seen_count"] = "0"
        else:
            updated += 1

        old["last_seen_at"] = seen_at
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

    return added, updated


def catalog_news(
    max_per_bucket: int,
    include_low: bool,
    dry_run: bool,
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> tuple[int, int, int]:
    # Live fetch (bypasses the Streamlit cache) with per-feed result stats so
    # all-feeds-down is detectable instead of collapsing into a silent "ok".
    feed_stats = {"attempted": 0, "succeeded": 0, "failed_feeds": []}
    news_data = _fetch_news_buckets_uncached(
        max_per_bucket=max_per_bucket,
        start_date=start_date,
        end_date=end_date,
        stats=feed_stats,
    )
    current_items = flatten_news_buckets(news_data)
    current_items = [
        item for item in current_items
        if include_low or item.get("tier") in {"HIGH", "MEDIUM"}
    ]
    attempted, succeeded = feed_stats["attempted"], feed_stats["succeeded"]
    status = final_status(succeeded, attempted)

    existing = _read_catalog(CATALOG_PATH)

    if not current_items and not dry_run:
        # Feeds may be down but the catalog is not empty: an unchanged (or
        # empty) rewrite would advance mtime without observations and look
        # like success. Preserve last-good rows, log the failure, exit hard.
        write_log_record(
            LOG_PATH,
            "catalog_news.py",
            status="error",
            attempted=attempted,
            succeeded=succeeded,
            observations=0,
            notes=(
                f"no observations fetched ({fetch_stats_summary(feed_stats)}); "
                f"catalog unchanged with {len(existing)} rows"
            ),
            count=0,
        )
        raise SystemExit(
            "catalog_news: no observations fetched — catalog preserved, "
            f"see {LOG_PATH} ({fetch_stats_summary(feed_stats)})"
        )

    now = now_iso()
    added, updated = _merge_items(
        existing,
        current_items,
        seen_at=now,
        include_low=include_low,
    )

    if not dry_run:
        _write_catalog(CATALOG_PATH, list(existing.values()))
        write_log_record(
            LOG_PATH,
            "catalog_news.py",
            status=status,
            attempted=attempted,
            succeeded=succeeded,
            observations=len(current_items),
            notes=(
                f"added={added}, updated={updated}, "
                f"total_catalogued={len(existing)}; {fetch_stats_summary(feed_stats)}"
            ),
            count=len(current_items),
        )

    return added, updated, len(existing)


def _date_windows(days: int, window_days: int) -> list[tuple[date, date]]:
    if days <= 0:
        raise ValueError("--backfill-days must be positive")
    if window_days <= 0:
        raise ValueError("--window-days must be positive")

    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=days)
    windows = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(days=window_days), end)
        windows.append((cursor, nxt))
        cursor = nxt
    return windows


def catalog_backfill(
    *,
    days: int,
    window_days: int,
    max_per_bucket: int,
    include_low: bool,
    dry_run: bool,
) -> tuple[int, int, int, int]:
    existing = _read_catalog(CATALOG_PATH)
    now = now_iso()
    added_total = 0
    updated_total = 0
    item_total = 0
    feed_stats = {"attempted": 0, "succeeded": 0, "failed_feeds": []}
    windows = _date_windows(days, window_days)

    for start, end in windows:
        news_data = _fetch_news_buckets_uncached(
            max_per_bucket=max_per_bucket,
            start_date=start,
            end_date=end,
            stats=feed_stats,
        )
        current_items = flatten_news_buckets(news_data)
        current_items = [
            item for item in current_items
            if include_low or item.get("tier") in {"HIGH", "MEDIUM"}
        ]
        item_total += len(current_items)
        added, updated = _merge_items(
            existing,
            current_items,
            seen_at=now,
            include_low=include_low,
        )
        added_total += added
        updated_total += updated
        print(
            f"{start.isoformat()} to {end.isoformat()}: "
            f"items={len(current_items)} added={added} updated={updated}"
        )

    attempted, succeeded = feed_stats["attempted"], feed_stats["succeeded"]
    status = final_status(succeeded, attempted)

    if not dry_run:
        if item_total == 0:
            # No observations at all: an unchanged rewrite would advance mtime
            # without content. Preserve last-good rows and report honestly.
            if succeeded == 0:
                write_log_record(
                    LOG_PATH,
                    "catalog_news.py",
                    status="error",
                    attempted=attempted,
                    succeeded=succeeded,
                    observations=0,
                    notes=(
                        f"backfill fetched no observations, all feed requests failed "
                        f"({fetch_stats_summary(feed_stats)}); catalog unchanged "
                        f"with {len(existing)} rows"
                    ),
                    count=0,
                )
                raise SystemExit(
                    "catalog_backfill: no observations fetched — catalog "
                    f"preserved, see {LOG_PATH}"
                )
            write_log_record(
                LOG_PATH,
                "catalog_news.py",
                status=status,
                attempted=attempted,
                succeeded=succeeded,
                observations=0,
                notes=(
                    f"backfill_days={days}, window_days={window_days}: feeds "
                    f"responded but no items matched the windows; catalog "
                    f"unchanged with {len(existing)} rows; "
                    f"{fetch_stats_summary(feed_stats)}"
                ),
                count=0,
            )
            print("No items matched any window — catalog left unchanged (mtime preserved).")
            return added_total, updated_total, len(existing), len(windows)

        _write_catalog(CATALOG_PATH, list(existing.values()))
        write_log_record(
            LOG_PATH,
            "catalog_news.py",
            status=status,
            attempted=attempted,
            succeeded=succeeded,
            observations=item_total,
            notes=(
                f"backfill_days={days}, window_days={window_days}, "
                f"added={added_total}, updated={updated_total}, "
                f"total_catalogued={len(existing)}; {fetch_stats_summary(feed_stats)}"
            ),
            count=item_total,
        )

    return added_total, updated_total, len(existing), len(windows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-per-bucket", type=int, default=50)
    parser.add_argument("--include-low", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=0,
        help="Walk Google News date windows for the trailing N days and merge them into the catalog.",
    )
    parser.add_argument("--window-days", type=int, default=7)
    args = parser.parse_args()

    if args.backfill_days:
        added, updated, total, windows = catalog_backfill(
            days=args.backfill_days,
            window_days=args.window_days,
            max_per_bucket=args.max_per_bucket,
            include_low=args.include_low,
            dry_run=args.dry_run,
        )
        mode = "DRY RUN" if args.dry_run else "WROTE"
        print(f"{mode}: windows={windows} added={added} updated={updated} total_catalogued={total}")
        return 0

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
