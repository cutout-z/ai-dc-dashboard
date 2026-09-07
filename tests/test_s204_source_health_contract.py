"""S2-04 (B4) verification: explicit source-health result contract.

Covers the Astra review requirements:
- freshness from embedded observation dates, not mtime (a file rewritten
  moments ago whose newest row is months old reports very-stale);
- expected-input inventory: an absent file is reported `missing` even
  though directory scans can't see absences, with role-appropriate
  severity (data/enrichment -> error, intermediate/derived -> degraded);
- unreadable payloads and missing required columns are hard failures;
- future-dated embedded values (forecast targets) are not freshness evidence;
- CLI `--check` audit mode: exit 0 on ok/degraded, 2 on error
  (deploy/run-vps-*.sh treat >=2 as fatal); default runs stay exit 0;
- run_result contract: final_status vocabulary and write_log_record's
  last_attempt/last_success preservation;
- the Streamlit view module imports and renders under a stub (no server).

All filesystem state lives in per-test temp dirs (configure_roots);
no test writes to the repository.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import scripts.source_health_report as shr  # noqa: E402
from app.lib import run_result  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────
TODAY = datetime.now().strftime("%Y-%m-%d")
NOW_ISO = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
DAYS_AGO = lambda n: (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731

EXPECTED_SUBSET = [
    {"name": "sp500_pe.csv", "subdir": "reference", "role": "data", "required": ["date", "trailing_pe"]},
    {"name": "funding_deals.csv", "subdir": "reference", "role": "data", "required": ["date", "entity", "source"]},
    {"name": "capex_guidance.csv", "subdir": "reference", "role": "enrichment", "required": ["ticker", "guidance_usd_b", "guidance_date"]},
    {"name": "consensus.json", "subdir": "reference", "role": "enrichment", "required": ["updated", "data"]},
    {"name": "news_catalog.csv", "subdir": "reference", "role": "intermediate", "required": ["catalog_key", "title", "source", "published"]},
    {"name": "financials_history.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["date", "ticker"]},
    {"name": "spot_check.json", "subdir": "au_dc/processed", "role": "diagnostic", "required": ["run_at", "summary"]},
    {"name": "stale_guidance.json", "subdir": "data", "role": "derived", "required": ["checked_at", "stale_tickers"]},
]


def _write_csv(path: Path, columns: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


@pytest.fixture()
def fresh_tree(tmp_path, monkeypatch):
    """A minimal healthy checkout: every fixture source present and current."""
    ref = tmp_path / "data" / "reference"
    proc = tmp_path / "data" / "au_dc" / "processed"
    datadir = tmp_path / "data"

    _write_csv(ref / "sp500_pe.csv", ["date", "trailing_pe", "source"],
               [[DAYS_AGO(1), 25.1, "multpl"], [TODAY, 25.2, "multpl"]])
    _write_csv(ref / "funding_deals.csv", ["date", "entity", "amount_bn", "type", "source"],
               [[TODAY, "Anthropic", 13.0, "primary", "press"]])
    _write_csv(ref / "capex_guidance.csv",
               ["ticker", "company", "fiscal_year", "guidance_usd_b", "guidance_date", "source"],
               [["MSFT", "Microsoft", 2026, 120.0, TODAY, "earnings call"]])
    _write_json(ref / "consensus.json", {"updated": NOW_ISO, "source": "yfinance", "data": {"MSFT": {}}})
    _write_csv(ref / "news_catalog.csv",
               ["catalog_key", "title", "source", "published"],
               [["k1", "headline", "reuters", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")]])
    proc.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": [pd.Timestamp.now()], "ticker": ["MSFT"]}).to_parquet(proc / "financials_history.parquet", index=False)
    _write_json(proc / "spot_check.json", {"run_at": NOW_ISO, "project_count": 42, "summary": {"errors": 0, "warnings": 0, "ok": 5}})
    _write_json(datadir / "stale_guidance.json", {"checked_at": NOW_ISO, "stale_tickers": [], "fresh_tickers": ["MSFT"]})

    monkeypatch.setattr(shr, "EXPECTED_FILES", [dict(e) for e in EXPECTED_SUBSET])
    shr.configure_roots(tmp_path)
    yield tmp_path
    shr.configure_roots(REPO_ROOT)


def _expected(tree: Path, name: str) -> dict:
    report = shr.build_report()
    for entry in report["expected_inputs"]:
        if entry["source"].endswith(name):
            return entry
    raise AssertionError(f"{name} not in expected inventory")


# ────────────────────────────────────────────────────────────────────
# Embedded-date freshness vs mtime
# ────────────────────────────────────────────────────────────────────
def test_healthy_tree_is_ok(fresh_tree):
    report = shr.build_report()
    assert report["overall_status"] == "ok"
    assert report["counts"]["missing"] == 0
    assert report["counts"]["unreadable"] == 0


def test_stale_data_detects_embedded_date_not_mtime(fresh_tree):
    """The review's core complaint: mtime says fresh, data says very-stale."""
    ref = fresh_tree / "data" / "reference"
    _write_csv(ref / "funding_deals.csv", ["date", "entity", "amount_bn", "type", "source"],
               [[DAYS_AGO(400), "OldCo", 1.0, "primary", "press"]])  # rewritten just now
    report = shr.build_report()
    row = next(r for r in report["reference_files"] if r["source"].endswith("funding_deals.csv"))
    assert row["status"] == "very-stale"
    assert row["date_basis"] == "embedded"
    assert row["age_days"] >= 399
    assert report["overall_status"] == "error"  # very-stale on a scanned source


