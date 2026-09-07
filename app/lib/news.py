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
from urllib.parse import urlunsplit, urlsplit
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timezone

import feedparser
import requests
import streamlit as st

from app.lib.news_scoring import get_display_tier, score_news_item

logger = logging.getLogger("ai_research.news")

# ──────────────────────────────────────────────
# Bucket definitions
# ──────────────────────────────────────────────
# Each bucket = (label, list of Google News queries, list of direct feed URLs)

GN_BASE = "https://news.google.com/rss/search"


def _format_query_date(value: str | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _gn_url(
    query: str,
    gl: str = "US",
    hl: str = "en-US",
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> str:
    start = _format_query_date(start_date)
    end = _format_query_date(end_date)
    dated_query = query
    if start:
        dated_query = f"{dated_query} after:{start}"
    if end:
        dated_query = f"{dated_query} before:{end}"
    params = {"q": query, "hl": hl, "gl": gl, "ceid": f"{gl}:{hl.split('-')[0]}"}
    params["q"] = dated_query
    return f"{GN_BASE}?{urllib.parse.urlencode(params)}"


# Direct DC-specific feeds
DIRECT_FEEDS = {
    "DatacenterDynamics": "https://www.datacenterdynamics.com/en/rss/",
    "The Register On-Prem": (
        "https://api.theregister.com/api/v1/article?"
        "limit=25&orderBy=published&query=tag%3Aon_prem&remapper=rss&site_id=2"
    ),
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


# Query parameters that do not identify the article and are stripped when
# normalising a URL into an article-identity key (S2-09). `oc` is the Google
# News RSS display parameter — the article token lives in the path (CBMi...),
# never in this query value.
_TRACKING_PARAMS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "oc", "ref", "ref_src",
    "cmp", "igshid", "hsCtaTracking", "_hsenc", "_hsmi", "vero_conv",
    "vero_id", "wt_mc", "yclid", "msclkid",
}


def normalise_url(url: str) -> str:
    """Normalise a source URL into a stable article-identity key (S2-09).

    Declared normalisation:
      - strip surrounding whitespace and any URL fragment;
      - lowercase the scheme and host, drop default ports (:80 / :443);
      - drop known tracking/click parameters (``utm_*`` plus
        :data:`_TRACKING_PARAMS`) so click-tagged variants of one article
        collapse to one identity;
      - sort remaining query parameters by name for byte-stable output;
      - collapse duplicate slashes in the path and drop any trailing slash
        (a bare origin therefore collapses to an empty path);
      - otherwise preserve the path and remaining query exactly — Google News
        RSS article tokens (``/rss/articles/CBMi...``) are path data and are
        identity.

    Empty / whitespace-only input returns ``""``.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        # Not an absolute http(s) URL — leave it untouched rather than guess.
        return raw
    try:
        port = parts.port
    except ValueError:
        port = None
    if port in (80, 443):
        port = None
    netloc = host
    if port is not None:
        netloc = f"{host}:{port}"
    path = re.sub(r"/+", "/", parts.path or "")
    if path.endswith("/"):
        path = path[:-1]
    kept = []
    if parts.query:
        for param in sorted(parts.query.split("&")):
            if not param:
                continue
            name = param.partition("=")[0].lower()
            if name.startswith("utm_") or name in _TRACKING_PARAMS:
                continue
            kept.append(param)
    query = "&".join(kept)
    rebuilt = urlunsplit((scheme, netloc, path, query, ""))
    return rebuilt


def article_identity_key(url: str, title: str = "") -> str:
    """Primary article identity = normalised source URL, with a declared fallback.

    Article rows are keyed by :func:`normalise_url` of the source URL (S2-09).
    When no usable URL is present the fallback is explicit and inspectable —
    ``title:<normalised-title-key>`` — never an opaque hash. The ``title:``
    prefix cannot collide with a real URL identity.
    """
    normalised = normalise_url(url)
    if normalised:
        return normalised
    return f"title:{normalise_title_key(title)}"


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
        "direct": ["DatacenterDynamics", "The Register On-Prem"],
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


def _fetch_feed(
    url: str,
    source_fallback: str,
    *,
    stats: dict | None = None,
    failed_label: str | None = None,
) -> list[NewsItem]:
    """Fetch one feed URL.

    When ``stats`` is given, the attempt is counted (attempted/succeeded);
    a failed feed is appended to ``stats["failed_feeds"]`` using
    ``failed_label`` (defaulting to the source fallback name).
    """
    if stats is not None:
        stats["attempted"] += 1
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as e:
        logger.warning("feedparser error for %s: %s", url, e)
        if stats is not None:
            stats["failed_feeds"].append(failed_label or source_fallback)
            return []
        return []
    if stats is not None:
        stats["succeeded"] += 1

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


def _date_to_datetime(value: str | date | None, *, end_of_day: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        t = datetime_time.max if end_of_day else datetime_time.min
        return datetime.combine(value, t, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(str(value)), datetime_time.min, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _in_date_window(
    published: datetime | None,
    start_date: str | date | None,
    end_date: str | date | None,
) -> bool:
    if published is None:
        return start_date is None and end_date is None
    start = _date_to_datetime(start_date)
    end = _date_to_datetime(end_date)
    published_utc = published.astimezone(timezone.utc)
    if start and published_utc.date() < start.date():
        return False
    if end and published_utc.date() >= end.date():
        return False
    return True


def _fetch_news_buckets_uncached(
    max_per_bucket: int,
    start_date,
    end_date,
    stats: dict | None,
) -> dict[str, list[dict]]:
    """Live fetch of all configured buckets (no caching).

    ``stats``, when given, is filled with feed-request level results —
    attempted/succeeded counts plus per-feed failure labels — giving the
    catalogue producer the S2-04 attempted/succeeded contract.
    """
    result: dict[str, list[dict]] = {}
    for label, cfg in BUCKETS.items():
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        items: list[NewsItem] = []

        for query in cfg.get("queries", []):
            url = _gn_url(query, start_date=start_date, end_date=end_date)
            for item in _fetch_feed(
                url,
                source_fallback="Google News",
                stats=stats,
                failed_label=f"google_news:{query}",
            ):
                if not _in_date_window(item.published, start_date, end_date):
                    continue
                if label == "ANZ DC" and not is_anz_operator_news(item.title, item.summary):
                    continue
                title_key = normalise_title_key(item.title)
                url_key = normalise_url(item.url)
                if url_key in seen_urls or title_key in seen_titles:
                    continue
                seen_urls.add(url_key)
                seen_titles.add(title_key)
                items.append(item)

        for direct_name in cfg.get("direct", []):
            feed_url = DIRECT_FEEDS.get(direct_name)
            if not feed_url:
                continue
            for item in _fetch_feed(
                feed_url,
                source_fallback=direct_name,
                stats=stats,
                failed_label=f"direct:{direct_name}",
            ):
                if not _in_date_window(item.published, start_date, end_date):
                    continue
                if label == "ANZ DC" and not is_anz_operator_news(item.title, item.summary):
                    continue
                title_key = normalise_title_key(item.title)
                url_key = normalise_url(item.url)
                if url_key in seen_urls or title_key in seen_titles:
                    continue
                seen_urls.add(url_key)
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


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news_buckets(
    max_per_bucket: int = 30,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> dict[str, list[dict]]:
    """Fetch all configured buckets. Returns bucket_label -> list of item dicts.

    Cached wrapper around :func:`_fetch_news_buckets_uncached`. Producer
    scripts that need per-feed attempted/succeeded stats call the uncached
    core directly with a ``stats`` dict.
    Returns dicts (not NewsItem objects) because Streamlit's cache serializes output.
    """
    return _fetch_news_buckets_uncached(max_per_bucket, start_date, end_date, None)


def fetch_stats_summary(stats: dict) -> str:
    """One-line human summary of a feed-stats dict (S2-04 contract)."""
    attempted = stats.get("attempted", 0)
    succeeded = stats.get("succeeded", 0)
    failed = stats.get("failed_feeds", [])
    base = f"{succeeded}/{attempted} feed requests succeeded"
    if failed:
        shown = ", ".join(failed[:5])
        more = f" (+{len(failed) - 5} more)" if len(failed) > 5 else ""
        return f"{base}; failed: {shown}{more}"
    return base


def flatten_news_buckets(news_data: dict[str, list[dict]]) -> list[dict]:
    """Flatten bucketed news into one deduped, display-tiered feed.

    Article identity is the normalised source URL (S2-09); the same headline
    served from multiple URLs (syndication) is collapsed in the live feed by
    exact normalised-title match only — never by broad event/company class.
    Each emitted item carries its ``url_key`` (article identity) for the
    durable catalog to key on.
    """
    all_items: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for bucket_label, items in news_data.items():
        for item in items:
            title_key = normalise_title_key(item["title"])
            url_key = normalise_url(item["url"])
            if url_key in seen_urls or title_key in seen_titles:
                continue
            if url_key:
                seen_urls.add(url_key)
            seen_titles.add(title_key)
            all_items.append({
                **item,
                "bucket": bucket_label,
                "url_key": url_key,
                "tier": get_display_tier(item, bucket_label),
            })

    all_items.sort(
        key=lambda x: (x.get("materiality_score", 0), x.get("published") or ""),
        reverse=True,
    )
    return all_items


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
