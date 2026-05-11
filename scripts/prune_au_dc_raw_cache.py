"""Prune old AU DC raw AEMO/NEMOSIS cache files.

The processed AU DC dashboard outputs are tiny; the bulky raw cache is mostly
monthly DISPATCHREGIONSUM CSVs. Routine automation only needs a recent raw
window plus processed outputs, so this keeps files newer than a retention
cutoff and removes older dated cache files.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "au_dc" / "raw" / "aemo" / "nemosis_cache"
DATE_RE = re.compile(r"(20\d{6})")


def _file_date(path: Path) -> datetime | None:
    match = DATE_RE.search(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def prune(cache_dir: Path, retention_days: int, dry_run: bool) -> tuple[int, int, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    kept = 0
    skipped_undated = 0

    if not cache_dir.exists():
        print(f"Cache directory does not exist: {cache_dir}")
        return removed, kept, skipped_undated

    for path in sorted(cache_dir.iterdir()):
        if not path.is_file():
            continue
        file_dt = _file_date(path)
        if file_dt is None:
            skipped_undated += 1
            continue
        if file_dt >= cutoff:
            kept += 1
            continue

        removed += 1
        print(f"{'Would remove' if dry_run else 'Removing'} {path.name}")
        if not dry_run:
            path.unlink()

    return removed, kept, skipped_undated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--retention-days", type=int, default=540)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    removed, kept, skipped = prune(args.cache_dir, args.retention_days, args.dry_run)
    print()
    print(f"Cache: {args.cache_dir}")
    print(f"Retention: {args.retention_days} days")
    print(f"Removed: {removed}")
    print(f"Kept dated files: {kept}")
    print(f"Skipped undated files: {skipped}")


if __name__ == "__main__":
    main()
