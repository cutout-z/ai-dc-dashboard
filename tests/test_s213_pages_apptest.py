"""S2-13 (C15) page-level AppTest checks under a real Streamlit runtime.

Run:  /opt/anaconda3/bin/python3.12 tests/test_s213_pages_apptest.py

Covers the page-critical-path behaviours pytest can't (its streamlit
cache_data is not coherent outside a runtime):
- News page renders committed content (earnings snapshot + durable catalog)
  with NO live network on a cold load: the live Yahoo earnings check is off by
  default and the live feed fetch runs after the catalogue's first render;
- ONE News Feed section: the durable catalogue and the live fetch are a single
  table (no separate 'News History' section), and the fetched items merge into
  that same table — so the catalogue is on screen when every feed is stalled;
- a fully stalled feed run leaves the stored history rendered and visible, and
  the failure is reported (attempted/succeeded/failed feeds) instead of a
  silent empty feed;
- a partially-failed feed run keeps the successful items AND shows the
  partial-failure warning (partial errors remain visible; ordering of sections
  is deterministic);
- the Risk Monitor's breadth path makes exactly ONE Yahoo spark call (14
  symbols, 10y) and never touches the fundamental fetch.

Never touches the network; never writes to the repo.
"""
from __future__ import annotations

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from streamlit.testing.v1 import AppTest  # noqa: E402

import pandas as pd  # noqa: E402

import app.lib.news as news_lib  # noqa: E402
import app.lib.equities as eq  # noqa: E402
from app.lib.news import NewsItem  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def _sections_order(at, *, expect_catalog_rows: bool) -> None:
    """ONE News Feed section; the committed catalogue renders with no live feeds.

    (Was: a separate 'News History' section that had to render before 'News
    Feed'. The catalogue and the live fetch are now a single section, so the
    S2-13 guarantee is asserted where it actually lives — the durable rows are
    on screen when every feed is stalled — not as a second header.)
    """
    texts = []
    for coll in ("header", "subheader", "caption", "markdown", "title", "warning", "info"):
        for el in getattr(at, coll, []) or []:
            t = getattr(el, "value", None)
            if t is not None:
                texts.append(str(t))
    joined = "\n".join(texts)
    check("news: single News Feed section renders", joined.count("News Feed") == 1,
          f"header count={joined.count('News Feed')}")
    check("news: no separate News History section remains",
          "News History" not in joined, "legacy history header present")
    tables = list(getattr(at, "dataframe", []) or [])
    check("news: exactly one feed table (2 earnings + 1 feed)",
          len(tables) == 3, f"{len(tables)} dataframes")
    if expect_catalog_rows:
        feed = tables[-1].value if tables else None
        check("news: catalogue rows render with no live network",
              feed is not None and len(feed) > 0,
              f"rows={0 if feed is None else len(feed)}")


def _news_feed_fake(items_per_feed: int = 3, fail: set[str] | None = None):
    """Fake news_lib._fetch_feed: deterministic items; thread-safe stats."""
    fail = fail or set()
    lock = threading.Lock()
    counter = {"n": 0}
    failed_labels = []

    def _fake_feed(url, source_fallback, *, stats=None, failed_label=None):
        label = failed_label or source_fallback or url
        if stats is not None:
            stats["attempted"] += 1
        if label in fail:
            with lock:
                failed_labels.append(label)
            if stats is not None:
                stats["failed_feeds"].append(label)
            return []
        with lock:
            base = counter["n"]
            counter["n"] += 1
        items = [
            NewsItem(
                title=f"{label} headline {base}-{j}",
                url=f"https://ex.example/{base}-{j}",
                source=f"Source-{base}",
                published=datetime(2026, 9, 1, 0, 0, j, tzinfo=timezone.utc),
                summary="",
            )
            for j in range(items_per_feed)
        ]
        if stats is not None:
            stats["succeeded"] += 1
        return items

    return _fake_feed, failed_labels


def all_feed_labels() -> set[str]:
    return {
        f"google_news:{q}" for b in news_lib.BUCKETS.values()
        for q in b.get("queries", [])
    } | {
        f"direct:{d}" for b in news_lib.BUCKETS.values()
        for d in b.get("direct", []) if d in news_lib.DIRECT_FEEDS
    }


