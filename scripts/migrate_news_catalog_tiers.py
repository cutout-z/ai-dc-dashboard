"""Reclassify stored HIGH news rows under the S2-10 common source-quality gate.

S2-10: display tier previously returned HIGH immediately — a raw score of
0.85+ bypassed the source-quality gate, so articles from unverified sources
(aggregators, unrecognised outlets) displayed HIGH on magnitude alone. The
live gate in ``app/lib/news_scoring.get_display_tier`` now runs a common
trust gate before ANY visible material tier: HIGH/MEDIUM require a verified
source (trust >= 0.70); unrecognised sources stay LOW no matter how large the
claimed magnitude.

This script applies that correction to the committed catalog WITHOUT deleting
historical evidence — every row is kept, only ``last_tier`` changes:

  * stored HIGH rows from a verified source (trust >= 0.70) stay HIGH;
  * stored HIGH rows from an unverified source are demoted to LOW.

MEDIUM rows are left untouched: they already ran the same trust gate at
catalog time (only HIGH bypassed it), so their stored tier is the corrected
rule's own output. Stored rows are reclassified on the source-trust gate only
— never by re-running the event/marker regexes over stored title/summary
fields, because the persisted summary is often empty/truncated and a trusted
row whose event marker lived in an unpersisted summary must not be demoted by
stored-text lossiness (the max_materiality_score column alone proves a HIGH
event was seen: score >= 0.85 is unreachable without one).

Dry-run by default: prints the full demotion report (title, source, trust,
score, bucket, published) and writes nothing. Pass ``--write`` to persist in
place (or ``--out`` for another path). Idempotent: re-running on a migrated
catalog reports zero changes and rewrites identical bytes.

Usage:
    python scripts/migrate_news_catalog_tiers.py            # review the mapping
    python scripts/migrate_news_catalog_tiers.py --write    # persist
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.lib.news_scoring import (  # noqa: E402
    TRUSTED_SOURCE_THRESHOLD,
    get_source_trust,
)

DEFAULT_PATH = PROJECT_ROOT / "data" / "reference" / "news_catalog.csv"


def _num(row: dict, field: str, default: float = 0.0) -> float:
    try:
        return float(row.get(field) or default)
    except (TypeError, ValueError):
        return default


def reclassify_tiers(rows: list[dict]) -> tuple[list[dict], dict]:
    """Return rows with stored HIGH tiers corrected + a reviewable report.

    Only ``last_tier`` changes and only for stored HIGH rows. The report is
    the reviewed mapping: every demotion lists title, source, trust, score,
    bucket and published date so a human can confirm the demoted outlets are
    genuinely unverified (no verified primary/trade source was lost).
    """
    report: dict = {
        "input_rows": len(rows),
        "high_before": 0,
        "demoted": [],
        "kept_high": 0,
    }
    out: list[dict] = []
    for row in rows:
        if (row.get("last_tier") or "") != "HIGH":
            out.append(dict(row))
            continue
        report["high_before"] += 1
        source = row.get("source") or ""
        trust = get_source_trust(source)
        if trust >= TRUSTED_SOURCE_THRESHOLD:
            report["kept_high"] += 1
            out.append(dict(row))
            continue
        new = dict(row)
        new["last_tier"] = "LOW"
        out.append(new)
        report["demoted"].append(
            {
                "title": (new.get("title") or "")[:140],
                "source": source,
                "trust": trust,
                "max_materiality_score": new.get("max_materiality_score", ""),
                "bucket": new.get("last_bucket", ""),
                "published": new.get("published", ""),
                "catalog_key": new.get("catalog_key", ""),
            }
        )
    report["output_rows"] = len(out)
    return out, report


def _format_report(report: dict) -> str:
    lines = [
        "news_catalog S2-10 source-quality gate — tier reclassification report",
        "",
        f"rows before : {report['input_rows']}",
        f"rows after  : {report['output_rows']} (rows kept — historical evidence preserved)",
        f"stored HIGH : {report['high_before']}",
        f"  kept HIGH (verified source, trust >= 0.70): {report['kept_high']}",
        f"  demoted to LOW (unverified source):        {len(report['demoted'])}",
    ]
    if report["demoted"]:
        lines.append("")
        lines.append("Demoted HIGH -> LOW (magnitude alone can no longer display HIGH):")
        for d in report["demoted"]:
            lines.append(
                f"  [{d['published']}] bucket={d['bucket']} trust={d['trust']:.2f} "
                f"score={d['max_materiality_score']} source={d['source']!r} "
                f"title={d['title']!r}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--write", action="store_true", help="persist the reclassified CSV")
    parser.add_argument("--out", type=Path, default=None, help="write reclassified CSV to this path")
    args = parser.parse_args()

    path = args.path.resolve()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    out, report = reclassify_tiers(rows)
    print(_format_report(report))

    if args.write or args.out:
        out_path = (args.out or path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(out)
        print(f"\nwrote {len(out)} rows to {out_path}")
    else:
        print("\nDRY RUN — pass --write to persist (or --out for another path).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