def test_stale_embedded_date_is_degraded_exit_zero(fresh_tree):
    ref = fresh_tree / "data" / "reference"
    _write_csv(ref / "sp500_pe.csv", ["date", "trailing_pe", "source"],
               [[DAYS_AGO(40), 25.0, "multpl"]])  # threshold 30d -> stale, not very-stale
    report = shr.build_report()
    row = next(r for r in report["reference_files"] if r["source"].endswith("sp500_pe.csv"))
    assert row["status"] == "stale"
    assert report["overall_status"] == "degraded"
    assert shr.main(["--check"]) == 0


def test_json_key_observation_dates(fresh_tree):
    """consensus 'updated' and llm _meta.updated drive freshness, not mtime."""
    ref = fresh_tree / "data" / "reference"
    _write_json(ref / "consensus.json",
                {"updated": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "source": "yfinance", "data": {}})
    report = shr.build_report()
    row = next(r for r in report["reference_files"] if r["source"].endswith("consensus.json"))
    assert row["status"] == "very-stale"  # threshold 7d; 30d-old embedded date
    assert row["date_basis"] == "embedded"


def test_future_embedded_date_is_not_freshness_evidence(fresh_tree):
    """Forecast-target years (e.g. 2032) must not green a file."""
    proc = fresh_tree / "data" / "au_dc" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": [pd.Timestamp("2032-01-01")], "ticker": ["MSFT"]}).to_parquet(
        proc / "financials_history.parquet", index=False)
    report = shr.build_report()
    row = next(r for r in report["au_dc_files"] if r["source"].endswith("financials_history.parquet"))
    assert "future embedded date" in row["date_basis"]
    assert "not evidence of freshness" in (row.get("detail") or "")


# ────────────────────────────────────────────────────────────────────
# Expected-input inventory
# ────────────────────────────────────────────────────────────────────
def test_missing_expected_file_is_reported(fresh_tree):
    """Absent files must surface even though directory scans can't see them."""
    (fresh_tree / "data" / "reference" / "consensus.json").unlink()
    entry = _expected(fresh_tree, "consensus.json")
    assert entry["status"] == "missing"
    report = shr.build_report()
    assert report["overall_status"] == "error"  # enrichment role -> hard


def test_missing_intermediate_is_degraded_not_error(fresh_tree):
    (fresh_tree / "data" / "reference" / "news_catalog.csv").unlink()
    entry = _expected(fresh_tree, "news_catalog.csv")
    assert entry["status"] == "missing"
    report = shr.build_report()
    assert report["overall_status"] == "degraded"


def test_missing_derived_reports_expected_before_first_run(fresh_tree):
    (fresh_tree / "data" / "stale_guidance.json").unlink()
    entry = _expected(fresh_tree, "stale_guidance.json")
    assert entry["status"] == "missing"
    assert "expected before first run" in (entry.get("detail") or "")
    report = shr.build_report()
    assert report["overall_status"] == "degraded"


