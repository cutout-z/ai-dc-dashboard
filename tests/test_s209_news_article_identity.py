"""S2-09 (C11) verification: article identity = normalised source URL.

Review reproductions (astra-review-2026-09-04 S2-09):
- catalogue rows were keyed by a title-derived event key, so a changed title
  on the same URL forked a second row (live pair: the NextDC $1.5bn raising
  article catalogued under two keys), while broad company/event-class collapse
  rules merged genuinely distinct stories (two CDC customer contracts, any
  Cerebras IPO story incl. a withdrawal) into one row;
- after the fix: identity is the normalised source URL (declared title
  fallback); event grouping is a separate OPTIONAL relation derived from an
  exact normalised-headline match and never collapses rows; the broad class
  collapse rules are gone; identical-URL rows migrate with a reviewed mapping
  (report lists every merge, sources retained).
"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(REPO))  # noqa: E402

from app.lib.news import (  # noqa: E402
    article_identity_key,
    flatten_news_buckets,
    normalise_title_key,
    normalise_url,
)

# scripts/catalog_news.py is a runnable script, not a package — load by path.
_catalog_spec = importlib.util.spec_from_file_location(
    "catalog_news", REPO / "scripts" / "catalog_news.py"
)
assert _catalog_spec and _catalog_spec.loader, "cannot locate scripts/catalog_news.py"
_catalog = importlib.util.module_from_spec(_catalog_spec)
_catalog_spec.loader.exec_module(_catalog)

_migrate_spec = importlib.util.spec_from_file_location(
    "migrate_news_catalog", REPO / "scripts" / "migrate_news_catalog.py"
)
assert _migrate_spec and _migrate_spec.loader, "cannot locate scripts/migrate_news_catalog.py"
_migrate = importlib.util.module_from_spec(_migrate_spec)
_migrate_spec.loader.exec_module(_migrate)

merge_items = _catalog._merge_items
FIELDNAMES = _catalog.FIELDNAMES
migrate_catalog = _migrate.migrate_catalog

GN = "https://news.google.com/rss/articles/CBMiTESTARTICLE"


# ──────────────────────────────────────────────
# URL normalisation / identity helpers
# ──────────────────────────────────────────────

def test_normalise_url_declared_rules():
    cases = {
        # (input, expected)
        "fragment stripped": (
            "https://example.com/a/story#section-2",
            "https://example.com/a/story",
        ),
        "utm params stripped, others kept sorted": (
            "https://example.com/a?utm_source=rss&utm_medium=feed&id=42&z=1&a=2",
            "https://example.com/a?a=2&id=42&z=1",
        ),
        "google news oc param stripped, article token kept": (
            f"{GN}?oc=5",
            GN,
        ),
        "host case + default port + trailing slash": (
            "HTTPS://Example.COM:443/en/news/story/",
            "https://example.com/en/news/story",
        ),
        "duplicate slashes collapsed": (
            "https://example.com/a//b///c",
            "https://example.com/a/b/c",
        ),
        "bare origin keeps root": ("https://example.com/", "https://example.com"),
        "blank returns blank": ("   ", ""),
        "non-absolute left untouched": ("news.google.com/rss/articles/X", "news.google.com/rss/articles/X"),
    }
    for name, (raw, expected) in cases.items():
        assert normalise_url(raw) == expected, name


def test_identity_is_normalised_url():
    assert article_identity_key(f"{GN}?oc=5", "any title") == GN
    assert article_identity_key("https://X.com/a?utm_source=rss", "t") == "https://x.com/a"
    # different titles, same URL -> same identity
    assert article_identity_key(GN, "First headline") == article_identity_key(
        GN + "?oc=5", "Changed headline"
    )


def test_identity_declared_title_fallback():
    # No usable URL -> explicit, inspectable fallback key (never an opaque hash).
    key = article_identity_key("", "Cerebras bumps up IPO range - CNBC")
    assert key == f"title:{normalise_title_key('Cerebras bumps up IPO range - CNBC')}"
    assert key.startswith("title:")
    # stable for the same title; distinct for distinct titles
    assert article_identity_key("", "Same headline here") == article_identity_key(
        "", "Same headline here"
    )
    assert article_identity_key("", "Headline one") != article_identity_key("", "Headline two")
    # a real URL key never collides with the fallback namespace
    assert not article_identity_key("https://x.com/a", "t").startswith("title:")


# ──────────────────────────────────────────────
# Feed flattening: no broad class collapse
# ──────────────────────────────────────────────

def _item(title: str, url: str) -> dict:
    return {"title": title, "url": url, "summary": "", "published": None,
            "materiality_score": 0.5, "source": "Test Source"}


def test_flatten_keeps_two_cdc_contracts():
    # Both would have collapsed to "cdc-infratil-us-customer-contract" under
    # the old normalise_event_key rules -> only one survived the feed.
    items = flatten_news_buckets({
        "ANZ DC": [
            _item("CDC Data Centres signs monster 555 MW US customer deal - Bloomberg",
                  "https://www.bloomberg.com/a/555"),
            _item("CDC Data Centres wins 200 MW contract in new market - AFR",
                  "https://www.afr.com/a/200"),
        ]
    })
    assert len(items) == 2
    assert {it["url_key"] for it in items} == {
        "https://www.bloomberg.com/a/555",
        "https://www.afr.com/a/200",
    }


def test_flatten_keeps_ipo_filing_and_withdrawal_distinct():
    items = flatten_news_buckets({
        "Frontier Labs": [
            _item("Cerebras bumps up IPO range as it looks to raise up to $4.8 billion - CNBC",
                  "https://www.cnbc.com/a/filing"),
            _item("Cerebras withdraws IPO filing, cites market conditions - Reuters",
                  "https://www.reuters.com/a/withdrawal"),
        ]
    })
    assert len(items) == 2


def test_flatten_dedupes_same_article_url_variants_and_exact_title_dupes():
    # utm variant of the same URL -> one; identical headline from a mirror URL
    # (syndication) -> collapsed in the live feed only, by exact title.
    items = flatten_news_buckets({
        "Hyperscaler CAPEX": [
            _item("Microsoft doubles data centre spend - Bloomberg", "https://x.com/a?utm_source=rss"),
            _item("Microsoft doubles data centre spend - Bloomberg", "https://x.com/a?utm_source=tw"),
            _item("Microsoft doubles data centre spend - Bloomberg", "https://y.com/mirror"),
        ]
    })
    assert len(items) == 1


# ──────────────────────────────────────────────
# Catalog merge semantics (identity-keyed)
# ──────────────────────────────────────────────

def _feed_item(title: str, url: str, *, score: float = 0.5, bucket: str = "ANZ DC",
               published: str = "2026-05-19T00:00:00+00:00",
               source: str = "The Australian") -> dict:
    return {
        "title": title,
        "url": url,
        "url_key": normalise_url(url),
        "source": source,
        "bucket": bucket,
        "tier": "HIGH",
        "published": published,
        "summary": "summary",
        "materiality_score": score,
    }


def _blank_row() -> dict:
    return {f: "" for f in FIELDNAMES}


def test_same_url_changed_title_upserts_one_article():
    url = GN + "?oc=5"
    existing = {}
    seen_1 = "2026-04-20T07:00:00+00:00"
    seen_2 = "2026-05-19T00:03:05Z"
    added, updated = merge_items(
        existing,
        [
            _feed_item("Barrenjoey joins two others to advise on NextDC's $1.5bn raising - The Australian",
                       url, score=0.520, published="2026-04-20T07:00:00+00:00"),
            _feed_item("NextDC secures $1.5bn raise after landing Microsoft contract - The Australian",
                       url, score=0.700, published="2026-04-20T07:00:00+00:00"),
        ],
        seen_at=seen_1,
        include_low=False,
    )
    assert (added, updated) == (1, 1)
    assert len(existing) == 1
    row = existing[normalise_url(url)]
    assert row["catalog_key"] == normalise_url(url)
    assert row["seen_count"] == "2"
    assert row["first_seen_at"] == seen_1
    assert row["max_materiality_score"] == "0.700"
    # representative is the higher-scored headline, but the article is one row
    assert "NextDC secures" in row["title"]
    # a third sighting of the same URL (any title) still updates the same row
    added2, updated2 = merge_items(
        existing,
        [_feed_item("NextDC raising attracts strong demand - The Australian", url, score=0.4)],
        seen_at=seen_2,
        include_low=False,
    )
    assert (added2, updated2) == (0, 1)
    assert len(existing) == 1
    assert existing[normalise_url(url)]["seen_count"] == "3"
    assert existing[normalise_url(url)]["last_seen_at"] == seen_2
    # lower-scored follow-up does not overwrite the higher-scored representative
    assert "NextDC secures" in existing[normalise_url(url)]["title"]


def test_two_cdc_contracts_remain_two_rows():
    # The old collapse rule mapped both headlines to one key -> one row.
    # Identity is the URL, so two distinct contracts stay two rows.
    existing = {}
    merge_items(existing, [
        _feed_item("CDC Data Centres signs monster 555 MW US customer deal - Bloomberg",
                   "https://www.bloomberg.com/a/555", score=0.8),
        _feed_item("CDC Data Centres wins 200 MW contract in new market - AFR",
                   "https://www.afr.com/a/200", score=0.6),
    ], seen_at="2026-05-19T00:00:00Z", include_low=False)
    assert len(existing) == 2
    keys = set(existing)
    assert "https://www.bloomberg.com/a/555" in keys
    assert "https://www.afr.com/a/200" in keys
    # different stories -> no shared event group
    assert all(row["event_key"] == "" for row in existing.values())


def test_ipo_filing_and_withdrawal_remain_distinct():
    existing = {}
    merge_items(existing, [
        _feed_item("Cerebras bumps up IPO range as it looks to raise up to $4.8 billion - CNBC",
                   "https://www.cnbc.com/a/filing", score=0.8),
        _feed_item("Cerebras withdraws IPO filing, cites market conditions - Reuters",
                   "https://www.reuters.com/a/withdrawal", score=0.9),
    ], seen_at="2026-05-19T00:00:00Z", include_low=False)
    assert len(existing) == 2


def test_syndicated_copies_group_without_deleting_sources():
    # Two distinct outlets carry the exact same headline (syndication):
    # two rows survive (one per source), sharing an optional event_key.
    existing = {}
    merge_items(existing, [
        _feed_item("Microsoft to spend $120bn on AI data centres - Reuters",
                   "https://www.reuters.com/a/msft", score=0.7, source="Reuters"),
        _feed_item("Microsoft to spend $120bn on AI data centres - Bloomberg",
                   "https://www.bloomberg.com/a/msft", score=0.7, source="Bloomberg"),
    ], seen_at="2026-05-19T00:00:00Z", include_low=False)
    assert len(existing) == 2
    groups = {row["event_key"] for row in existing.values()}
    assert len(groups) == 1
    key = groups.pop()
    assert key == normalise_title_key("Microsoft to spend $120bn on AI data centres - Reuters")
    sources = {row["source"] for row in existing.values()}
    assert sources == {"Reuters", "Bloomberg"}


def test_url_less_items_keyed_by_declared_fallback():
    existing = {}
    item = _feed_item("A headline with no url - Source", "", score=0.5)
    item.pop("url_key")
    added, updated = merge_items(existing, [item, dict(item)],
                                 seen_at="2026-05-19T00:00:00Z", include_low=False)
    assert (added, updated) == (1, 1)
    assert len(existing) == 1
    key = next(iter(existing))
    assert key == f"title:{normalise_title_key('A headline with no url - Source')}"


def test_new_row_keeps_required_columns_for_source_health():
    existing = {}
    merge_items(existing, [
        _feed_item("Some contract story - AFR", "https://www.afr.com/x", score=0.6),
    ], seen_at="2026-05-19T00:00:00Z", include_low=False)
    row = next(iter(existing.values()))
    for col in ("catalog_key", "title", "source", "published"):
        assert col in row and row[col] != ""


# ──────────────────────────────────────────────
# Migration: identical-URL rows -> reviewed mapping
# ──────────────────────────────────────────────

def _csv_row(catalog_key: str, title: str, url: str, *, seen: str, first: str,
             last: str, score: str, source: str = "The Australian") -> dict:
    return {
        "catalog_key": catalog_key, "event_key": catalog_key,
        "first_seen_at": first, "last_seen_at": last, "seen_count": seen,
        "last_bucket": "ANZ DC", "last_tier": "HIGH",
        "max_materiality_score": score, "title": title, "source": source,
        "url": url, "published": "2026-04-20T07:00:00+00:00",
        "summary": "s",
    }


def test_migration_merges_live_identical_url_pair():
    # The two live rows (review rows 45/64): same Google News URL, different
    # title-derived keys, one article that changed headline between fetches.
    url = GN + "?oc=5"
    rows = [
        _csv_row("barrenjoey joins two others to advise on nextdc s 1 5bn raising",
                 "Barrenjoey joins two others to advise on NextDC's $1.5bn raising - The Australian",
                 url, seen="4", first="2026-04-20T07:00:00+00:00",
                 last="2026-07-10T23:51:40Z", score="0.520"),
        _csv_row("nextdc secures 1 5bn raise after landing microsoft contract",
                 "NextDC secures $1.5bn raise after landing Microsoft contract - The Australian",
                 url, seen="1", first="2026-04-20T07:00:00+00:00",
                 last="2026-05-19T00:03:05Z", score="0.700"),
        _csv_row("infratil s cdc stake hits 8b as datacentre expansion drives valuation surge",
                 "Infratil's CDC stake hits $8b as datacentre expansion drives valuation surge - Bloomberg",
                 "https://news.google.com/rss/articles/CBMiOTHER", seen="2",
                 first="2026-05-01T00:00:00+00:00", last="2026-06-01T00:00:00Z",
                 score="0.600", source="Bloomberg"),
    ]
    migrated, report = migrate_catalog(rows)
    assert len(migrated) == 2, report
    assert report["input_rows"] == 3
    assert report["output_rows"] == 2
    assert len(report["merged"]) == 1
    merge_report = report["merged"][0]
    assert merge_report["identity"] == normalise_url(url)
    assert {r["catalog_key"] for r in merge_report["rows"]} == {
        "barrenjoey joins two others to advise on nextdc s 1 5bn raising",
        "nextdc secures 1 5bn raise after landing microsoft contract",
    }
    keys = {r["catalog_key"] for r in migrated}
    assert normalise_url(url) in keys
    assert "barrenjoey joins two others to advise on nextdc s 1 5bn raising" not in keys
    merged = next(r for r in migrated if r["catalog_key"] == normalise_url(url))
    assert merged["seen_count"] == "5"          # 4 + 1 sightings preserved
    assert merged["max_materiality_score"] == "0.700"
    assert "NextDC secures" in merged["title"]  # higher-scored representative
    assert merged["url"] == url
    assert merged["first_seen_at"] == "2026-04-20T07:00:00+00:00"
    assert merged["last_seen_at"] == "2026-07-10T23:51:40Z"
    # untouched row keeps its own identity (now URL-keyed)
    other = next(r for r in migrated if r["catalog_key"].startswith("https://news.google.com/rss/articles/CBMiOTHER"))
    assert other["seen_count"] == "2"


def test_migration_is_idempotent_and_reviewable():
    url = GN + "?oc=5"
    rows = [
        _csv_row("key old title a", "Title A - The Australian", url,
                 seen="2", first="2026-04-20T07:00:00+00:00",
                 last="2026-06-01T00:00:00Z", score="0.5"),
        _csv_row("key old title b", "Title B - The Australian", url,
                 seen="1", first="2026-04-20T07:00:00+00:00",
                 last="2026-05-19T00:03:05Z", score="0.8"),
    ]
    migrated, report = migrate_catalog(rows)
    assert report["output_rows"] == 1
    again, report2 = migrate_catalog(migrated)
    assert report2["merged"] == []
    assert report2["output_rows"] == 1
    # byte-identical rewrite
    import io

    def _dump(rs):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=FIELDNAMES, lineterminator="\n")
        w.writeheader()
        w.writerows(rs)
        return buf.getvalue()
    assert _dump(migrated) == _dump(again)


def test_migration_reports_unkeyable_rows():
    rows = [
        _csv_row("good key", "Good title - The Australian", GN,
                 seen="1", first="2026-04-20T07:00:00+00:00",
                 last="2026-05-19T00:03:05Z", score="0.5"),
        {"catalog_key": "orphan", "title": "", "url": "", "seen_count": "1"},
    ]
    migrated, report = migrate_catalog(rows)
    assert len(report["unkeyed"]) == 1
    assert report["unkeyed"][0]["catalog_key"] == "orphan"
    assert len(migrated) == 2  # preserved, flagged, never silently dropped


def test_migration_normalises_existing_event_keys():
    # Old class-collapse value "cerebras-ipo" disappears under the new
    # optional exact-headline grouping for a lone article.
    rows = [
        _csv_row("cerebras-ipo",
                 "Cerebras bumps up IPO range as it looks to raise up to $4.8 billion - CNBC",
                 "https://news.google.com/rss/articles/CBMiCEREBRAS", seen="3",
                 first="2026-05-01T00:00:00+00:00", last="2026-05-19T00:03:05Z",
                 score="0.8", source="CNBC"),
    ]
    migrated, report = migrate_catalog(rows)
    assert report["output_rows"] == 1
    assert migrated[0]["event_key"] == ""
    assert migrated[0]["catalog_key"].startswith("https://news.google.com/")
