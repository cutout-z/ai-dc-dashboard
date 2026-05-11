"""News sourcing — Google News RSS per bucket + curated DC-specific feeds.

Hybrid approach:
- Each bucket has one or more Google News RSS search URLs built from keyword queries
- Plus a small set of direct RSS/Atom feeds that are DC/AI specific (DatacenterDynamics,
  The Register Data Centre)
- Results are deduped by URL, sorted by published date desc, and returned grouped.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import streamlit as st

from app.lib.news_scoring import score_news_item

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

BLOCKED_SOURCE_PATTERNS = (
    "analytics india magazine",
    "business standard",
    "deccan herald",
    "economic times",
    "financial express",
    "hindustan times",
    "india today",
    "indian express",
    "inc42",
    "livemint",
    "moneycontrol",
    "ndtv",
    "news18",
    "ad hoc news",
    "asatunews",
    "finimize",
    "futu",
    "kalkine media",
    "marketscreener",
    "moomoo",
    "msn",
    "prop news time",
    "proactive financial news",
    "proactive investors",
    "stocktwits",
    "stocks down under",
    "tahawultech",
    "the fast mode",
    "the hindu",
    "the daily star",
    "the motley fool",
    "the times of india",
    "thebull",
    "times of india",
    "tradingview",
    "trak.in",
    "varindia",
    "verdict",
    "wccftech",
    "yourstory",
    "zeebiz",
    "富途牛牛",
)


def is_blocked_news_source(source: str) -> bool:
    lower = source.lower()
    return any(pattern in lower for pattern in BLOCKED_SOURCE_PATTERNS)


def normalise_title_key(title: str) -> str:
    # Google News often appends " - Source" to titles; remove that tail for de-duping.
    base = re.sub(r"\s+-\s+[^-]{2,80}$", "", title).lower()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


def normalise_event_key(title: str) -> str:
    lower = normalise_title_key(title)
    if "cdc" in lower and "555" in lower and "data cent" in lower:
        return "cdc-555mw-data-centre-contract"
    if "anthropic" in lower and "akamai" in lower and ("1 8" in lower or "cloud deal" in lower):
        return "anthropic-akamai-cloud-contract"
    if "eu commission" in lower and "openai" in lower and "anthropic" in lower:
        return "eu-commission-openai-anthropic"
    if "cerebras" in lower and "ipo" in lower:
        return "cerebras-ipo"
    if "apple" in lower and "cleanmax" in lower and "150mw" in lower:
        return "apple-cleanmax-150mw"
    return lower


_ANZ_OPERATOR_PATTERNS = [
    re.compile(r"\b(CDC Data Centres?|NEXTDC|AirTrunk|Keppel Data Centres?|Keppel DC)\b", re.I),
    re.compile(r"\b(Stack Infrastructure|Macquarie Data Centres?|Vantage Data Cent(?:ers|res))\b", re.I),
    re.compile(r"\b(Doma Infrastructure Group|Equinix|DigiCo Infrastructure REIT|Leading Edge Data Centres?)\b", re.I),
    re.compile(r"\bTelstra InfraCo\b", re.I),
    re.compile(r"\bFujitsu\b.{0,140}\b(data cent(?:er|re)|hyperscale|cloud)\b", re.I),
    re.compile(r"\bGoodman\b.{0,140}\b(data cent(?:er|re)|hyperscale|AI infrastructure)\b", re.I),
    re.compile(r"\b(data cent(?:er|re)|hyperscale|AI infrastructure)\b.{0,140}\bGoodman\b", re.I),
    re.compile(r"\bInfratil\b.{0,140}\b(CDC|data cent(?:er|re)|hyperscale)\b", re.I),
    re.compile(r"\b(CDC|data cent(?:er|re)|hyperscale)\b.{0,140}\bInfratil\b", re.I),
    re.compile(r"\bMacquarie\b.{0,140}\b(data cent(?:er|re)|hyperscale|cloud services)\b", re.I),
    re.compile(r"\bNCI\b.{0,140}\bdata cent(?:er|re)\b", re.I),
]

_ANZ_REGION_PATTERNS = [
    re.compile(r"\b(Australia|Australian|Aussie|New Zealand|NZ|ASX|NZX)\b", re.I),
    re.compile(r"\b(Sydney|Melbourne|Brisbane|Perth|Canberra|Adelaide|Auckland|Wellington)\b", re.I),
    re.compile(r"\b(NSW|Victoria|Queensland|Western Australia|South Australia)\b", re.I),
    re.compile(r"\b(NEXTDC|NXT\.AX|DigiCo|Infratil|IFT\.NZ|CDC Data Centres?)\b", re.I),
]


def is_anz_operator_news(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}"
    has_operator = any(pattern.search(text) for pattern in _ANZ_OPERATOR_PATTERNS)
    has_region = any(pattern.search(text) for pattern in _ANZ_REGION_PATTERNS)
    return has_operator and has_region


BUCKETS: dict[str, dict] = {
    "Frontier Labs": {
        "queries": [
            "(OpenAI OR Anthropic OR xAI OR DeepMind OR Mistral) (funding OR valuation OR revenue OR contract OR cloud OR regulator OR investigation OR \"EU Commission\" OR losses OR margin)",
            "(Cerebras OR CoreWeave OR DeepSeek OR Moonshot AI) (IPO OR funding OR valuation OR contract OR demand OR customer OR margin)",
        ],
        "direct": [],
    },
    "Hyperscaler CAPEX": {
        "queries": [
            "(Microsoft OR Amazon OR Google OR Meta OR Apple OR Oracle) (\"data center\" OR \"data centre\" OR \"AI infrastructure\") (capex OR investment OR build OR campus OR power OR renewable OR PPA OR MW OR GW OR delay OR cancelled)",
            "(Microsoft OR Amazon OR Google OR Meta OR Apple OR Oracle) (\"cloud contract\" OR \"AI infrastructure\" OR \"data center power\" OR \"capacity reservation\" OR \"contract loss\")",
        ],
        "direct": [],
    },
    "Supply Chain": {
        "queries": [
            "(TSMC OR ASML OR Nvidia OR Broadcom OR AMD OR Cerebras) (supply OR shortage OR demand OR order OR IPO OR valuation)",
            "(HBM OR \"advanced packaging\" OR CoWoS OR \"SK Hynix\" OR Samsung) (capacity OR shortage OR bottleneck OR supply)",
        ],
        "direct": ["DatacenterDynamics", "The Register DC"],
    },
    "Model Releases": {
        "queries": [
            "(GPT OR Claude OR Gemini OR Llama OR DeepSeek) (\"price cut\" OR pricing OR cheaper OR efficiency OR benchmark OR \"model release\")",
            "AI benchmark (MMLU OR GPQA OR \"SWE-bench\") (frontier OR cost OR efficiency OR plateau)",
        ],
        "direct": [],
    },
    "ANZ DC": {
        "queries": [
            "(\"CDC Data Centres\" OR NEXTDC OR AirTrunk OR \"Keppel Data Centres\" OR \"Stack Infrastructure\" OR \"Macquarie Data Centres\" OR Fujitsu OR \"Goodman Group\" OR \"Vantage Data Centers\" OR \"Doma Infrastructure Group\" OR Equinix OR \"DigiCo Infrastructure REIT\" OR \"Telstra InfraCo\" OR \"Leading Edge Data Centres\" OR NCI) (\"data centre\" OR \"data center\" OR hyperscale OR campus OR MW OR power OR capacity OR AI)",
            "(NextDC OR NXT.AX OR \"CDC Data Centres\" OR AirTrunk OR \"DigiCo Infrastructure REIT\") (earnings OR results OR guidance OR shares OR stock OR acquisition OR investment OR valuation OR contract OR customer)",
            "(Infratil OR IFT.NZ OR \"Macquarie Group\" OR MQG.AX OR \"Goodman Group\" OR GMG.AX) (\"data centre\" OR \"data center\" OR CDC OR hyperscale OR campus OR MW OR power OR capacity)",
            "(NextDC OR AirTrunk OR CDC OR Infratil OR Macquarie OR Goodman) \"data centre\" (Australia OR \"New Zealand\") (capacity OR MW OR campus OR investment OR power OR contract)",
            "\"data centre\" (Australia OR \"New Zealand\") (MW OR power OR renewable OR campus OR hyperscale)",
        ],
        "direct": [],
    },
    "China / Export Controls": {
        "queries": [
            "China AI chip export controls Nvidia Huawei SMIC",
            "(Huawei OR DeepSeek OR SMIC) (AI chip OR export controls OR sanctions OR GPU)",
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
        source = _entry_source(entry, source_fallback)
        if is_blocked_news_source(source):
            continue
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=source,
                published=_parse_published(entry),
                summary=getattr(entry, "summary", "")[:300],
            )
        )
    return items


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news_buckets(max_per_bucket: int = 30) -> dict[str, list[dict]]:
    """Fetch all configured buckets. Returns bucket_label -> list of item dicts.

    Returns dicts (not NewsItem objects) because Streamlit's cache serializes output.
    """
    result: dict[str, list[dict]] = {}
    for label, cfg in BUCKETS.items():
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        items: list[NewsItem] = []

        for query in cfg.get("queries", []):
            url = _gn_url(query)
            for item in _fetch_feed(url, source_fallback="Google News"):
                if label == "ANZ DC" and not is_anz_operator_news(item.title, item.summary):
                    continue
                title_key = normalise_event_key(item.title)
                if item.url in seen_urls or title_key in seen_titles:
                    continue
                seen_urls.add(item.url)
                seen_titles.add(title_key)
                items.append(item)

        for direct_name in cfg.get("direct", []):
            feed_url = DIRECT_FEEDS.get(direct_name)
            if not feed_url:
                continue
            for item in _fetch_feed(feed_url, source_fallback=direct_name):
                if label == "ANZ DC" and not is_anz_operator_news(item.title, item.summary):
                    continue
                title_key = normalise_event_key(item.title)
                if item.url in seen_urls or title_key in seen_titles:
                    continue
                seen_urls.add(item.url)
                seen_titles.add(title_key)
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
                "materiality_score": score_news_item(
                    title=it.title,
                    summary=it.summary,
                    source=it.source,
                    published=it.published,
                ),
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