def test_existing_out_of_tree_derived_file_not_false_missing(fresh_tree):
    """data/ files are not scanned by directory walks but exist -> must not
    be reported missing (regression for the on-demand scan)."""
    entry = _expected(fresh_tree, "stale_guidance.json")
    assert entry["status"] != "missing"


def test_unreadable_payload_is_error(fresh_tree):
    ref = fresh_tree / "data" / "reference"
    (ref / "consensus.json").write_bytes(b"\x00\x01not json")
    entry = _expected(fresh_tree, "consensus.json")
    assert entry["status"] == "unreadable"
    assert shr.build_report()["overall_status"] == "error"


def test_missing_required_column_is_unexpected_format(fresh_tree):
    ref = fresh_tree / "data" / "reference"
    _write_csv(ref / "capex_guidance.csv",
               ["ticker", "company", "fiscal_year", "guidance_usd_b", "source"],
               [["MSFT", "Microsoft", 2026, 120.0, "call"]])  # guidance_date dropped
    entry = _expected(fresh_tree, "capex_guidance.csv")
    assert entry["status"] == "unexpected-format"
    assert "guidance_date" in (entry.get("detail") or "")
    assert shr.build_report()["overall_status"] == "error"


def test_fetcher_error_blocks_overall_ok(fresh_tree):
    """A producer-recorded error means the pipeline is not plain 'ok'."""
    _write_json(fresh_tree / "data" / "fetcher_log.json",
                {"refresh_capex_guidance.py": {"status": "error", "last_attempt": NOW_ISO,
                                               "notes": "total lookup failure"}})
    report = shr.build_report()
    assert report["fetcher_errors"]
    assert report["overall_status"] == "degraded"


