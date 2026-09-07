"""S2-10 (C12) verification: common source-quality (trust) gate before HIGH.

Review reproductions (astra-review-2026-09-04 S2-10):
- display tier previously returned HIGH immediately — ``get_display_tier``
  only ran its trust/event gates when the raw tier was MEDIUM, so a fresh
  synthetic unknown-source Anthropic contract scored 0.88 and displayed HIGH
  with trust 0.40; 22 of 65 stored HIGH rows had trust below 0.70
  (magnitude/keywords overrode the intended quality boundary);
- after the fix: a common trust gate runs BEFORE any visible material tier —
  HIGH and MEDIUM alike require a verified source (trust >= 0.70);
  unrecognised sources stay LOW no matter how large the claimed magnitude;
  known Reuters/Bloomberg/company events retain intended treatment; the ANZ
  DC bucket keeps its deliberately lower materiality bar for genuine operator
  news; stored HIGH rows are reclassified on the trust gate only (migration
  script), preserving every row as historical evidence.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # noqa: E402

from app.lib.news_scoring import (  # noqa: E402
    TRUSTED_SOURCE_THRESHOLD,
    get_display_tier,
    get_materiality_tier,
    get_source_trust,
    score_news_item,
)

# scripts/migrate_news_catalog_tiers.py is a runnable script, not a package.
_migrate_spec = importlib.util.spec_from_file_location(
    "migrate_news_catalog_tiers", REPO / "scripts" / "migrate_news_catalog_tiers.py"
)
assert _migrate_spec and _migrate_spec.loader, "cannot locate scripts/migrate_news_catalog_tiers.py"
_migrate = importlib.util.module_from_spec(_migrate_spec)
_migrate_spec.loader.exec_module(_migrate)

reclassify_tiers = _migrate.reclassify_tiers
FIELDNAMES = [
    "catalog_key", "event_key", "first_seen_at", "last_seen_at", "seen_count",
    "last_bucket", "last_tier", "max_materiality_score", "title", "source",
    "url", "published", "summary",
]


def _item(score, title, source, summary="", bucket="Frontier Labs"):
    return {
        "materiality_score": score,
        "title": title,
        "summary": summary,
        "source": source,
    }, bucket


def _row(**over):
    row = {
        "catalog_key": "https://example.com/a",
        "event_key": "", "first_seen_at": "2026-09-01T00:00:00Z",
        "last_seen_at": "2026-09-01T00:00:00Z", "seen_count": "1",
        "last_bucket": "Frontier Labs", "last_tier": "HIGH",
        "max_materiality_score": "0.880", "title": "Anthropic signs $45bn deal",
        "source": "Unknown Blog", "url": "https://example.com/a",
        "published": "2026-09-01T00:00:00+00:00", "summary": "",
    }
    row.update(over)
    return row


# ──────────────────────────────────────────────
# Review reproduction: unknown source cannot bypass the gate
# ──────────────────────────────────────────────

def test_review_repro_unknown_source_cannot_bypass_high():
    # The review's synthetic: an unknown-source Anthropic $45B contract scores
    # 0.88 raw (magnitude + ticker + recency) — old code displayed HIGH with
    # trust 0.40 because HIGH returned before the gates ran.
    published = datetime.now(timezone.utc)
    text = "Anthropic signs $45 billion compute capacity agreement with Nscale"
    score = score_news_item(text, "", "Some Unknown Blog", published)
    assert score >= 0.85, f"fixture must reach raw HIGH tier, got {score}"
    assert get_source_trust("Some Unknown Blog") < TRUSTED_SOURCE_THRESHOLD

    item, bucket = _item(score, text, "Some Unknown Blog")
    assert get_display_tier(item, bucket) == "LOW"
    # Same bypass in the ANZ DC bucket — unverified source never displays HIGH.
    assert get_display_tier(item, "ANZ DC") == "LOW"


def test_unknown_source_medium_also_low():
    item, _ = _item(0.55, "NextDC secures new customer lease", "Unknown Blog")
    assert get_display_tier(item, "ANZ DC") == "LOW"


def test_recognised_but_unverified_source_below_gate_stays_low():
    # TechCrunch is *recognised* in the map (0.55, tier-4 general tech) but is
    # not a verified primary/trade source — magnitude cannot promote it.
    item, _ = _item(0.90, "Anthropic signs $45 billion compute deal with Nscale", "TechCrunch")
    assert get_display_tier(item, "Frontier Labs") == "LOW"
    assert get_display_tier(item, "ANZ DC") == "LOW"
    # Yahoo Finance is a recognised aggregator (0.45) — same rule.
    item, _ = _item(0.88, "Anthropic signs $45 billion compute deal with Nscale", "Yahoo Finance")
    assert get_display_tier(item, "Frontier Labs") == "LOW"


# ──────────────────────────────────────────────
# Known verified sources retain intended treatment
# ──────────────────────────────────────────────

def test_known_reuters_bloomberg_company_events_retain_high():
    text = "Anthropic signs $45 billion compute capacity agreement with Nscale"
    published = datetime.now(timezone.utc)
    for source in ("Reuters", "Bloomberg", "Anthropic", "Data Center Dynamics"):
        score = score_news_item(text, "", source, published)
        assert score >= 0.85
        item, _ = _item(score, text, source)
        assert get_display_tier(item, "Frontier Labs") == "HIGH", source
        assert get_display_tier(item, "ANZ DC") == "HIGH", source


def test_new_york_times_deliberately_added_as_verified():
    # The catalog carried an Anthropic-valuation HIGH row from The New York
    # Times that defaulted to trust 0.40; NYT was added deliberately as a
    # verified source (S2-10: "add verified primary/trade sources
    # deliberately"), so it keeps HIGH.
    assert get_source_trust("The New York Times") == 0.85
    assert get_source_trust("https://www.nytimes.com") == 0.85
    item, _ = _item(
        0.875,
        "Anthropic in Talks to Raise Funding at a $950 Billion Valuation",
        "The New York Times",
    )
    assert get_display_tier(item, "Frontier Labs") == "HIGH"


def test_trusted_boundary_source_high():
    # trust exactly 0.70 (trade press boundary) passes the common gate.
    assert TRUSTED_SOURCE_THRESHOLD == 0.70
    for source in ("Data Center Dynamics", "The Register", "Capital Brief"):
        item, _ = _item(0.90, "Anthropic signs $45 billion compute deal with Nscale", source)
        assert get_display_tier(item, "Frontier Labs") == "HIGH", source
        assert get_display_tier(item, "ANZ DC") == "HIGH", source


# ──────────────────────────────────────────────
# MEDIUM semantics preserved (incl. ANZ lower bar)
# ──────────────────────────────────────────────

def test_anz_keeps_lower_materiality_bar_for_operator_news():
    # Genuine ANZ operator news from a trusted source with a magnitude marker
    # stays MEDIUM on a raw-MEDIUM score (Capital Brief is exactly 0.70).
    item, _ = _item(
        0.575, "NextDC expects 50% earnings growth in FY27 as it starts billing new customers",
        "Capital Brief", bucket="ANZ DC",
    )
    assert get_display_tier(item, "ANZ DC") == "MEDIUM"
    # Untrusted ANZ operator news with the same magnitude marker is LOW.
    item, _ = _item(
        0.575, "NextDC expects 50% earnings growth in FY27 as it starts billing new customers",
        "Yahoo Finance", bucket="ANZ DC",
    )
    assert get_display_tier(item, "ANZ DC") == "LOW"


def test_anz_marker_required():
    # Trusted ANZ source but no event/magnitude marker and score < 0.48 -> LOW.
    item, _ = _item(0.42, "NextDC publishes a routine corporate governance note", "AFR", bucket="ANZ DC")
    assert get_display_tier(item, "ANZ DC") == "LOW"


def test_non_anz_medium_needs_high_event_and_score():
    # Trusted source + HIGH-level event + score >= 0.78 -> MEDIUM.
    item, _ = _item(
        0.82, "NEXTDC signs $1.6 billion senior debt facilities to fund expansion", "Reuters",
    )
    assert get_materiality_tier(0.82) == "MEDIUM"
    assert get_display_tier(item, "Frontier Labs") == "MEDIUM"
    # Trusted source but no thesis-level event (exclusive talks, not a signed
    # material contract) -> LOW even with a high raw-MEDIUM score.
    item, _ = _item(0.83, "EXCLUSIVE: Anthropic in talks with chip start up MatX", "Reuters")
    assert get_display_tier(item, "Frontier Labs") == "LOW"
    # MEDIUM raw below 0.78 -> LOW for non-ANZ.
    item, _ = _item(0.60, "Anthropic signs $45 billion compute deal with Nscale", "Reuters")
    assert get_display_tier(item, "Frontier Labs") == "LOW"


def test_low_raw_never_promoted_by_trust():
    item, _ = _item(0.20, "some random filler", "Reuters")
    assert get_display_tier(item, "Frontier Labs") == "LOW"
    assert get_display_tier(item, "ANZ DC") == "LOW"


def test_raw_tier_boundaries_unchanged():
    assert get_materiality_tier(0.849) == "MEDIUM"
    assert get_materiality_tier(0.85) == "HIGH"
    assert get_materiality_tier(0.40) == "MEDIUM"
    assert get_materiality_tier(0.399) == "LOW"


def test_high_score_without_event_marker_is_low():
    # Structural contract: even a trusted source cannot display HIGH when the
    # text carries no thesis-level event (unreachable via score_news_item —
    # raw >= 0.85 requires a HIGH event — but the gate must not trust a bare
    # number). Verifies the gate no longer returns HIGH unconditionally.
    item, _ = _item(0.90, "OpenAI ships a routine product update today", "Reuters")
    assert get_display_tier(item, "Frontier Labs") == "LOW"


# ──────────────────────────────────────────────
# Stored-row reclassification (migration)
# ──────────────────────────────────────────────

def test_migration_demotes_unverified_high_keeps_verified_and_medium():
    rows = [
        _row(catalog_key="https://x/a", last_tier="HIGH", source="incrypted",
             max_materiality_score="0.858",
             title="Media: Anthropic Signed $45B Contract with AI Infrastructure Provider",
             last_bucket="Frontier Labs"),
        _row(catalog_key="https://x/b", last_tier="HIGH", source="Reuters",
             max_materiality_score="0.933",
             title="Australia's NEXTDC signs $1.6 billion senior debt facilities to fund expansion",
             last_bucket="ANZ DC"),
        _row(catalog_key="https://x/c", last_tier="HIGH", source="The New York Times",
             max_materiality_score="0.875",
             title="Anthropic in Talks to Raise Funding at a $950 Billion Valuation",
             last_bucket="Frontier Labs"),
        _row(catalog_key="https://x/d", last_tier="MEDIUM", source="incrypted",
             max_materiality_score="0.575",
             title="Some medium story from an unverified outlet",
             last_bucket="Frontier Labs"),
        _row(catalog_key="https://x/e", last_tier="HIGH", source="Data Center Dynamics",
             max_materiality_score="0.896",
             title="Anthropic signs $45 billion compute capacity agreement with Nscale",
             last_bucket="Frontier Labs"),
    ]
    out, report = reclassify_tiers(rows)
    assert report["input_rows"] == 5
    assert report["high_before"] == 4
    assert len(report["demoted"]) == 1
    assert report["kept_high"] == 3
    assert report["demoted"][0]["source"] == "incrypted"
    assert report["output_rows"] == 5  # nothing deleted — evidence preserved
    by_key = {r["catalog_key"]: r for r in out}
    assert by_key["https://x/a"]["last_tier"] == "LOW"          # unverified HIGH demoted
    assert by_key["https://x/b"]["last_tier"] == "HIGH"         # Reuters kept
    assert by_key["https://x/c"]["last_tier"] == "HIGH"         # NYT (added) kept
    assert by_key["https://x/d"]["last_tier"] == "MEDIUM"       # MEDIUM untouched
    assert by_key["https://x/e"]["last_tier"] == "HIGH"         # trade press kept
    # Only last_tier changed; every other field byte-identical.
    for r, nr in zip(rows, out):
        for field, value in r.items():
            if field != "last_tier":
                assert nr[field] == value, field


def test_migration_idempotent_and_preserves_order():
    rows = [
        _row(catalog_key="https://x/a", last_tier="HIGH", source="incrypted",
             max_materiality_score="0.858"),
        _row(catalog_key="https://x/b", last_tier="HIGH", source="Reuters",
             max_materiality_score="0.933"),
        _row(catalog_key="https://x/c", last_tier="MEDIUM", source="incrypted",
             max_materiality_score="0.575"),
    ]
    first, report1 = reclassify_tiers(rows)
    assert len(report1["demoted"]) == 1
    second, report2 = reclassify_tiers(first)
    assert len(report2["demoted"]) == 0  # idempotent — re-run changes nothing
    assert [r["catalog_key"] for r in second] == [r["catalog_key"] for r in rows]
    assert [r["last_tier"] for r in second] == ["LOW", "HIGH", "MEDIUM"]


def test_migration_csv_round_trip_in_tmp(tmp_path):
    # Round-trip through the real 13-column schema with a quoting-sensitive
    # title — unchanged cells must survive byte-identically.
    rows = [
        _row(catalog_key="https://x/1", last_tier="HIGH", source="incrypted",
             title="Media: Anthropic Signed $45B Contract, with \"quotes\"",
             max_materiality_score="0.858"),
        _row(catalog_key="https://x/2", last_tier="HIGH", source="Reuters",
             title="Australia's NEXTDC signs $1.6 billion senior debt facilities",
             max_materiality_score="0.933"),
    ]
    out, _ = reclassify_tiers(rows)
    csv_path = tmp_path / "news_catalog.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(out)
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        reread = list(reader)
    assert len(reread) == 2
    assert reread[0]["last_tier"] == "LOW"
    assert reread[0]["title"] == 'Media: Anthropic Signed $45B Contract, with "quotes"'
    assert reread[1]["last_tier"] == "HIGH"
    assert reread[1]["max_materiality_score"] == "0.933"
    # Re-run on the round-tripped rows stays idempotent.
    _, report2 = reclassify_tiers(reread)
    assert len(report2["demoted"]) == 0
