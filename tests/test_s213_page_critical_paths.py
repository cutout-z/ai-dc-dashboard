"""S2-13 (C15) verification: page critical paths in ai-research.

Review reproductions (astra-review-2026-09-04 S2-13):
- cold News page issued 17 SEQUENTIAL feed requests (15 s timeout each) after
  18 sequential Yahoo earnings lookups, with committed history rendered below
  all of that network work — a stalled feed could hide stored history for
  minutes;
- the Risk Monitor called the full equities loader (one 14-symbol 10y spark
  call PLUS 14 fundamental jobs) although breadth only consumes returns and
  52-week drawdowns.

After the fix (verify criteria):
- feed fetches are bounded-concurrent (<= FEED_MAX_WORKERS in flight) with
  shared per-thread sessions, and per-bucket output + feed stats are
  deterministic in config order regardless of completion order;
- an all-feeds-down or partially-failed run is visible in stats
  (attempted/succeeded/failed_feeds) and never fabricates items; page-level
  committed history rendering is covered by the AppTest script
  (tests/test_s213_pages_apptest.py);
- breadth has a price-only loader: one spark call, ZERO fundamental jobs,
  same-snapshot returns/drawdowns, and the signal reproduces from the loader;
- live Yahoo earnings are bounded-concurrent and an explicit opt-in; the
  committed earnings snapshot reader touches no network.
"""
from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.lib import news as news_lib  # noqa: E402
from app.lib.equities import (  # noqa: E402
    MAG7_AI_STOCKS,
    committed_earnings_newest_date,
    fetch_committed_earnings_dates,
    fetch_earnings_dates,
)
from app.lib.news import (  # noqa: E402
    BUCKETS,
    DIRECT_FEEDS,
    FEED_MAX_WORKERS,
    NewsItem,
    _fetch_news_buckets_uncached,
)
from app.lib.yahoo_spark import (  # noqa: E402
    _format_price,
    compute_pct_from_high,
    compute_returns_from_closes,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# ────────────────────────────────────────────────────────────────────────────
# Feed-fetch harness: deterministic fake _fetch_feed with concurrency tracking
# ────────────────────────────────────────────────────────────────────────────

def _config_feed_labels() -> list[str]:
    """Feed labels in config order (queries then directs per bucket)."""
    labels: list[str] = []
    for label, cfg in BUCKETS.items():
        for query in cfg.get("queries", []):
            labels.append(f"google_news:{query}")
        for direct_name in cfg.get("direct", []):
            if direct_name in DIRECT_FEEDS:
                labels.append(f"direct:{direct_name}")
    return labels


FEED_LABELS = _config_feed_labels()


def _items_for(feed_label: str, n: int = 3, url_base: str = "https://ex.example") -> list[NewsItem]:
    safe = re.sub(r"[^A-Za-z0-9]+", "-", feed_label).strip("-")[:40]
    return [
        NewsItem(
            title=f"{feed_label} headline {j}",
            url=f"{url_base}/{safe}/{j}",
            source=f"Source-{safe}-{j}",
            published=datetime(2026, 8, 30, 0, 0, j, tzinfo=timezone.utc),
            summary=f"summary {feed_label} {j}",
        )
        for j in range(n)
    ]


class FeedHarness:
    """Fake news_lib._fetch_feed. Per-label delay/fail/override control."""

    def __init__(
        self,
        *,
        fail: set[str] | None = None,
        delays: dict[str, float] | None = None,
        overrides: dict[str, list[NewsItem]] | None = None,
        item_count: int = 3,
    ) -> None:
        self.fail = set(fail or [])
        self.delays = delays or {}
        self.overrides = overrides or {}
        self.item_count = item_count
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def __call__(self, url, source_fallback, *, stats=None, failed_label=None) -> list[NewsItem]:
        label = failed_label or source_fallback or url
        with self._lock:
            self.calls.append(label)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            delay = self.delays.get(label, 0.0)
            if delay:
                time.sleep(delay)
            if stats is not None:
                stats["attempted"] += 1
            if label in self.fail:
                if stats is not None:
                    stats["failed_feeds"].append(label)
                return []
            if stats is not None:
                stats["succeeded"] += 1
            return self.overrides.get(label) or _items_for(label, self.item_count)
        finally:
            with self._lock:
                self.active -= 1


def _bucket_urls(data: dict[str, list[dict]]) -> dict[str, list[str]]:
    return {label: [it["url"] for it in items] for label, items in data.items()}


# ────────────────────────────────────────────────────────────────────────────
# 1. Feed fetch: inventory, bounded concurrency, deterministic output
# ────────────────────────────────────────────────────────────────────────────

def test_feed_inventory_matches_review_count():
    # Review: 17 sequential feed requests on a cold News page.
    assert len(FEED_LABELS) == 17
    assert len(set(FEED_LABELS)) == 17


def test_feed_fetch_is_bounded_concurrent(monkeypatch):
    harness = FeedHarness(delays={label: 0.02 for label in FEED_LABELS})
    monkeypatch.setattr(news_lib, "_fetch_feed", harness)

    stats = {"attempted": 0, "succeeded": 0, "failed_feeds": []}
    result = _fetch_news_buckets_uncached(30, None, None, stats)

    assert len(harness.calls) == 17
    assert 2 <= harness.max_active <= FEED_MAX_WORKERS, harness.max_active
    assert stats == {"attempted": 17, "succeeded": 17, "failed_feeds": []}
    assert set(result) == set(BUCKETS)
    assert all(len(items) > 0 for items in result.values())
    # Every configured feed contributed items.
    assert sum(len(items) for items in result.values()) >= 17


def test_feed_output_independent_of_completion_order(monkeypatch):
    # First-configured feeds finish LAST in run A, FIRST in run B. Output must
    # be byte-identical because assembly runs in config order.
    n = len(FEED_LABELS)

    def _run(reverse: bool) -> dict:
        delays = {
            label: 0.001 * (n - i if not reverse else i)
            for i, label in enumerate(FEED_LABELS)
        }
        harness = FeedHarness(delays=delays)
        monkeypatch.setattr(news_lib, "_fetch_feed", harness)
        return _fetch_news_buckets_uncached(30, None, None, None)

    monkeypatch.setattr(news_lib, "_fetch_feed", FeedHarness())  # reset spy
    a = _run(reverse=False)
    b = _run(reverse=True)
    assert a == b


def test_feed_dedupe_deterministic_first_config_feed_wins(monkeypatch):
    # Same bucket, two feeds (the first two configured feeds are Frontier
    # Labs' two Google News queries): feed 1 echoes feed 0's article (same URL
    # + same title). The URL/title dedupe must keep the FIRST config-order
    # copy and drop the echo.
    first, second = FEED_LABELS[0], FEED_LABELS[1]
    assert first.startswith("google_news:") and second.startswith("google_news:")
    shared = NewsItem(
        title="Duplicated across feeds",
        url="https://ex.example/shared-article",
        source="Source-A",
        published=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    only_b = _items_for(second, 2)
    harness = FeedHarness(overrides={first: [shared], second: [shared, *only_b]})
    monkeypatch.setattr(news_lib, "_fetch_feed", harness)

    result = _fetch_news_buckets_uncached(30, None, None, None)
    frontier = next(
        items for label, items in result.items() if label == "Frontier Labs"
    )
    urls = [it["url"] for it in frontier]
    assert urls.count("https://ex.example/shared-article") == 1
    dup = [it for it in frontier if it["url"] == "https://ex.example/shared-article"]
    assert dup[0]["source"] == "Source-A"  # first config-order copy won


def test_all_feeds_down_empty_buckets_exact_stats(monkeypatch):
    # A fully stalled feed run cannot fabricate items; stats are exact and the
    # failure labels are recorded in deterministic config order.
    harness = FeedHarness(fail=set(FEED_LABELS), delays={lbl: 0.001 for lbl in FEED_LABELS})
    monkeypatch.setattr(news_lib, "_fetch_feed", harness)

    stats = {"attempted": 0, "succeeded": 0, "failed_feeds": []}
    result = _fetch_news_buckets_uncached(30, None, None, stats)

    assert stats["attempted"] == 17
    assert stats["succeeded"] == 0
    assert stats["failed_feeds"] == FEED_LABELS  # config order, deterministic
    assert all(items == [] for items in result.values())


def test_partial_feed_failure_stats_visible(monkeypatch):
    fail_labels = [FEED_LABELS[1], FEED_LABELS[2], FEED_LABELS[10]]
    # Reverse delays so a failed feed would finish first — labels must still
    # be recorded in config order.
    n = len(FEED_LABELS)
    delays = {label: 0.001 * (n - i) for i, label in enumerate(FEED_LABELS)}
    harness = FeedHarness(fail=set(fail_labels), delays=delays)
    monkeypatch.setattr(news_lib, "_fetch_feed", harness)

    stats = {"attempted": 0, "succeeded": 0, "failed_feeds": []}
    result = _fetch_news_buckets_uncached(30, None, None, stats)

    assert stats["attempted"] == 17
    assert stats["succeeded"] == 14
    assert stats["failed_feeds"] == fail_labels  # config order regardless of finish order
    # Successful feeds still produced items; no feed is silently missing.
    assert sum(len(items) for items in result.values()) >= 14


def test_with_stats_wrapper_returns_data_and_stats(monkeypatch):
    fake_data = {"A": [{"title": "t", "url": "https://ex.example/1", "source": "s",
                        "published": "2026-09-01T00:00:00+00:00", "published_str": "",
                        "age_str": "", "summary": "", "materiality_score": 0.0}]}
    invoked = {"n": 0}

    def _fake_uncached(max_per_bucket, start_date, end_date, stats=None):
        invoked["n"] += 1
        if stats is not None:
            stats["attempted"] = 1
            stats["succeeded"] = 1
        return fake_data

    monkeypatch.setattr(news_lib, "_fetch_news_buckets_uncached", _fake_uncached)
    news_lib.fetch_news_buckets_with_stats.clear()
    data, stats = news_lib.fetch_news_buckets_with_stats()
    assert invoked["n"] == 1  # wrapper executed the (stubbed) fetch, not a stale cache
    assert data == fake_data
    assert stats == {"attempted": 1, "succeeded": 1, "failed_feeds": []}


# ────────────────────────────────────────────────────────────────────────────
# 2. Price-only breadth loader (no fundamental calls)
# ────────────────────────────────────────────────────────────────────────────

MAG_SYMBOLS = [s["symbol"] for s in MAG7_AI_STOCKS]


def _normal_closes(n: int = 320, base: float = 100.0, slope: float = 0.05) -> list[float]:
    return [round(base + slope * i, 4) for i in range(n)]


def _droop_closes(n: int = 320, peak: float = 200.0, tail: float = 150.0) -> list[float]:
    """Rise to ``peak`` by index 260, then ease down to ``tail`` — the peak
    sits inside the trailing 252-close 52-week window, so last is ~25% below
    the 52-week high close."""
    out: list[float] = []
    for i in range(n):
        if i <= 260:
            out.append(100.0 + (peak - 100.0) * i / 260.0)
        else:
            out.append(peak + (tail - peak) * (i - 260.0) / (n - 260.0))
    return [round(v, 4) for v in out]


def _spark_fixture(closes_by_symbol: dict[str, list[float]]) -> dict:
    out = {}
    for sym in MAG_SYMBOLS:
        closes = closes_by_symbol.get(sym, _normal_closes())
        out[sym] = {"closes": closes, "timestamps": list(range(len(closes))),
                    "chart_prev_close": None}
    return out


def _breadth_rows(closes_by_symbol=None) -> list[dict]:
    """Pure-builder rows (the cached wrapper is exercised under the AppTest
    runtime, where st.cache_data is coherent)."""
    import app.lib.equities as eq
    return eq._breadth_rows_from_spark(_spark_fixture(closes_by_symbol or {}))


def test_breadth_loader_makes_no_fundamental_calls(monkeypatch):
    import app.lib.equities as eq

    boom = {"called": False}

    def _explode(*a, **k):
        boom["called"] = True
        raise AssertionError("fundamental fetch must never run on the breadth path")

    # Guard the builder itself: even if someone later adds a network call into
    # it, both the spark fetch and the fundamental fetch are tripped.
    monkeypatch.setattr(eq, "run_spark", _explode)
    monkeypatch.setattr(eq, "_fetch_fundamentals", _explode)

    rows = _breadth_rows()

    assert boom["called"] is False
    assert len(rows) == len(MAG7_AI_STOCKS)
    # No fundamental-only keys anywhere.
    forbidden = {"market_cap", "pe_trailing", "pe_forward", "eps_trailing",
                 "eps_forward", "week52_low", "week52_high", "target_mean_1y",
                 "rev_growth_yoy", "capex_yoy"}
    assert not any(forbidden & set(row) for row in rows)


def test_breadth_loader_same_snapshot_price_formulas():
    closes_by = {sym: _normal_closes(slope=0.1) for sym in MAG_SYMBOLS}
    rows = {row["symbol"]: row for row in _breadth_rows(closes_by)}

    for sym in MAG_SYMBOLS:
        closes = closes_by[sym]
        row = rows[sym]
        assert row["returns"] == compute_returns_from_closes(closes)
        assert row["pct_from_high"] == compute_pct_from_high(closes)
        assert row["price"] == _format_price(closes[-1])
        prev = closes[-2]
        assert row["change_pct"] == round((closes[-1] / prev - 1) * 100, 2)


def test_breadth_loader_rows_are_deterministic():
    closes_by = {sym: _normal_closes(slope=0.1) for sym in MAG_SYMBOLS}
    assert _breadth_rows(closes_by) == _breadth_rows(closes_by)


def test_breadth_signal_reproduces_from_loader():
    from app.lib.dc_risk_signals import market_breadth_signal

    closes_by = {sym: _normal_closes() for sym in MAG_SYMBOLS}
    closes_by["EQIX"] = _droop_closes()
    closes_by["DLR"] = _droop_closes()

    rows = _breadth_rows(closes_by)
    sig = market_breadth_signal(rows)

    assert sig.name == "Market breadth"
    assert sig.status == "red"  # two DC operators >20% below the 52w high close
    assert any("more than 20% below" in ev for ev in sig.evidence)

    # Single deep drawdown -> amber (not red).
    closes_by2 = {sym: _normal_closes() for sym in MAG_SYMBOLS}
    closes_by2["EQIX"] = _droop_closes()
    sig_amber = market_breadth_signal(_breadth_rows(closes_by2))
    assert sig_amber.status == "amber"

    # No deep drawdowns -> green.
    sig_green = market_breadth_signal(_breadth_rows())
    assert sig_green.status == "green"


def test_breadth_loader_empty_snapshot_is_gray():
    from app.lib.dc_risk_signals import market_breadth_signal

    rows = _breadth_rows({sym: [] for sym in MAG_SYMBOLS})  # spark has no closes
    assert len(rows) == len(MAG7_AI_STOCKS)
    assert all(row["returns"] == {} and row["pct_from_high"] is None for row in rows)
    sig = market_breadth_signal(rows)
    assert sig.status == "gray"  # metadata-only rows can never read green


# ────────────────────────────────────────────────────────────────────────────
# 3. Earnings: committed snapshot (no network) + bounded live opt-in
# ────────────────────────────────────────────────────────────────────────────

def test_committed_earnings_snapshot_is_no_network_reader(monkeypatch):
    snapshot = {"MSFT": "2026-10-28", "NXT.AX": "2026-08-26", "AAPL": None}
    monkeypatch.setattr("app.lib.equities._load_earnings_fallback", lambda: snapshot)
    fetch_committed_earnings_dates.clear()
    assert fetch_committed_earnings_dates() == snapshot


def test_committed_earnings_newest_date_is_content_derived():
    assert committed_earnings_newest_date(
        {"MSFT": "2026-10-28", "NXT.AX": None, "AAPL": "2026-07-31"}
    ) == "2026-10-28"
    assert committed_earnings_newest_date({"MSFT": None}) is None
    assert committed_earnings_newest_date({}) is None
    # Never an mtime claim: only the snapshot's own dates count.
    assert committed_earnings_newest_date({"MSFT": "garbage"}) is None


def test_live_earnings_is_bounded_concurrent(monkeypatch):
    syms = tuple(MAG_SYMBOLS[:8])
    lock = threading.Lock()
    state = {"active": 0, "max_active": 0}

    def _fake_one(sym):
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.02)
        with lock:
            state["active"] -= 1
        return sym, "2026-10-15"

    monkeypatch.setattr("app.lib.equities._fetch_one_earnings_date", _fake_one)
    monkeypatch.setattr("app.lib.equities._load_earnings_fallback", lambda: {})
    fetch_earnings_dates.clear()
    results = fetch_earnings_dates(syms)
    assert results == {s: "2026-10-15" for s in syms}
    assert 2 <= state["max_active"] <= 6, state["max_active"]


def test_live_earnings_falls_back_to_committed_per_ticker(monkeypatch):
    syms = ("MSFT", "NXT.AX")
    monkeypatch.setattr("app.lib.equities._fetch_one_earnings_date",
                        lambda s: (s, None))  # Yahoo returns nothing
    fallback = {"MSFT": "2026-10-28", "NXT.AX": "2026-08-26"}
    monkeypatch.setattr("app.lib.equities._load_earnings_fallback", lambda: fallback)
    fetch_earnings_dates.clear()
    results = fetch_earnings_dates(syms)
    assert results == {"MSFT": "2026-10-28", "NXT.AX": "2026-08-26"}
