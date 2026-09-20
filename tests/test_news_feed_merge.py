"""Unified News Feed: catalogue ∪ live fetch merge (2026-09-20).

The News page renders ONE feed — the durable catalogue plus live items that
have arrived since the last catalogue write — so this covers the join that
backs it: article identity (normalised source URL, S2-09) decides the dedupe,
a catalogued article is never forked by the same article arriving live, and
live-only rows are distinguishable (``status="Live"``, null ``seen``).

Run:  /opt/anaconda3/bin/python3 -m pytest tests/test_news_feed_merge.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from app.lib.news import (  # noqa: E402
    NEWS_FEED_COLUMNS,
    article_identity_key,
    merge_catalog_and_live_feed,
    normalise_url,
)

CATALOG_KEY = "https://www.datacenterdynamics.com/en/news/microsoft-150mw-deal"


def _catalog_frame(rows: list[dict] | None = None) -> pd.DataFrame:
    """Minimal catalogue frame shaped like data/reference/news_catalog.csv."""
    return pd.DataFrame(
        rows
        if rows is not None
        else [{
            "catalog_key": CATALOG_KEY,
            "event_key": "",
            "first_seen_at": "2026-07-31T23:51:20Z",
            "last_seen_at": "2026-09-18T23:51:27Z",
            "seen_count": 8,
            "last_bucket": "Hyperscaler CAPEX",
            "last_tier": "HIGH",
            "max_materiality_score": 0.820,
            "title": "Microsoft signs 150MW renewable deal",
            "source": "DatacenterDynamics",
            "url": CATALOG_KEY,
            "published": "2026-07-20T07:00:00+00:00",
            "summary": "Hyperscaler signs a large renewable PPA.",
        }],
    )


def _live_item(url: str = CATALOG_KEY, title: str = "Microsoft signs 150MW renewable deal",
               published: str | None = "2026-07-20T07:00:00+00:00",
               score: float = 0.5, tier: str = "MEDIUM",
               bucket: str = "Hyperscaler CAPEX") -> dict:
    return {
        "title": title,
        "url": url,
        "source": "DatacenterDynamics",
        "published": published,
        "published_str": "2026-07-20 07:00",
        "age_str": "60d ago",
        "summary": "",
        "materiality_score": score,
        "bucket": bucket,
        "url_key": normalise_url(url),
        "tier": tier,
    }


# ──────────────────────────────────────────────
# Empty / degenerate inputs
# ──────────────────────────────────────────────

def test_empty_inputs_return_the_column_contract():
    frame = merge_catalog_and_live_feed(pd.DataFrame(), [])
    assert list(frame.columns) == NEWS_FEED_COLUMNS
    assert frame.empty

    none_frame = merge_catalog_and_live_feed(None, None)
    assert list(none_frame.columns) == NEWS_FEED_COLUMNS
    assert none_frame.empty


def test_live_items_without_a_catalogue_still_render():
    frame = merge_catalog_and_live_feed(pd.DataFrame(), [_live_item()])
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["status"] == "Live"
    assert pd.isna(row["seen"])
    assert row["bucket"] == "Hyperscaler CAPEX"


# ──────────────────────────────────────────────
# Identity: one row per article, never forked
# ──────────────────────────────────────────────

def test_catalogued_article_arriving_live_is_one_row():
    frame = merge_catalog_and_live_feed(_catalog_frame(), [_live_item(score=0.95, tier="HIGH")])
    assert len(frame) == 1
    row = frame.iloc[0]
    # The catalogue row wins: it carries the durable observation state.
    assert row["status"] == "Catalogued"
    assert int(row["seen"]) == 8
    assert float(row["score"]) == 0.820


def test_identity_survives_tracking_params_and_trailing_slash():
    """Same article, click-tagged URL → identity collapses (S2-09)."""
    tagged = f"{CATALOG_KEY}?utm_source=newsletter&oc=5"
    frame = merge_catalog_and_live_feed(_catalog_frame(), [_live_item(url=tagged)])
    assert len(frame) == 1
    assert frame.iloc[0]["status"] == "Catalogued"

    slashed = merge_catalog_and_live_feed(_catalog_frame(), [_live_item(url=CATALOG_KEY + "/")])
    assert len(slashed) == 1


def test_urlless_live_item_falls_back_to_the_title_identity():
    url_less_catalog = _catalog_frame([{
        **_catalog_frame().iloc[0].to_dict(),
        "catalog_key": article_identity_key("", "Syndicated headline: same story"),
        "url": "",
        "title": "Syndicated headline: same story",
    }])
    frame = merge_catalog_and_live_feed(
        url_less_catalog,
        [_live_item(url="", title="Syndicated headline: same story")],
    )
    assert len(frame) == 1
    assert frame.iloc[0]["status"] == "Catalogued"


def test_distinct_live_articles_are_both_kept():
    frame = merge_catalog_and_live_feed(
        _catalog_frame(),
        [_live_item(url="https://ex.example/a", title="A"),
         _live_item(url="https://ex.example/b", title="B")],
    )
    assert len(frame) == 3
    assert sorted(set(frame["status"])) == ["Catalogued", "Live"]


# ──────────────────────────────────────────────
# Ordering + dtypes the page relies on
# ──────────────────────────────────────────────

def test_sorted_published_desc_ties_by_score_undated_last():
    frame = merge_catalog_and_live_feed(
        _catalog_frame(),
        [
            _live_item(url="https://ex.example/new", title="Newest", published="2026-09-19T00:00:00+00:00"),
            _live_item(url="https://ex.example/same-day-low", title="Same day low",
                       published="2026-07-20T07:00:00+00:00", score=0.1),
            _live_item(url="https://ex.example/undated", title="Undated", published=None, score=0.9),
        ],
    )
    assert list(frame["title"]) == [
        "Newest",
        "Microsoft signs 150MW renewable deal",
        "Same day low",
        "Undated",
    ]
    assert frame["published"].dtype.tz is not None
    assert str(frame["seen"].dtype) == "Int64"
    assert frame["score"].tolist() == [0.5, 0.82, 0.1, 0.9]
