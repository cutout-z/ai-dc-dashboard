"""S2-03 (B3) verification: partial financial fetch cannot erase last-good history.

Covers the Astra review reproductions and verify list:
- partial outage (MSFT succeeds, every other ticker fails) -> publication
  aborts, the previous 285-row series is preserved untouched;
- all-endpoints-empty (with and without seed data) -> abort, not silent wipe;
- a valid upsert replaces only the keys the candidate covers and keeps
  last-good rows the candidate does not mention;
- correction of a prior period updates values in place (no row growth);
- one failed endpoint blocks publication even when the rest of the candidate
  is data-rich (a failed endpoint is not a deletion instruction);
- explicitly declared new listings are allowed;
- a fresh empty DB is created with table + views.

All database state is in-memory SQLite copied (read-only) from the real DB.
No test writes to the repository or to the production database file.
"""

from __future__ import annotations

import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import scripts.fetch_financials as ff  # noqa: E402

REAL_DB = REPO_ROOT / "data" / "db" / "ai_research.db"

COLUMNS = [
    "ticker", "company", "period", "metric", "frequency",
    "value", "unit", "source", "fetched_at",
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _fixture_conn() -> sqlite3.Connection:
    """In-memory copy of the real production DB (read via a read-only handle)."""
    src = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(":memory:")
    src.backup(dst)
    src.close()
    return dst


def _snapshot(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT ticker, period, metric, frequency, value, source, fetched_at "
        "FROM quarterly_financials ORDER BY ticker, metric, frequency, period"
    ).fetchall()


def _group_counts(conn: sqlite3.Connection) -> dict[tuple, int]:
    rows = conn.execute(
        "SELECT ticker, metric, frequency, COUNT(*) FROM quarterly_financials "
        "GROUP BY 1, 2, 3"
    ).fetchall()
    return {tuple(r[:3]): r[3] for r in rows}


def _dup_keys(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT ticker, period, metric, frequency, COUNT(*) c "
        "FROM quarterly_financials GROUP BY 1, 2, 3, 4 HAVING c > 1"
    ).fetchall()


def _row(ticker: str, period: str, metric: str, frequency: str, value: float) -> dict:
    return {
        "ticker": ticker,
        "company": ff.ALL_TICKERS.get(ticker, ticker),
        "period": period,
        "metric": metric,
        "frequency": frequency,
        "value": value,
        "unit": ff.REPORTING_CURRENCY.get(ticker, "USD"),
        "source": "yahoo_finance",
        "fetched_at": datetime.now().isoformat(),
    }


def _stub_fetch(monkeypatch, behaviour):
    """Replace fetch_quarterly_financials with a scripted fake.

    ``behaviour(ticker, on_error) -> list[dict]`` returns rows or raises.
    """
    def fake(ticker, name, on_error=None):
        return behaviour(ticker, on_error)

    monkeypatch.setattr(ff, "fetch_quarterly_financials", fake)


def _raise_for(tickers_fail: set[str], rows_builder):
    """Behaviour: failing tickers report via on_error; others use builder."""
    def behaviour(ticker, on_error):
        if ticker in tickers_fail:
            if on_error is not None:
                on_error(f"{ticker}: all endpoints failed (simulated outage)")
            return []
        return rows_builder(ticker)

    return behaviour


# ── review reproduction: partial outage must fail closed ────────────────────

def test_partial_outage_preserves_history_and_aborts(monkeypatch) -> None:
    """285-row DB + only MSFT reachable -> abort, old series byte-identical."""
    conn = _fixture_conn()
    before = _snapshot(conn)
    assert len(before) == 285, "fixture must mirror the real 285-row DB"

    # MSFT candidate = exactly its current stored rows (an "exact" fetch).
    msft_rows = [
        dict(zip(COLUMNS, row))
        for row in conn.execute(
            "SELECT ticker, company, period, metric, frequency, value, unit, "
            "source, fetched_at FROM quarterly_financials WHERE ticker='MSFT'"
        ).fetchall()
    ]
    _stub_fetch(monkeypatch, _raise_for(
        set(ff.ALL_TICKERS) - {"MSFT"},
        lambda t: msft_rows,
    ))

    with pytest.raises(ff.PublishValidationError) as excinfo:
        ff.run(conn=conn)

    assert any("MSFT" not in p for p in excinfo.value.problems), (
        "non-MSFT failures must be reported as problems"
    )
    assert _snapshot(conn) == before, "partial failure must leave the DB untouched"
    assert sum(_group_counts(conn).values()) == 285
    conn.close()


def test_all_endpoints_empty_no_seeds_aborts(monkeypatch) -> None:
    """Every endpoint returns empty, seeds absent -> empty-candidate abort."""
    conn = _fixture_conn()
    before = _snapshot(conn)
    monkeypatch.setattr(ff, "_load_seed_data", lambda: pd.DataFrame())
    _stub_fetch(monkeypatch, lambda t, on_error: [])

    with pytest.raises(ff.PublishValidationError) as excinfo:
        ff.run(conn=conn)

    assert any("empty" in p for p in excinfo.value.problems)
    assert _snapshot(conn) == before
    conn.close()


def test_all_endpoints_empty_with_seeds_aborts(monkeypatch) -> None:
    """APIs silently empty (no errors reported), seed fills only its slice ->
    every non-seed series 'vanishes' -> abort, not a silent 285->126 wipe."""
    conn = _fixture_conn()
    before = _snapshot(conn)
    _stub_fetch(monkeypatch, lambda t, on_error: [])

    with pytest.raises(ff.PublishValidationError) as excinfo:
        ff.run(conn=conn)

    vanished = [p for p in excinfo.value.problems if "vanished" in p]
    assert vanished, "silently empty endpoints must be caught by the vanished-series check"
    assert _snapshot(conn) == before
    conn.close()


def test_single_failed_endpoint_blocks_publication(monkeypatch) -> None:
    """Data-rich candidate but ONE ticker down -> degraded abort (fail closed)."""
    conn = _fixture_conn()

    def full_series(ticker: str) -> list[dict]:
        rows = conn.execute(
            "SELECT period, metric, frequency FROM quarterly_financials "
            "WHERE ticker=?",
            (ticker,),
        ).fetchall()
        return [
            _row(ticker, period, metric, frequency, 1000.0)
            for period, metric, frequency in rows
        ]

    failing = "AAPL"
    _stub_fetch(monkeypatch, _raise_for(
        {failing},
        full_series,
    ))

    with pytest.raises(ff.PublishValidationError) as excinfo:
        ff.run(conn=conn)
    assert any(failing in p for p in excinfo.value.problems)

    # The untouched fixture baseline is intact (this test's own connection).
    assert sum(_group_counts(conn).values()) == 285
    conn.close()


# ── valid approvals: upsert semantics ────────────────────────────────────────

def test_valid_upsert_keeps_last_good_rows_not_covered(monkeypatch) -> None:
    """Candidate covers the newest ~60% of each series: those rows update,
    the older rows survive untouched, row count is unchanged, no dup keys."""
    conn = _fixture_conn()

    def partial_series(ticker: str) -> list[dict]:
        rows = conn.execute(
            "SELECT period, metric, frequency FROM quarterly_financials "
            "WHERE ticker=? ORDER BY period",
            (ticker,),
        ).fetchall()
        out = []
        for metric, frequency in {(m, f) for _, m, f in rows}:
            group = sorted(p for p, m, f in rows if (m, f) == (metric, frequency))
            keep = group[-max(1, math.ceil(len(group) * 0.6)):]
            out.extend(_row(ticker, p, metric, frequency, 999.0) for p in keep)
        return out

    _stub_fetch(monkeypatch, _raise_for(set(), partial_series))

    result = ff.run(conn=conn)
    assert result["status"] == "ok"

    total = conn.execute("SELECT COUNT(*) FROM quarterly_financials").fetchone()[0]
    assert total == 285, "upsert must not grow or shrink the table"
    assert _dup_keys(conn) == []

    updated = conn.execute(
        "SELECT COUNT(*) FROM quarterly_financials WHERE value=999.0"
    ).fetchone()[0]
    preserved = conn.execute(
        "SELECT COUNT(*) FROM quarterly_financials WHERE value<>999.0"
    ).fetchone()[0]
    assert updated > 0, "candidate rows must replace their keys"
    assert preserved > 0, "last-good rows not covered by the candidate must survive"

    # Per-series arithmetic: updated + preserved == previous count.
    counts = _group_counts(conn)
    conn2_updated = conn.execute(
        "SELECT ticker, metric, frequency, COUNT(*) FROM quarterly_financials "
        "WHERE value=999.0 GROUP BY 1,2,3"
    ).fetchall()
    for ticker, metric, frequency, n in conn2_updated:
        assert n < counts[(ticker, metric, frequency)], (
            "a partial candidate must not erase the uncovered tail of a series"
        )
    conn.close()


def test_correction_of_prior_period_updates_in_place(monkeypatch) -> None:
    """Full-coverage candidate with corrected values: same 285 rows, values
    shifted by +1, reader views recreated on the publish connection."""
    conn = _fixture_conn()
    before = {
        (t, p, m, f): v
        for t, p, m, f, v, *_ in conn.execute(
            "SELECT ticker, period, metric, frequency, value FROM quarterly_financials"
        ).fetchall()
    }

    def corrected_series(ticker: str) -> list[dict]:
        rows = conn.execute(
            "SELECT period, metric, frequency FROM quarterly_financials WHERE ticker=?",
            (ticker,),
        ).fetchall()
        return [
            _row(ticker, period, metric, frequency, before[(ticker, period, metric, frequency)] + 1.0)
            for period, metric, frequency in rows
        ]

    _stub_fetch(monkeypatch, _raise_for(set(), corrected_series))

    result = ff.run(conn=conn)
    assert result["status"] == "ok"
    assert result["rows"] == 285

    total = conn.execute("SELECT COUNT(*) FROM quarterly_financials").fetchone()[0]
    assert total == 285, "corrections must update in place, not append"
    assert _dup_keys(conn) == []

    shifted = conn.execute(
        "SELECT ticker, period, metric, frequency, value FROM quarterly_financials"
    ).fetchall()
    for ticker, period, metric, frequency, value in shifted:
        assert value == pytest.approx(before[(ticker, period, metric, frequency)] + 1.0)

    # Views exist and return rows (recreated on the publish connection).
    view_rows = conn.execute("SELECT COUNT(*) FROM v_hyperscaler_capex").fetchone()[0]
    assert view_rows > 0
    semi_rows = conn.execute("SELECT COUNT(*) FROM v_semi_revenue").fetchone()[0]
    assert semi_rows > 0
    conn.close()


def test_declared_new_listing_is_allowed(monkeypatch) -> None:
    """A ticker declared in ALL_TICKERS (the declaration mechanism) joins the
    table without tripping the completeness gate (only existing series are
    validated against their previous row counts)."""
    conn = _fixture_conn()

    def series_with_newcomer(ticker: str) -> list[dict]:
        rows = conn.execute(
            "SELECT period, metric, frequency FROM quarterly_financials WHERE ticker=?",
            (ticker,),
        ).fetchall()
        return [
            _row(ticker, period, metric, frequency, 1000.0)
            for period, metric, frequency in rows
        ]

    def behaviour(ticker, on_error):
        if ticker == "NBIS":
            # Valid quarter-end dates.
            return [_row("NBIS", f"2026-{month}-30", "capex", "quarterly", 5.0e8)
                    for month in ("03", "06", "09", "12")]
        return series_with_newcomer(ticker)

    _stub_fetch(monkeypatch, behaviour)
    monkeypatch.setattr(
        ff, "ALL_TICKERS", {**ff.ALL_TICKERS, "NBIS": "Nebius"}
    )

    result = ff.run(conn=conn)
    assert result["status"] == "ok"
    total = conn.execute("SELECT COUNT(*) FROM quarterly_financials").fetchone()[0]
    assert total == 285 + 4
    nbis = conn.execute(
        "SELECT COUNT(*) FROM quarterly_financials WHERE ticker='NBIS'"
    ).fetchone()[0]
    assert nbis == 4
    conn.close()


def test_fresh_empty_db_gets_table_and_views(monkeypatch) -> None:
    """First run on an empty DB creates the table and reader views."""
    conn = sqlite3.connect(":memory:")

    def small_series(ticker: str) -> list[dict]:
        return [
            _row(ticker, f"2026-0{q}-30", metric, "quarterly", 100.0 * q)
            for q in (1, 2, 3)
            for metric in ("capex", "revenue")
        ]

    _stub_fetch(monkeypatch, _raise_for(set(), small_series))
    monkeypatch.setattr(ff, "_load_seed_data", lambda: pd.DataFrame())

    result = ff.run(conn=conn)
    assert result["status"] == "ok"
    # 10 tracked tickers x 3 quarters x 2 metrics.
    assert result["rows"] == 60
    assert _dup_keys(conn) == []
    # The capex view covers the 7 CAPEX_COMPANIES x 3 quarters.
    assert conn.execute("SELECT COUNT(*) FROM v_hyperscaler_capex").fetchone()[0] == 21
    conn.close()


# ── fetch-level on_error wiring ──────────────────────────────────────────────

def test_fetch_reports_endpoint_failures_via_on_error(monkeypatch) -> None:
    """Endpoint exceptions reach the on_error callback instead of being
    silently printed; no partial rows are returned."""

    class BoomTicker:
        def __init__(self, ticker: str) -> None:
            pass

        @property
        def quarterly_cashflow(self):  # noqa: ANN201
            raise RuntimeError("boom quarterly cashflow")

        @property
        def quarterly_income_stmt(self):  # noqa: ANN201
            raise RuntimeError("boom quarterly income")

        @property
        def cashflow(self):  # noqa: ANN201
            raise RuntimeError("boom annual cashflow")

        @property
        def income_stmt(self):  # noqa: ANN201
            raise RuntimeError("boom annual income")

    monkeypatch.setattr(ff.yf, "Ticker", BoomTicker)

    failures: list[str] = []
    records = ff.fetch_quarterly_financials("MSFT", "Microsoft", on_error=failures.append)
    assert records == []
    assert len(failures) == 4, "each of the four endpoints must report its failure"
    assert all("MSFT" in m for m in failures)

    # Legacy mode (no callback): still must not raise.
    records_legacy = ff.fetch_quarterly_financials("MSFT", "Microsoft")
    assert records_legacy == []
