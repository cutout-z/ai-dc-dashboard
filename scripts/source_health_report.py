"""CLI source-health report for AI & DC Dashboard automation (Astra S2-04).

Result contract
---------------
Every file-level source gets an explicit status derived from *embedded
observation dates* (never file mtime — mtime says "file was touched", not
"data is current"):

    fresh / stale / very-stale   — observation age vs per-source thresholds
    missing                      — expected source absent from disk
    unreadable                   — exists but could not be parsed

An expected-input inventory (EXPECTED_FILES) lists every file the pipelines
and dashboards consume, with the required columns/keys per role, so an
absent file is reported instead of silently skipped by a directory scan.

Overall status (overall_status) aggregates to the same vocabulary used by
the shared run-result contract (app/lib/run_result.py):

    ok        — every source readable and observation-current
    degraded  — some stale/very-stale sources, nothing hard-broken
    error     — any missing/unreadable source, or any very-stale source
                whose observation date is evidence (data/enrichment role)

CLI
---
    python scripts/source_health_report.py                 # markdown to stdout
    python scripts/source_health_report.py --json          # JSON to stdout
    python scripts/source_health_report.py --out-dir DIR   # write .md + .json
    python scripts/source_health_report.py --check         # audit mode

``--check`` prints one summary line and exits 0 on ok/degraded, >=2 on
error — matching the ``deploy/run-vps-*.sh`` audit convention (wrappers run
``set -euo pipefail`` and treat exit >= 2 as fatal).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Allowed statuses
HEALTHY = {"fresh"}
DEGRADED = {"stale", "very-stale"}
UNHEALTHY = {"missing", "unreadable"}

# Overall contract vocabulary (mirrors app/lib/run_result.py)
OVERALL_OK = "ok"
OVERALL_DEGRADED = "degraded"
OVERALL_ERROR = "error"


class Roots(NamedTuple):
    project: Path
    reference: Path
    au_dc: Path
    data: Path

    @classmethod
    def under(cls, project_root: Path) -> "Roots":
        return cls(
            project=project_root,
            reference=project_root / "data" / "reference",
            au_dc=project_root / "data" / "au_dc",
            data=project_root / "data",
        )


_ROOTS = Roots.under(PROJECT_ROOT)


def configure_roots(project_root: Path) -> Roots:
    """Point the report at an alternate checkout (tests use temp dirs)."""
    global _ROOTS
    _ROOTS = Roots.under(project_root)
    return _ROOTS


def _roots() -> Roots:
    return _ROOTS


# ────────────────────────────────────────────────────────────────────
# Embedded-observation-date inventory
#
# For each known source: which column(s)/key(s) carry the observation
# (the "as of" of the *data*), and which format. Files not listed are
# still scanned; they fall back to mtime with the default threshold.
# ────────────────────────────────────────────────────────────────────
OBSERVED_DATE_COLS: dict[str, dict[str, Any]] = {
    # name -> {"col": str, "format": fmt} | {"cols": (a, b), "format": "year_month_pair"}
    #     | {"key": str} for JSON
    "sp500_pe.csv": {"col": "date", "format": "date"},
    "token_prices_history.csv": {"col": "date", "format": "date"},
    "funding_deals.csv": {"col": "date", "format": "date"},
    "earnings_dates.csv": {"col": "earnings_date", "format": "date"},
    "dc_power_sourcing.csv": {"col": "announced_date", "format": "date"},
    "dc_power_supply.csv": {"col": "published_date", "format": "date"},
    "dc_queue_metrics.csv": {"col": "published_date", "format": "date"},
    "us_gdp_annual.csv": {"col": "year", "format": "year"},
    "h100_rental_prices.csv": {"col": "month", "format": "month"},
    "bubble_benchmarks.csv": {"col": "period", "format": "period"},
    "capex_guidance.csv": {"col": "guidance_date", "format": "date"},
    "capex_guidance_history.csv": {"col": "announced_date", "format": "date"},
    "capex_quarterly_seed.csv": {"col": "period", "format": "period"},
    "model_releases.csv": {"col": "release_date", "format": "date"},
    "news_catalog.csv": {"col": "published", "format": "datetime"},
    "tsmc_monthly_revenue.csv": {"cols": ("year", "month"), "format": "year_month_pair"},
    "token_consumption.csv": {"col": "date", "format": "date"},
    "frontier_lab_valuations.csv": {"col": "date", "format": "date"},
    "gpu_lease_prices.csv": {"col": "date", "format": "date"},
    "dc_power_forecasts.csv": {"col": "published_date", "format": "date"},
    "consensus.json": {"key": "updated"},
    "llm_leaderboard.json": {"key_path": ("_meta", "updated")},
    # NB: forecast files (dc_demand, esoo_forecasts — parquet + CSV) carry only
    # *target* years (e.g. 2032), which are not observation dates — they stay
    # on the mtime fallback rather than false-greening on future years.
    "financials_history.parquet": {"col": "date", "format": "datetime"},
    "nem_demand_actual.parquet": {"col": "year_month", "format": "month"},
    "hyperscaler_announcements.csv": {"col": "announcement_date", "format": "date"},
    "operator_aggregate_guidance.csv": {"col": "announcement_date", "format": "date"},
}

# Freshness thresholds in days, keyed by file name (relative across
# reference/ and au_dc). Unlisted files default to 30 days.
FRESH_DAYS = {
    # reference/
    "capex_guidance.csv": 30,
    "capex_guidance_history.csv": 90,
    "capex_quarterly_seed.csv": 90,
    "consensus.json": 7,
    "earnings_dates.csv": 14,
    "funding_deals.csv": 30,
    "llm_leaderboard.json": 30,
    "model_releases.csv": 30,
    "news_catalog.csv": 7,
    "tsmc_monthly_revenue.csv": 15,
    "token_consumption.csv": 60,
    "token_prices_history.csv": 60,
    "frontier_lab_valuations.csv": 60,
    "gpu_lease_prices.csv": 60,
    "h100_rental_prices.csv": 60,
    "sp500_pe.csv": 30,
    "us_gdp_annual.csv": 180,        # annual series, published with lag
    "bubble_benchmarks.csv": 3650,   # historical-era comparisons by design
    "dc_power_forecasts.csv": 180,
    "dc_power_sourcing.csv": 90,
    "dc_power_supply.csv": 180,
    "dc_queue_metrics.csv": 180,
    "ai_supplement.csv": 90,
    # au_dc/processed
    "dc_demand.parquet": 30,
    "esoo_forecasts.parquet": 90,
    "financials_history.parquet": 30,
    "financials_quotes.parquet": 7,
    "generation_info.parquet": 30,
    "grid_capacity.parquet": 30,
    "nem_demand_actual.parquet": 30,
    "projects.parquet": 30,
    "spot_check.json": 30,
    # au_dc/reference
    "projects_seed.csv": 90,
    "dc_demand_forecasts.csv": 180,
    "esoo_forecasts.csv": 180,
    "nem_regions.csv": 365,
    "operator_types.csv": 365,
    "operator_aggregate_guidance.csv": 30,
    "hyperscaler_announcements.csv": 30,
    "hyperscaler_site_leads.csv": 90,
}
DEFAULT_FRESH_DAYS = 30

# ────────────────────────────────────────────────────────────────────
# Expected-input inventory
#
# role:
#   data         — published dataset consumed by dashboards (missing => hard error)
#   enrichment   — ETL-produced cache backing live-fetch fallbacks (missing => hard error)
#   intermediate — rebuildable artifact (missing => reported, not fatal)
#   derived      — written downstream of another file (informational)
#   diagnostic   — health/self-audit output (informational)
# ────────────────────────────────────────────────────────────────────
EXPECTED_FILES: list[dict[str, Any]] = [
    # name, subdir, role, required (columns for tabular / JSON keys)
    {"name": "capex_guidance.csv", "subdir": "reference", "role": "enrichment", "required": ["ticker", "guidance_usd_b", "guidance_date"]},
    {"name": "capex_guidance_history.csv", "subdir": "reference", "role": "data", "required": ["ticker", "guidance_usd_b", "announced_date"]},
    {"name": "capex_quarterly_seed.csv", "subdir": "reference", "role": "data", "required": ["ticker", "period", "capex_usd"]},
    {"name": "consensus.json", "subdir": "reference", "role": "enrichment", "required": ["updated", "data"]},
    {"name": "earnings_dates.csv", "subdir": "reference", "role": "enrichment", "required": ["symbol", "earnings_date"]},
    {"name": "funding_deals.csv", "subdir": "reference", "role": "data", "required": ["date", "entity", "source"]},
    {"name": "llm_leaderboard.json", "subdir": "reference", "role": "enrichment", "required": ["_meta", "models"]},
    {"name": "model_releases.csv", "subdir": "reference", "role": "data", "required": ["release_date", "model"]},
    {"name": "news_catalog.csv", "subdir": "reference", "role": "intermediate", "required": ["catalog_key", "title", "source", "published"],
     "rebuild": "python scripts/catalog_news.py"},
    {"name": "sp500_pe.csv", "subdir": "reference", "role": "data", "required": ["date", "trailing_pe"]},
    {"name": "token_prices_history.csv", "subdir": "reference", "role": "data", "required": ["date", "model", "input_usd_per_mtok"]},
    {"name": "tsmc_monthly_revenue.csv", "subdir": "reference", "role": "data", "required": ["year", "month", "revenue_twd_b"]},
    {"name": "dc_power_forecasts.csv", "subdir": "reference", "role": "data", "required": ["source", "year", "demand_twh"]},
    {"name": "dc_power_sourcing.csv", "subdir": "reference", "role": "data", "required": ["company", "capacity_gw", "announced_date"]},
    {"name": "dc_power_supply.csv", "subdir": "reference", "role": "data", "required": ["region", "year", "supply_twh", "published_date"]},
    {"name": "dc_queue_metrics.csv", "subdir": "reference", "role": "data", "required": ["region", "year", "metric", "value", "published_date"]},
    {"name": "us_gdp_annual.csv", "subdir": "reference", "role": "data", "required": ["year", "gdp_nominal_bn"]},
    {"name": "h100_rental_prices.csv", "subdir": "reference", "role": "data", "required": ["month", "tier", "price_usd_per_gpu_hr"]},
    {"name": "bubble_benchmarks.csv", "subdir": "reference", "role": "data", "required": ["gauge", "benchmark_name", "period"]},
    {"name": "dc_demand.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["year", "scenario", "dc_consumption_twh"]},
    {"name": "esoo_forecasts.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["year", "nem_region", "max_demand_mw"]},
    {"name": "financials_history.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["date", "ticker"]},
    {"name": "financials_quotes.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["ticker", "price", "market_cap"]},
    {"name": "generation_info.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["duid", "nameplate_mw"]},
    {"name": "grid_capacity.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["nem_region", "fuel_category", "capacity_mw"]},
    {"name": "nem_demand_actual.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["nem_region", "year_month", "energy_twh"]},
    {"name": "projects.parquet", "subdir": "au_dc/processed", "role": "data", "required": ["project_name", "nem_region"]},
    {"name": "spot_check.json", "subdir": "au_dc/processed", "role": "diagnostic", "required": ["run_at", "summary"],
     "rebuild": "python etl/au_dc/build_project_db.py"},
    {"name": "projects_seed.csv", "subdir": "au_dc/reference", "role": "data", "required": ["project_name", "status"]},
    {"name": "dc_demand_forecasts.csv", "subdir": "au_dc/reference", "role": "data", "required": ["year", "scenario", "dc_consumption_twh"]},
    {"name": "esoo_forecasts.csv", "subdir": "au_dc/reference", "role": "data", "required": ["year", "nem_region", "max_demand_mw"]},
    {"name": "nem_regions.csv", "subdir": "au_dc/reference", "role": "data", "required": ["nem_region", "state"]},
    {"name": "operator_types.csv", "subdir": "au_dc/reference", "role": "data", "required": ["operator", "operator_type"]},
    {"name": "operator_aggregate_guidance.csv", "subdir": "au_dc/reference", "role": "data", "required": ["operator", "announcement_date"]},
    {"name": "hyperscaler_announcements.csv", "subdir": "au_dc/reference", "role": "data", "required": ["announcement_name", "announcement_date"]},
    {"name": "hyperscaler_site_leads.csv", "subdir": "au_dc/reference", "role": "data", "required": ["site_name", "evidence_tier"]},
    {"name": "stale_guidance.json", "subdir": "data", "role": "derived", "required": ["checked_at", "stale_tickers"]},
]


# ────────────────────────────────────────────────────────────────────
# Observation-date parsing
# ────────────────────────────────────────────────────────────────────
def _parse_observation(value: Any, fmt: str) -> pd.Timestamp | None:
    """Parse one observed-date value; None when absent/unparseable."""
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if fmt == "year_month_pair":
            y, m = value
            return _parse_observation(f"{int(y)}-{int(m):02d}", "month")
        if fmt == "epoch_int":
            return pd.Timestamp.utcfromtimestamp(int(value))  # noqa: TZ003
        ts = pd.to_datetime(str(value).strip(), errors="coerce")
        if pd.isna(ts):
            return None
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts
    except (TypeError, ValueError):
        return None


def _auto_format(value: Any) -> str:
    s = str(value)
    if s.endswith("Z") or ("T" in s and (":" in s.split("T", 1)[1])):
        return "datetime"
    if "T" in s:
        return "date"
    return "date"


def _latest_observation(name: str, path: Path, columns: list[str] | None) -> tuple[pd.Timestamp | None, str | None]:
    """(latest embedded observation, detail) for a known source.

    Returns (None, None) when the file has no registered observation column
    — caller falls back to mtime.
    """
    spec = OBSERVED_DATE_COLS.get(name)
    if spec is None:
        return None, None
    try:
        if "key" in spec or "key_path" in spec:
            data = json.loads(path.read_text())
            if "key" in spec:
                value = data.get(spec["key"])
            else:
                value: Any = data
                for k in spec["key_path"]:
                    if not isinstance(value, dict):
                        return None, None
                    value = value.get(k)
            if value is None:
                return None, "observation key absent"
            return _parse_observation(value, _auto_format(value)), None

        if path.suffix == ".parquet":
            df = pd.read_parquet(path, columns=None)
        else:
            df = pd.read_csv(path, sep=None, engine="python")
        cols = [str(c) for c in df.columns]

        if "cols" in spec:
            a, b = spec["cols"]
            if a not in cols or b not in cols:
                return None, f"columns {a}/{b} absent"
            pairs = df[[a, b]].dropna()
            latest = None
            for y, m in pairs.itertuples(index=False):
                ts = _parse_observation((y, m), "year_month_pair")
                if ts is not None and (latest is None or ts > latest):
                    latest = ts
            return latest, None

        col = spec["col"]
        fmt = spec["format"]
        if col not in cols:
            return None, f"column {col} absent"
        series = df[col].dropna()
        if series.empty:
            return None, "no observation values"
        if fmt == "epoch_int":
            ts = _parse_observation(series.max(), fmt)
            return ts, None
        parsed = (_parse_observation(v, fmt) for v in series)
        stamps = [p for p in parsed if p is not None]
        if not stamps:
            return None, "no parseable observation values"
        return max(stamps), None
    except Exception as exc:  # unreadable payload
        return None, f"{type(exc).__name__}: {exc}"


# ────────────────────────────────────────────────────────────────────
# File scanning
# ────────────────────────────────────────────────────────────────────
def _classify_observation_age(age_days: float | None, fresh_days: int) -> str:
    if age_days is None:
        return "no-date"
    if age_days <= fresh_days:
        return "fresh"
    if age_days <= fresh_days * 3:
        return "stale"
    return "very-stale"


def _mtime_status(path: Path, fresh_days: int) -> str:
    age_days = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 86400
    return _classify_observation_age(age_days, fresh_days)


def _scan_one(path: Path, display: str) -> dict[str, Any]:
    """One file's health row: embedded-date first, mtime fallback."""
    fresh_days = FRESH_DAYS.get(path.name, DEFAULT_FRESH_DAYS)
    row: dict[str, Any] = {
        "source": display,
        "fresh_days": fresh_days,
        "rows": None,
        "latest_observation": None,
        "date_basis": None,
        "detail": None,
    }
    if not path.exists():
        row["status"] = "missing"
        return row
    try:
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
            row["rows"] = len(df)
            columns = [str(c) for c in df.columns]
        elif path.suffix == ".csv":
            df = pd.read_csv(path, sep=None, engine="python")
            row["rows"] = len(df)
            columns = [str(c) for c in df.columns]
        elif path.suffix == ".json":
            data = json.loads(path.read_text())
            columns = None
            if isinstance(data, list):
                row["rows"] = len(data)
            elif isinstance(data, dict):
                if isinstance(data.get("models"), list):
                    row["rows"] = len(data["models"])
                elif isinstance(data.get("data"), dict):
                    row["rows"] = len(data["data"])
                else:
                    row["rows"] = len(data)
        else:
            columns = None
    except Exception as exc:
        row["status"] = "unreadable"
        row["detail"] = f"{type(exc).__name__}: {exc}"
        return row

    latest, detail = _latest_observation(path.name, path, columns)
    if latest is not None:
        age_days = (pd.Timestamp.now() - latest).total_seconds() / 86400
        row["latest_observation"] = latest.strftime("%Y-%m-%d")
        row["date_basis"] = "embedded"
        row["age_days"] = round(age_days, 1)
        # Future-dated observations are forecast targets or clock-skewed data,
        # not evidence of freshness: treat like a missing date, mtime fallback.
        if age_days < 0:
            row["status"] = _mtime_status(path, fresh_days)
            row["date_basis"] = f"mtime (future embedded date {row['latest_observation']})"
            row["detail"] = "embedded date is in the future; not evidence of freshness"
            return row
        row["status"] = _classify_observation_age(age_days, fresh_days)
        if row["status"] == "no-date":
            row["status"] = "fresh"
            row["detail"] = "observation date in the future"
        if detail:
            row["detail"] = detail
        return row

    if detail is not None:
        # Readable, but the registered observation date yielded nothing usable
        # (absent column/key, no parseable values). Freshness is unverifiable:
        # report conservatively stale rather than claiming ok or unreadable.
        # The expected-inputs check hardens this to unexpected-format when the
        # missing column is a required one.
        row["date_basis"] = "embedded"
        row["status"] = "stale"
        row["detail"] = f"cannot verify freshness: {detail}"
        return row

    # No registered observation: mtime fallback (pre-S2-04 behaviour)
    age_days = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 86400
    row["date_basis"] = "mtime"
    row["age_days"] = round(age_days, 1)
    row["status"] = _classify_observation_age(age_days, fresh_days)
    return row


