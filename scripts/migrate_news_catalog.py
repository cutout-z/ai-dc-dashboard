"""Migrate the news catalog to article-identity keys (normalised source URL).

S2-09: catalogue rows were keyed by a title-derived event key, so one article
whose headline changed between fetches forked into two rows, while genuinely
different stories that matched a broad company/event-class collapse rule
(CDC 555 MW vs 200 MW contracts, any Cerebras IPO story) were merged into one
row. Identity is now the normalised source URL (`catalog_news.py` keys on it);
this script rewrites the committed CSV:

  1. every row's `catalog_key` -> normalised source URL (declared fallback:
     `title:<normalised-title>` when a row has no usable URL);
  2. rows whose keys collide (identical URL seen under several titles/sources)
     are merged with a reviewed mapping — earliest first-seen, latest
     last-seen, summed seen_count, max materiality score, representative
     fields from the highest-scored row, differing sources retained joined;
  3. `event_key` values are recomputed as the OPTIONAL exact-headline grouping
     (shared only when two distinct articles carry the same normalised title);
     the old company/event-class collapse values are dropped.

Dry-run by default: prints a full migration report (every merge with the old
keys/titles/sources/counts) and writes nothing. Pass `--write` to persist the
migrated CSV in place (or `--out` to write to another path). Idempotent:
re-running on a migrated catalog reports zero merges and rewrites identical
bytes.

Usage:
    python scripts/migrate_news_catalog.py            # review the mapping
    python scripts/migrate_news_catalog.py --write    # persist
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.lib.news import article_identity_key, normalise_title_key  # noqa: E402

# Reuse the catalog writer's field list + event-group recompute so migration
# and the daily producer cannot drift apart.
_catalog_spec = importlib.util.spec_from_file_location(
    "catalog_news_shared",
    PROJECT_ROOT / "scripts" / "catalog_news.py",
)
assert _catalog_spec and _catalog_spec.loader, "cannot locate scripts/catalog_news.py"
_catalog_mod = importlib.util.module_from_spec(_catalog_spec)
_catalog_spec.loader.exec_module(_catalog_mod)
FIELDNAMES = _catalog_mod.FIELDNAMES
_recompute_event_groups = _catalog_mod._recompute_event_groups

DEFAULT_PATH = PROJECT_ROOT / "data" / "reference" / "news_catalog.csv"


def _num(row: dict, field: str, default: float = 0.0) -> float:
    try:
        return float(row.get(field) or default)
    except (TypeError, ValueError):
        return default


def _score_key(row: dict) -> tuple:
    """Deterministic representative ordering: score, seen count, last seen."""
    return (
        _num(row, "max_materiality_score"),
        int(_num(row, "seen_count")),
        row.get("last_seen_at", "") or "",
    )


def migrate_catalog(rows: list[dict]) -> tuple[list[dict], dict]:
    """Return the migrated row list + a reviewable mapping report.

    The report is the reviewed mapping: every merge lists the old keys,
    titles, sources and counts that collapsed into the surviving row, so a
    human can confirm nothing unrecoverable was dropped.
    """
    report: dict = {
        "input_rows": len(rows),
        "merged": [],
        "fallback_keyed": [],
        "unkeyed": [],
    }

    # Group by article identity; preserve original order for determinism.
    groups: dict[str, list[dict]] = {}
    unkeyed_rows: list[dict] = []
    for idx, row in enumerate(rows):
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        if not url and not title:
            report["unkeyed"].append(
                {"catalog_key": row.get("catalog_key") or str(idx), "title": title}
            )
            row["catalog_key"] = f"unkeyed:{row.get('catalog_key') or idx}"
            unkeyed_rows.append(row)
            continue
        identity = article_identity_key(url, title)
        if identity.startswith("title:") and url:
            # URL present but unusable (non-absolute) — still its own article.
            identity = article_identity_key("", title)
            report["fallback_keyed"].append(
                {"url": url, "title": title, "key": identity}
            )
        groups.setdefault(identity, []).append(row)

    migrated = list(unkeyed_rows)

    for identity in sorted(groups):
        group = groups[identity]
        if len(group) == 1:
            row = dict(group[0])
            row["catalog_key"] = identity
            migrated.append(row)
            continue

        ordered = sorted(
            group,
            key=lambda r: _score_key(r),
            reverse=True,
        )
        rep = dict(ordered[0])
        rep["catalog_key"] = identity
        rep["first_seen_at"] = min(
            (r.get("first_seen_at") or "") for r in group
        ) or rep.get("first_seen_at", "")
        rep["last_seen_at"] = max(
            (r.get("last_seen_at") or "") for r in group
        ) or rep.get("last_seen_at", "")
        rep["seen_count"] = str(
            sum(int(_num(r, "seen_count")) for r in group)
        )
        rep["max_materiality_score"] = f"{max(_num(r, 'max_materiality_score') for r in group):.3f}"
        sources = sorted({(r.get("source") or "").strip() for r in group if (r.get("source") or "").strip()})
        if len(sources) > 1:
            rep["source"] = " | ".join(sources)
        migrated.append(rep)
        report["merged"].append(
            {
                "identity": identity,
                "rows": [
                    {
                        "catalog_key": r.get("catalog_key"),
                        "title": (r.get("title") or "")[:120],
                        "source": r.get("source", ""),
                        "seen_count": r.get("seen_count", "0"),
                        "max_materiality_score": r.get("max_materiality_score", ""),
                        "last_seen_at": r.get("last_seen_at", ""),
                    }
                    for r in group
                ],
                "retained_title": (rep.get("title") or "")[:120],
                "retained_source": rep.get("source", ""),
                "seen_count_sum": rep["seen_count"],
            }
        )

    _recompute_event_groups({r["catalog_key"]: r for r in migrated})
    migrated.sort(key=lambda r: r.get("last_seen_at", ""), reverse=True)
    report["output_rows"] = len(migrated)
    return migrated, report


def _format_report(report: dict) -> str:
    lines = [f"news_catalog identity migration report", ""]
    lines.append(f"rows before : {report['input_rows']}")
    lines.append(f"rows after  : {report['output_rows']}")
    lines.append(f"url merges  : {len(report['merged'])}")
    if report["merged"]:
        lines.append("")
        lines.append("Merged identical-URL rows (reviewed mapping):")
        for m in report["merged"]:
            lines.append(f"  identity {m['identity']}")
            lines.append(f"    retained: title={m['retained_title']!r} source={m['retained_source']!r} seen_count_sum={m['seen_count_sum']}")
            for r in m["rows"]:
                lines.append(
                    f"    + old key={r['catalog_key']!r} seen={r['seen_count']} "
                    f"max={r['max_materiality_score']} last={r['last_seen_at']} "
                    f"title={r['title']!r} source={r['source']!r}"
                )
    if report["fallback_keyed"]:
        lines.append("")
        lines.append(f"Rows re-keyed via title fallback (no usable URL): {len(report['fallback_keyed'])}")
        for f in report["fallback_keyed"]:
            lines.append(f"  url={f['url']!r} title={f['title']!r} -> key={f['key']!r}")
    if report["unkeyed"]:
        lines.append("")
        lines.append(f"UNRECOVERABLE rows (no URL and no title, cannot be keyed): {len(report['unkeyed'])}")
        for u in report["unkeyed"]:
            lines.append(f"  {u['catalog_key']!r} title={u['title']!r}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--write", action="store_true", help="persist the migrated CSV")
    parser.add_argument("--out", type=Path, default=None, help="write migrated CSV to this path")
    args = parser.parse_args()

    path = args.path.resolve()
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    migrated, report = migrate_catalog(rows)
    print(_format_report(report))

    if args.write or args.out:
        out_path = (args.out or path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(migrated)
        print(f"\nwrote {len(migrated)} rows to {out_path}")
    else:
        print("\nDRY RUN — pass --write to persist (or --out for another path).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
