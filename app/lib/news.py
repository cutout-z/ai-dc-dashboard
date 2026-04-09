"""News sourcing — Google News RSS per bucket + curated DC-specific feeds.

Hybrid approach:
- Each bucket has one or more Google News RSS search URLs built from keyword queries
- Plus a small set of direct RSS/Atom feeds that are DC/AI specific (DatacenterDynamics,
  The Register Data Centre)
- Results are deduped by URL, sorted by published date desc, and returned grouped.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import streamlit as st

logger = logging.getLogger("ai_research.news")

# ──────────────────────────────────────────────
# Bucket definitions
# ──────────────────────────────────────────────
# Each bucket = (label, list of Google News queries, list of direct feed URLs)

GN_BASE = "https://news.google.com/rss/search"


def _gn_url(query: str, gl: str = "US", hl: str = "en-US") -> str:
    params = {"q": query, "hl": hl, "gl": gl, "ceid": f"{gl}:{hl.split('-')[0]}"}
    return f"{GN_BASE}?{urllib.parse.urlencode(params)}"


# Direct DC-specific feeds
DIRECT_FEEDS = {
    "DatacenterDynamics": "https://www.datacenterdynamics.com/en/rss/",
    "The Register DC": "https://www.theregister.com/data_centre/headlines.atom",
}

BUCKETS: dict[str, dict] = {
    "Frontier Labs": {
        "queries": [
            "(OpenAI OR Anthropic OR xAI OR DeepMind OR Mistral) AI",
            "DeepSeek OR Moonshot AI",
        ],
        "direct": [],
    },
    "Hyperscaler CAPEX": {
        "queries": [
            "(Microsoft OR Amazon OR Google OR Meta) \"data center\" capex",
            "(Microsoft OR Amazon OR Google OR Meta) \"AI infrastructure\"",
        ],
        "direct": [],
    },
    "Supply Chain": {
        "queries": [
            "(TSMC OR ASML OR Nvidia OR Broadcom OR AMD) supply OR shortage OR demand",
            "HBM memory OR advanced packaging OR CoWoS",
        ],
        "direct": ["DatacenterDynamics", "The Register DC"],
    },
    "Model Releases": {
        "queries": [
            "\"model release\" (GPT OR Claude OR Gemini OR Llama OR DeepSeek)",
            "AI benchmark (MMLU OR GPQA OR \"SWE-bench\")",
        ],
        "direct": [],
    },
    "ANZ DC": {
        "queries": [
            "(NextDC OR AirTrunk OR CDC OR Infratil OR Macquarie) \"data centre\" Australia",
            "\"data centre\" (Australia OR \"New Zealand\")",
        ],
        "direct": [],
    },
    "China / Export Controls": {
        "queries": [
            "China AI chip export controls",
            "Huawei OR DeepSeek OR SMIC AI",
        ],
        "direct": [],
    },
}


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: datetime | None
    summary: str = ""

    @property
    def published_str(self) -> str:
        if self.published is None:
            return ""
        return self.published.strftime("%Y-%m-%d %H:%M")

    @property
    def age_str(self) -> str:
        if self.published is None:
            return "—"
        now = datetime.now(timezone.utc)
        delta = now - self.published
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m"
        if hours < 24:
            return f"{int(hours)}h"
        days = hours / 24
        if days < 30:
            return f"{int(days)}d"
        return self.published.strftime("%Y-%m-%d")


def _parse_published(entry) -> datetime | None:
    """Best-effort parse of an entry's published date into UTC datetime."""
    for key in ("published_parsed", "updated_parsed"):
        tup = getattr(entry, key, None)
        if tup:
            try:
                return datetime.fromtimestamp(time.mktime(tup), tz=timezone.utc)
            except Exception:
                continue
    return None


def _entry_source(entry, fallback: str) -> str:
    src = getattr(entry, "source", None)
    if src and isinstance(src, dict) and src.get("title"):
        return src["title"]
    if src and hasattr(src, "get"):
        return src.get("title", fallback)
    return fallback


def _fetch_feed(url: str, source_fallback: str) -> list[NewsItem]:
    try:
        parsed = feedparser.parse(url)
    except Exception as e:
        logger.warning("feedparser error for %s: %s", url, e)
        return []

    items: list[NewsItem] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=_entry_source(entry, source_fallback),
                published=_parse_published(entry),
                summary=getattr(entry, "summary", "")[:300],
            )
        )
    return items


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news_buckets(max_per_bucket: int = 20) -> dict[str, list[dict]]:
    """Fetch all configured buckets. Returns bucket_label -> list of item dicts.

    Returns dicts (not NewsItem objects) because Streamlit's cache serializes output.
    """
    result: dict[str, list[dict]] = {}
    for label, cfg in BUCKETS.items():
        seen_urls: set[str] = set()
        items: list[NewsItem] = []

        for query in cfg.get("queries", []):
            url = _gn_url(query)
            for item in _fetch_feed(url, source_fallback="Google News"):
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                items.append(item)

        for direct_name in cfg.get("direct", []):
            feed_url = DIRECT_FEEDS.get(direct_name)
            if not feed_url:
                continue
            for item in _fetch_feed(feed_url, source_fallback=direct_name):
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                items.append(item)

        # Sort by published desc, None last
        items.sort(key=lambda it: it.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        items = items[:max_per_bucket]

        result[label] = [
            {
                "title": it.title,
                "url": it.url,
                "source": it.source,
                "published": it.published.isoformat() if it.published else None,
                "published_str": it.published_str,
                "age_str": it.age_str,
                "summary": it.summary,
            }
            for it in items
        ]

    return result


def fetch_news_source_health() -> list[dict]:
    """For the Source Health page — one row per configured feed with last-fetch info."""
    cache = fetch_news_buckets()
    rows = []
    for bucket, items in cache.items():
        latest = items[0]["published_str"] if items else None
        rows.append({
            "bucket": bucket,
            "item_count": len(items),
            "latest": latest,
        })
    return rows