def _iter_source_files(directory: Path, prefix: str, suffixes: tuple[str, ...]) -> list[tuple[Path, str]]:
    try:
        paths = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix in suffixes)
    except FileNotFoundError:
        return []
    return [(p, f"{prefix}/{p.name}") for p in paths]


def scan_sources() -> list[dict[str, Any]]:
    """Scan every discoverable source file under reference/ + au_dc/."""
    r = _roots()
    found: list[tuple[Path, str]] = []
    found += _iter_source_files(r.reference, "data/reference", (".csv", ".json"))
    found += _iter_source_files(r.au_dc / "processed", "data/au_dc/processed", (".parquet", ".json", ".csv"))
    found += _iter_source_files(r.au_dc / "reference", "data/au_dc/reference", (".csv", ".json"))

    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for path, display in found:
        if display in seen:
            continue
        seen.add(display)
        rows.append(_scan_one(path, display))
    return rows


# ────────────────────────────────────────────────────────────────────
# Expected-input inventory
# ────────────────────────────────────────────────────────────────────
def _required_missing(row: dict[str, Any], required: list[str]) -> list[str]:
    path = row["_path"]
    try:
        if path.suffix == ".parquet":
            cols = [str(c) for c in pd.read_parquet(path).columns]
        elif path.suffix == ".csv":
            cols = [str(c) for c in pd.read_csv(path, sep=None, engine="python", nrows=0).columns]
        else:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                return required
            return [k for k in required if k not in data]
        return [k for k in required if k not in cols]
    except Exception as exc:
        row["detail"] = f"{type(exc).__name__}: {exc}"
        return required


