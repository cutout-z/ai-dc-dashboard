"""Generate a CLI source-health report for AI & DC Dashboard automation."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REF_DIR = DATA_DIR / "reference"
AU_DC_DIR = DATA_DIR / "au_dc"
DB_PATH = DATA_DIR / "db" / "ai_research.db"
FETCHER_LOG_PATH = DATA_DIR / "fetcher_log.json"
STALE_GUIDANCE_PATH = DATA_DIR / "stale_guidance.json"
SPOT_CHECK_PATH = AU_DC_DIR / "processed" / "spot_check.json"

FILE_FRESH_DAYS = {
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
}

AU_DC_FRESH_DAYS = {
    "generation_info.parquet": 30,
    "grid_capacity.parquet": 30,
    "nem_demand_actual.parquet": 90,
    "projects.parquet": 30,
    "spot_check.json": 30,
    "projects_seed.csv": 90,
    "operator_aggregate_guidance.csv": 30,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_days(path: Path) -> float | None:
    if not path.exists():
        return None
    return (_now().timestamp() - path.stat().st_mtime) / 86400


def _status(age_days: float | None, fresh_days: int) -> str:
    if age_days is None:
        return "missing"
    if age_days <= fresh_days:
        return "fresh"
    if age_days <= fresh_days * 3:
        return "stale"
    return "very-stale"


def _row_count(path: Path) -> int | None:
    try:
        if path.suffix == ".csv":
            with path.open(newline="") as f:
                return max(sum(1 for _ in csv.reader(f)) - 1, 0)
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], dict):
                    return len(data["data"])
                if "models" in data and isinstance(data["models"], list):
                    return len(data["models"])
                return len(data)
    except Exception:
        return None
    return None


def _scan_files(directory: Path, thresholds: dict[str, int], suffixes: tuple[str, ...]) -> list[dict]:
    rows = []
    if not directory.exists():
        return rows
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        fresh_days = thresholds.get(path.name, 30)
        age = _age_days(path)
        rows.append({
            "source": str(path.relative_to(PROJECT_ROOT)),
            "status": _status(age, fresh_days),
            "age_days": None if age is None else round(age, 1),
            "fresh_days": fresh_days,
            "rows": _row_count(path),
        })
    return rows


def _fetcher_log() -> dict:
    if not FETCHER_LOG_PATH.exists():
        return {}
    try:
        return json.loads(FETCHER_LOG_PATH.read_text())
    except Exception as exc:
        return {"_error": str(exc)}


def _research_summary() -> dict:
    if not DB_PATH.exists():
        return {"error": "database missing"}
    try:
        conn = sqlite3.connect(DB_PATH)
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


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"_error": str(exc)}


def build_report() -> dict:
    au_rows = []
    au_rows.extend(_scan_files(AU_DC_DIR / "processed", AU_DC_FRESH_DAYS, (".parquet", ".json", ".csv")))
    au_rows.extend(_scan_files(AU_DC_DIR / "reference", AU_DC_FRESH_DAYS, (".csv", ".json")))
    return {
        "generated_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reference_files": _scan_files(REF_DIR, FILE_FRESH_DAYS, (".csv", ".json")),
        "au_dc_files": au_rows,
        "fetcher_log": _fetcher_log(),
        "stale_guidance": _load_json(STALE_GUIDANCE_PATH),
        "au_dc_spot_check": _load_json(SPOT_CHECK_PATH),
        "research": _research_summary(),
    }


def to_markdown(report: dict) -> str:
    lines = [
        f"# AI & DC Source Health — {report['generated_at']}",
        "",
        "## Reference Files",
        "| Source | Status | Age Days | Rows |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in report["reference_files"]:
        lines.append(f"| `{row['source']}` | {row['status']} | {row['age_days']} | {row['rows'] or ''} |")

    lines.extend(["", "## AU DC Files", "| Source | Status | Age Days |", "| --- | --- | ---: |"])
    for row in report["au_dc_files"]:
        lines.append(f"| `{row['source']}` | {row['status']} | {row['age_days']} |")

    lines.extend(["", "## ETL Last Runs"])
    fetcher_log = report.get("fetcher_log") or {}
    if fetcher_log:
        for script, entry in sorted(fetcher_log.items()):
            if script.startswith("_"):
                continue
            lines.append(f"- `{script}`: {entry.get('status', 'unknown')} at {entry.get('last_run', 'unknown')} — {entry.get('notes', '')}")
    else:
        lines.append("- No fetcher log found.")

    stale = (report.get("stale_guidance") or {}).get("stale_tickers", [])
    lines.extend(["", "## Capex Guidance"])
    if stale:
        for item in stale:
            lines.append(f"- Stale: {item.get('ticker')} ({item.get('company')}) — last guidance {item.get('last_guidance_date')}, earnings {item.get('last_earnings_date')}")
    else:
        lines.append("- No stale guidance tickers reported.")

    spot = report.get("au_dc_spot_check") or {}
    lines.extend(["", "## AU DC Spot Check"])
    summary = spot.get("summary")
    if summary:
        lines.append(f"- Summary: {summary.get('errors', 0)} errors, {summary.get('warnings', 0)} warnings, {summary.get('ok', 0)} ok.")
        for check in spot.get("checks", []):
            if check.get("level") != "ok":
                lines.append(f"- {check.get('level')}: `{check.get('code')}` — {check.get('message')}")
    else:
        lines.append("- No spot check summary found.")

    research = report.get("research") or {}
    lines.extend(["", "## Research Log"])
    for run in research.get("latest_runs", [])[:3]:
        lines.append(f"- {run['run_date']}: {run['findings_count']} findings across {run['categories']} — {run['notes'][:160]}")
    if not research.get("latest_runs"):
        lines.append("- No research runs logged.")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    args = parser.parse_args()

    report = build_report()
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = report["generated_at"].replace(":", "").replace("-", "")[:15]
        (args.out_dir / f"source-health-{stamp}.json").write_text(json.dumps(report, indent=2))
        (args.out_dir / f"source-health-{stamp}.md").write_text(to_markdown(report))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(to_markdown(report))


if __name__ == "__main__":
    main()
