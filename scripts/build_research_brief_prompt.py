"""Build the report-only AI & DC research prompt for a VPS LLM runner."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "db" / "ai_research.db"
STALE_GUIDANCE_PATH = DATA_DIR / "stale_guidance.json"


def _latest_research_runs() -> list[tuple]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT run_date, findings_count, categories_covered, COALESCE(notes, '')
        FROM research_log
        ORDER BY run_date DESC
        LIMIT 5
        """
    ).fetchall()
    conn.close()
    return rows


def _stale_guidance() -> list[dict]:
    if not STALE_GUIDANCE_PATH.exists():
        return []
    try:
        return json.loads(STALE_GUIDANCE_PATH.read_text()).get("stale_tickers", [])
    except Exception:
        return []


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stale = _stale_guidance()
    runs = _latest_research_runs()

    print(f"# AI & DC Dashboard Research Brief Prompt — {today}")
    print()
    print("You are running on the Hetzner VPS as a report-only research agent.")
    print("Do not edit repo data files, do not commit, and do not write to SQLite.")
    print("Return a concise Markdown brief plus a JSON appendix of candidate findings.")
    print()
    print("## Scope")
    print("- Search for material AI infrastructure and data-centre updates from the last 14 days.")
    print("- Prioritise primary/company/regulator sources over media.")
    print("- Include only candidate findings with concrete numbers and source URLs.")
    print("- Cover: AU data-centre pipeline, operator aggregate guidance/contracts, funding/debt deals, hyperscaler capex guidance, model release/pricing shifts, GPU rental or hardware pricing signals.")
    print("- Flag whether each candidate is safe for automatic promotion or requires human review.")
    print()
    print("## Current Stale Capex Guidance")
    if stale:
        for item in stale:
            print(f"- {item.get('ticker')} ({item.get('company')}): query `{item.get('search_query')}`")
    else:
        print("- None currently reported.")
    print()
    print("## Latest Research Runs")
    if runs:
        for run_date, findings_count, categories, notes in runs:
            print(f"- {run_date}: {findings_count} findings across {categories}; {notes[:180]}")
    else:
        print("- No research log found.")
    print()
    print("## Output Format")
    print("1. Executive summary: 5 bullets maximum.")
    print("2. Candidate findings table: category, company, metric, value, period, source URL, confidence, promotion recommendation.")
    print("3. Gaps and searches that found no verified number.")
    print("4. JSON appendix with an array named `candidate_findings`.")


if __name__ == "__main__":
    main()