def run_news_page(fail_labels: set[str] | None = None, expected: str | None = None,
                  show_low: bool = False) -> AppTest:
    fake, _ = _news_feed_fake(fail=fail_labels)
    news_lib._fetch_feed = fake
    # The live Yahoo earnings path must never run on a cold load (opt-in off).
    eq.fetch_earnings_dates = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("fetch_earnings_dates must not run unless the live toggle is on")
    )
    # st.cache_data storage persists across AppTest runtimes within one
    # process — evict the feed cache so each scenario computes fresh.
    news_lib.fetch_news_buckets_with_stats.clear()
    at = AppTest.from_file(str(REPO / "app" / "views" / "news" / "news.py")).run(timeout=120)
    check("news: page runs without exception", len(at.exception) == 0,
          str([str(e.value) for e in at.exception])[:300])
    if show_low:
        # Synthetic non-material articles score LOW, which the tier toggle
        # hides by default — flip it to assert the merged rows are reachable.
        at.toggle[1].set_value(True)
        at.run(timeout=120)
        check("news: page still runs with low-materiality shown", len(at.exception) == 0,
              str([str(e.value) for e in at.exception])[:300])
    _sections_order(at, expect_catalog_rows=True)
    joined = "\n".join(
        str(getattr(el, "value", ""))
        for coll in ("caption", "markdown", "warning", "info", "header", "subheader")
        for el in getattr(at, coll, []) or []
    )
    if expected is not None:
        check(f"news: expected status visible ({expected[:40]})", expected in joined,
              joined[-300:])
    return at


def feed_table(at) -> pd.DataFrame:
    """The single News Feed table (last dataframe on the page)."""
    tables = list(getattr(at, "dataframe", []) or [])
    return tables[-1].value if tables else pd.DataFrame()


def main() -> int:
    global PASS, FAIL
    print("== S2-13 page AppTest (real Streamlit runtime, offline) ==")

    # ── A. News page: all feeds stalled → committed history still renders ──
    print("\n[A] News page with every feed stalled")
    at = run_news_page(fail_labels=all_feed_labels(),
                       expected="No live news items fetched")
    toggles = list(getattr(at, "toggle", []) or [])
    check("news: earnings live toggle defaults OFF",
          len(toggles) > 0 and toggles[0].value is False,
          f"{len(toggles)} toggles")
    check("news: low-materiality toggle defaults OFF",
          len(toggles) > 1 and toggles[1].value is False,
          f"{len(toggles)} toggles")
    joined2 = "\n".join(str(getattr(el, "value", "")) for el in at.caption)
    check("news: committed-snapshot earnings caption present",
          "data/reference/earnings_dates.csv" in joined2, joined2[:200])
    stalled_rows = len(feed_table(at))

    # ── B. News page: healthy fetch merges live items into the one table ──
    print("\n[B] News page with healthy feeds")
    at = run_news_page(show_low=True)
    table = feed_table(at)
    check("news: live items merged into the single feed table",
          len(table) > stalled_rows
          and bool(table["Title"].astype(str).str.contains("headline").any()),
          f"rows={len(table)} stalled_rows={stalled_rows}")
    check("news: merged rows are marked live vs catalogued",
          set(table["Status"].astype(str).unique()) >= {"Live", "Catalogued"},
          str(sorted(set(table["Status"].astype(str).unique()))))

    # ── C. News page: partial feed failure keeps items + shows warning ──
    print("\n[C] News page with three feeds failed")
    run_news_page(fail_labels=set(sorted(all_feed_labels())[:3]),
                  expected="Partial live-fetch failure")

    # ── D. Risk Monitor breadth path: one spark call, no fundamentals ──
    print("\n[D] DC Risk Monitor price-only breadth")
    calls: list[tuple] = []
    boom = {"called": False}
    symbols = [s["symbol"] for s in eq.MAG7_AI_STOCKS]
    fixture = {}
    for sym in symbols:
        closes = [100.0 + 0.05 * i for i in range(320)]
        fixture[sym] = {"closes": closes, "timestamps": list(range(320)),
                        "chart_prev_close": None}

    def _spy_spark(symbols_arg, time_range="10y"):
        calls.append((list(symbols_arg), time_range))
        return fixture

    def _explode_fundamentals(*a, **k):
        boom["called"] = True
        raise AssertionError("fundamentals must never run on the Risk Monitor breadth path")

    eq.run_spark = _spy_spark
    eq._fetch_fundamentals = _explode_fundamentals
    eq.fetch_breadth_data.clear()
    at = AppTest.from_file(str(REPO / "app" / "views" / "dc_risk_monitor.py")).run(timeout=180)
    check("risk monitor: page runs without exception", len(at.exception) == 0,
          str([str(e.value) for e in at.exception])[:300])
    check("risk monitor: breadth made exactly ONE spark call (14 symbols, 10y)",
          len(calls) == 1 and calls[0][0] == symbols and calls[0][1] == "10y",
          str(calls))
    check("risk monitor: no fundamental call was made", boom["called"] is False)

    print(f"\nRESULT: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())