# ────────────────────────────────────────────────────────────────────
# CLI contract
# ────────────────────────────────────────────────────────────────────
def test_cli_check_exit_2_on_missing_expected(fresh_tree, capsys):
    (fresh_tree / "data" / "reference" / "funding_deals.csv").unlink()
    rc = shr.main(["--check"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "funding_deals.csv" in out
    assert out.startswith("source-health: ERROR")


def test_cli_check_exit_0_when_ok(fresh_tree):
    assert shr.main(["--check"]) == 0


def test_cli_default_markdown_exits_zero_despite_stale(fresh_tree):
    """Plain runs (as the VPS wrappers invoke them) never hard-error."""
    ref = fresh_tree / "data" / "reference"
    _write_csv(ref / "funding_deals.csv", ["date", "entity", "amount_bn", "type", "source"],
               [[DAYS_AGO(400), "OldCo", 1.0, "primary", "press"]])
    assert shr.main([]) == 0  # markdown to stdout, rc 0


def test_cli_out_dir_writes_report_files(fresh_tree, tmp_path):
    out = tmp_path / "reports"
    rc = shr.main(["--json", "--out-dir", str(out)])
    assert rc == 0
    json_files = list(out.glob("source-health-*.json"))
    md_files = list(out.glob("source-health-*.md"))
    assert json_files and md_files
    payload = json.loads(json_files[0].read_text())
    assert payload["schema_version"] == 2
    assert payload["overall_status"] in {"ok", "degraded", "error"}
    assert set(payload["counts"]) == {"fresh", "stale", "very_stale", "missing", "unreadable", "no_date"}
    assert "Overall:" in md_files[0].read_text()


def test_cli_check_truncates_long_problem_lists(fresh_tree, capsys):
    ref = fresh_tree / "data" / "reference"
    for name in ("sp500_pe.csv", "funding_deals.csv", "capex_guidance.csv",
                 "consensus.json", "news_catalog.csv"):
        (ref / name).unlink()
    (fresh_tree / "data" / "au_dc" / "processed" / "financials_history.parquet").unlink()
    rc = shr.main(["--check"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "(+0 more)" not in out  # <=12 problems: no ellipsis suffix


# ────────────────────────────────────────────────────────────────────
# run_result contract (shared by B4 producers)
# ────────────────────────────────────────────────────────────────────
def test_final_status_vocabulary():
    assert run_result.final_status(3, 3) == "ok"
    assert run_result.final_status(1, 3) == "degraded"
    assert run_result.final_status(0, 3) == "error"
    assert run_result.final_status(0, 0) == "error"  # nothing attempted is never ok


def test_write_log_record_preserves_last_success(tmp_path):
    log = tmp_path / "fetcher_log.json"
    run_result.write_log_record(log, "s.py", status="ok", attempted=2, succeeded=2)
    first = run_result.read_log_record(log, "s.py")
    assert first["status"] == "ok"
    assert first["last_success"] == first["last_attempt"]

    run_result.write_log_record(log, "s.py", status="error", attempted=2, succeeded=0, notes="outage")
    second = run_result.read_log_record(log, "s.py")
    assert second["last_attempt"] >= first["last_attempt"]  # attempt advanced
    assert second["last_success"] == first["last_success"]  # success preserved
    assert second["last_run"] == second["last_attempt"]     # legacy key in sync
    assert "count" not in second


def test_write_log_record_keeps_other_scripts(tmp_path):
    log = tmp_path / "fetcher_log.json"
    run_result.write_log_record(log, "a.py", status="ok", attempted=1, succeeded=1)
    run_result.write_log_record(log, "b.py", status="degraded", attempted=2, succeeded=1)
    assert run_result.read_log_record(log, "a.py")["status"] == "ok"
    assert run_result.read_log_record(log, "b.py")["status"] == "degraded"


# ────────────────────────────────────────────────────────────────────
# View renders under a Streamlit stub (offline)
# ────────────────────────────────────────────────────────────────────
@pytest.fixture()
def streamlit_stub(monkeypatch):
    calls: list[tuple[str, object]] = []

    class _El:
        def __getattr__(self, name):
            def _record(*a, **k):
                calls.append((name, a))
                return None
            return _record

        def __call__(self, *a, **k):  # e.g. st.columns(...)[i] usage safe
            return _SelfCols()

    class _SelfCols:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def metric(self, *a, **k):
            calls.append(("metric", a))
        def markdown(self, *a, **k):
            calls.append(("markdown", a))

    stub = types.ModuleType("streamlit")

    def _any_call(*a, **k):
        calls.append((a[0] if a else "", a))
        return None

    stub.title = lambda *a, **k: calls.append(("title", a))
    stub.caption = lambda *a, **k: calls.append(("caption", a))
    stub.header = lambda *a, **k: calls.append(("header", a))
    stub.error = lambda *a, **k: calls.append(("error", a))
    stub.warning = lambda *a, **k: calls.append(("warning", a))
    stub.info = lambda *a, **k: calls.append(("info", a))
    stub.dataframe = lambda *a, **k: calls.append(("dataframe", a))
    stub.metric = lambda *a, **k: calls.append(("metric", a))
    stub.markdown = lambda *a, **k: calls.append(("markdown", a))
    stub.write = lambda *a, **k: calls.append(("write", a))
    stub.expander = lambda *a, **k: _SelfCols()
    stub.columns = lambda n, **k: [_SelfCols() for _ in range(n)]
    stub.session_state = {"db_path": str(REPO_ROOT / "data" / "db" / "ai_research.db")}
    stub.cache_data = lambda *a, **k: (lambda f: f)
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    return calls


def test_view_imports_and_renders_with_stub(fresh_tree, streamlit_stub, monkeypatch):
    """The source-health view executes end-to-end offline: inventory banner
    runs, tables render, and the inventory never takes the page down."""
    monkeypatch.delitem(sys.modules, "app.views.system.source_health", raising=False)
    monkeypatch.setitem(sys.modules, "app.lib.news", _FakeNewsModule())
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    import app.views.system.source_health as view  # noqa: F401

    names = [c[0] for c in streamlit_stub]
    assert "title" in names
    assert "header" in names
    # healthy fixture: no inventory banner expected
    assert "error" not in names

    # Now break an expected file -> banner must appear
    (fresh_tree / "data" / "reference" / "consensus.json").unlink()
    monkeypatch.delitem(sys.modules, "app.views.system.source_health", raising=False)
    importlib.import_module("app.views.system.source_health")
    names2 = [c[0] for c in streamlit_stub]
    assert "error" in names2


class _FakeNewsModule:
    """Stand-in for app.lib.news so the view's news section runs offline."""

    @staticmethod
    def fetch_news_source_health():
        return [{"bucket": "test", "item_count": 3, "latest": NOW_ISO}]