def check_expected(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expected-input inventory: presence, role, required columns, observation."""
    r = _roots()
    by_display = {row["source"]: row for row in sources}
    results: list[dict[str, Any]] = []
    for spec in EXPECTED_FILES:
        name = spec["name"]
        subdir = spec["subdir"]
        display = f"data/{subdir}/{name}" if subdir != "data" else f"data/{name}"
        if subdir == "reference":
            path = r.reference / name
        elif subdir == "data":
            path = r.data / name
        else:
            path = r.au_dc / Path(subdir).name / name

        scan = by_display.get(display)
        if scan is None and path.exists():
            # Expected files outside the scanned directories (e.g. data/*.json)
            # are scanned on demand instead of being misreported as missing.
            scan = _scan_one(path, display)
        entry: dict[str, Any] = {
            "source": display,
            "role": spec["role"],
            "status": "missing",
            "rows": None,
            "latest_observation": None,
            "detail": None,
        }
        if scan is not None:
            entry["status"] = scan["status"]
            entry["rows"] = scan.get("rows")
            entry["latest_observation"] = scan.get("latest_observation")
            entry["detail"] = scan.get("detail")

        if entry["status"] not in ("missing", "unreadable") and spec.get("required"):
            missing = _required_missing({"_path": path}, list(spec["required"]))
            if missing:
                entry["status"] = "unexpected-format"
                entry["detail"] = f"missing required column(s)/key(s): {', '.join(missing)}"

        if entry["status"] == "missing" and spec.get("rebuild"):
            entry["detail"] = f"rebuild with: {spec['rebuild']}"
        elif entry["status"] == "missing" and spec["role"] == "derived":
            entry["detail"] = "produced by its publisher on next successful run; absence is expected before first run"
        results.append(entry)
    return results


# ────────────────────────────────────────────────────────────────────
# Aggregation
# ────────────────────────────────────────────────────────────────────
def overall_from_sources(sources: list[dict[str, Any]], expected: list[dict[str, Any]]) -> str:
    """ok / degraded / error using the run_result contract vocabulary.

    error: any missing/unreadable source, any expected data/enrichment file
    in a hard-failed state, or a very-stale observation on a scanned source.
    degraded: stale observations / soft-role problems with nothing hard-broken.
    """
    statuses = [row["status"] for row in sources]
    if any(s in UNHEALTHY or s == "very-stale" for s in statuses):
        return OVERALL_ERROR
    hard_expected = {
        e["source"]
        for e in expected
        if e["role"] in ("data", "enrichment") and e["status"] in ("missing", "unreadable", "unexpected-format")
    }
    if hard_expected:
        return OVERALL_ERROR
    if any(s == "stale" for s in statuses):
        return OVERALL_DEGRADED
    soft_expected = {
        e["source"]
        for e in expected
        if e["role"] in ("intermediate", "derived", "diagnostic")
        and e["status"] in ("missing", "unreadable", "unexpected-format")
    }
    if soft_expected:
        return OVERALL_DEGRADED
    return OVERALL_OK


# ────────────────────────────────────────────────────────────────────
# Companion artifacts (fetcher log, guidance, spot check, research DB)
# ────────────────────────────────────────────────────────────────────
def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"_error": str(exc)}


def _research_summary(db_path: Path) -> dict:
    if not db_path.exists():
        return {"error": "database missing"}
    try:
        conn = sqlite3.connect(db_path)
        latest_runs = conn.execute(
            """
            SELECT run_date, queries_run, findings_count, categories_covered, COALESCE(notes, '')
            FROM research_log
            ORDER BY run_date DESC
            LIMIT 5
            """
        ).fetchall()
        categories = conn.execute(
            """
            SELECT category, COUNT(*), MAX(finding_date), MAX(created_at)
            FROM research_findings
            GROUP BY category
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()
        conn.close()
        return {
            "latest_runs": [
                {
                    "run_date": r[0],
                    "queries_run": r[1],
                    "findings_count": r[2],
                    "categories": r[3],
                    "notes": r[4],
                }
                for r in latest_runs
            ],
            "categories": [
                {"category": r[0], "count": r[1], "latest_finding": r[2], "latest_created": r[3]}
                for r in categories
            ],
        }
    except sqlite3.Error as exc:
        return {"error": str(exc)}


def scan_companions() -> dict[str, Any]:
    r = _roots()
    fetcher_log = _load_json(r.data / "fetcher_log.json")
    # flag error/degraded fetchers so they participate in the overall status
    flagged: list[dict[str, str]] = []
    for script, entry in sorted(fetcher_log.items()):
        if script.startswith("_") or not isinstance(entry, dict):
            continue
        if entry.get("status") in ("error", "degraded"):
            flagged.append({
                "script": script,
                "status": entry.get("status", "unknown"),
                "last_attempt": entry.get("last_attempt") or entry.get("last_run") or "unknown",
                "notes": str(entry.get("notes", ""))[:200],
            })
    return {
        "fetcher_log": fetcher_log,
        "fetcher_errors": flagged,
        "stale_guidance": _load_json(r.data / "stale_guidance.json"),
        "au_dc_spot_check": _load_json(r.au_dc / "processed" / "spot_check.json"),
        "research": _research_summary(r.data / "db" / "ai_research.db"),
    }


# ────────────────────────────────────────────────────────────────────
# Report assembly
# ────────────────────────────────────────────────────────────────────
def scan_all() -> dict[str, Any]:
    sources = scan_sources()
    expected = check_expected(sources)
    overall = overall_from_sources(sources, expected)
    return {"sources": sources, "expected": expected, "overall_status": overall}


def build_report() -> dict:
    scanned = scan_all()
    report: dict[str, Any] = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall_status": scanned["overall_status"],
        "reference_files": [r for r in scanned["sources"] if r["source"].startswith("data/reference/")],
        "au_dc_files": [r for r in scanned["sources"] if r["source"].startswith("data/au_dc/")],
        "expected_inputs": scanned["expected"],
        "counts": {
            "fresh": sum(1 for r in scanned["sources"] if r["status"] == "fresh"),
            "stale": sum(1 for r in scanned["sources"] if r["status"] == "stale"),
            "very_stale": sum(1 for r in scanned["sources"] if r["status"] == "very-stale"),
            "missing": sum(1 for r in scanned["sources"] if r["status"] == "missing"),
            "unreadable": sum(1 for r in scanned["sources"] if r["status"] == "unreadable"),
            "no_date": sum(1 for r in scanned["sources"] if r["status"] == "no-date"),
        },
    }
    report.update(scan_companions())
    # If a producer recorded a hard failure, the overall can't be "ok".
    if report["overall_status"] == OVERALL_OK and report["fetcher_errors"]:
        report["overall_status"] = OVERALL_DEGRADED
        report["counts"]["fetcher_degraded"] = len(report["fetcher_errors"])
    return report


# ────────────────────────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────────────────────────
def _source_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Source | Status | Basis | Latest Obs | Age Days | Rows | Detail |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    order = {"unreadable": 0, "missing": 1, "very-stale": 2, "stale": 3, "no-date": 4, "fresh": 5}
    for row in sorted(rows, key=lambda r: (order.get(r["status"], 6), str(r["source"]))):
        age = row.get("age_days")
        lines.append(
            f"| `{row['source']}` | {row['status']} | {row.get('date_basis') or '—'} "
            f"| {row.get('latest_observation') or '—'} | {age if age is not None else '—'} "
            f"| {row.get('rows') if row.get('rows') is not None else '—'} "
            f"| {row.get('detail') or ''} |"
        )
    return lines


def to_markdown(report: dict) -> str:
    lines = [
        f"# AI & DC Source Health — {report['generated_at']}",
        "",
        f"**Overall: {report['overall_status'].upper()}** "
        f"(fresh {report['counts']['fresh']} · stale {report['counts']['stale']} · "
        f"very-stale {report['counts']['very_stale']} · missing {report['counts']['missing']} · "
        f"unreadable {report['counts']['unreadable']})",
        "",
        "## Reference Files",
    ]
    lines += _source_table(report["reference_files"])

    lines += ["", "## AU DC Files"]
    lines += _source_table(report["au_dc_files"])

    lines += [
        "",
        "## Expected Inputs",
        "| Source | Role | Status | Rows | Latest Obs | Detail |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    role_order = {"data": 0, "enrichment": 1, "intermediate": 2, "derived": 3, "diagnostic": 4}
    bad_first = {"missing": 0, "unreadable": 0, "unexpected-format": 1}
    for e in sorted(
        report["expected_inputs"],
        key=lambda e: (bad_first.get(e["status"], 2), role_order.get(e["role"], 5), e["source"]),
    ):
        lines.append(
            f"| `{e['source']}` | {e['role']} | {e['status']} "
            f"| {e.get('rows') if e.get('rows') is not None else '—'} "
            f"| {e.get('latest_observation') or '—'} | {e.get('detail') or ''} |"
        )

    lines += ["", "## ETL Last Runs"]
    fetcher_log = report.get("fetcher_log") or {}
    if fetcher_log:
        for script, entry in sorted(fetcher_log.items()):
            if script.startswith("_") or not isinstance(entry, dict):
                continue
            last_attempt = entry.get("last_attempt") or entry.get("last_run") or "unknown"
            last_success = entry.get("last_success", "")
            counts = ""
            if "succeeded" in entry:
                counts = f" ({entry.get('succeeded')}/{entry.get('attempted', '?')} sources)"
            elif "count" in entry:
                counts = f" (count {entry.get('count')})"
            success_note = f"; last success {last_success}" if last_success and last_success != last_attempt else ""
            lines.append(
                f"- `{script}`: {entry.get('status', 'unknown')} at {last_attempt}{counts}{success_note} — {entry.get('notes', '')}"
            )
    else:
        lines.append("- No fetcher log found.")

    stale = (report.get("stale_guidance") or {}).get("stale_tickers", [])
    lines += ["", "## Capex Guidance"]
    if stale:
        for item in stale:
            lines.append(
                f"- Stale: {item.get('ticker')} ({item.get('company')}) — last guidance "
                f"{item.get('last_guidance_date')}, earnings {item.get('last_earnings_date')}"
            )
    else:
        lines.append("- No stale guidance tickers reported.")

    spot = report.get("au_dc_spot_check") or {}
    lines += ["", "## AU DC Spot Check"]
    summary = spot.get("summary")
    if summary:
        lines.append(
            f"- Summary: {summary.get('errors', 0)} errors, {summary.get('warnings', 0)} warnings, "
            f"{summary.get('ok', 0)} ok (run {spot.get('run_at', 'unknown')})."
        )
        for check in spot.get("checks", []):
            if check.get("level") != "ok":
                lines.append(f"- {check.get('level')}: `{check.get('code')}` — {check.get('message')}")
    else:
        lines.append("- No spot check summary found.")

    research = report.get("research") or {}
    lines += ["", "## Research Log"]
    for run in research.get("latest_runs", [])[:3]:
        lines.append(f"- {run['run_date']}: {run['findings_count']} findings across {run['categories']} — {run['notes'][:160]}")
    if not research.get("latest_runs"):
        lines.append("- No research runs logged.")

    return "\n".join(lines) + "\n"


# ────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────
def _check_exit_code(report: dict) -> int:
    """0 = ok/degraded, 2 = error (run-vps-*.sh treat >=2 as fatal)."""
    return 0 if report["overall_status"] in (OVERALL_OK, OVERALL_DEGRADED) else 2


def main(argv: list[str] | None = None) -> int:
    docline = (sys.modules[__name__].__doc__ or "source health report").splitlines()[0]
    parser = argparse.ArgumentParser(description=docline)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown (default)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Audit mode: one summary line; exit 0 ok/degraded, 2 error (run-vps-*.sh convention)",
    )
    args = parser.parse_args(argv)

    report = build_report()

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = report["generated_at"].replace(":", "").replace("-", "")[:15]
        (args.out_dir / f"source-health-{stamp}.json").write_text(json.dumps(report, indent=2))
        (args.out_dir / f"source-health-{stamp}.md").write_text(to_markdown(report))

    if args.check:
        counts = report["counts"]
        problems = [
            f"{r['source']} ({r['status']})"
            for r in report["reference_files"] + report["au_dc_files"]
            if r["status"] in ("missing", "unreadable", "very-stale")
        ]
        problems += [
            f"expected {e['source']} ({e['status']})"
            for e in report["expected_inputs"]
            if e["role"] in ("data", "enrichment") and e["status"] in ("missing", "unreadable", "unexpected-format")
        ]
        tail = "; ".join(problems[:12]) if problems else "no hard problems"
        more = f" (+{len(problems) - 12} more)" if len(problems) > 12 else ""
        print(
            f"source-health: {report['overall_status'].upper()} — "
            f"fresh {counts['fresh']}, stale {counts['stale']}, very-stale {counts['very_stale']}, "
            f"missing {counts['missing']}, unreadable {counts['unreadable']} — {tail}{more}"
        )
        return _check_exit_code(report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(to_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
