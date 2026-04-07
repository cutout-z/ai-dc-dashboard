"""
Research Pass — Automated extraction of AI/DC datapoints from web sources.

This script is designed to be called by a Claude Code skill or scheduled agent.
It performs structured web research and appends findings to the database.

Data targets:
1. Hyperscaler AI revenue disclosures (from earnings/news)
2. CAPEX guidance changes
3. DC pipeline announcements (new builds, MW commitments)
4. Frontier model DAU/subscriber counts
5. International DC demand forecasts (IEA, PJM, etc.)

Each finding is stored as a structured record with source, date, and confidence.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"


def init_research_tables():
    """Create the research findings table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_date TEXT NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT,
            company TEXT,
            metric_name TEXT,
            metric_value TEXT,
            unit TEXT,
            period TEXT,
            source_url TEXT,
            source_description TEXT,
            extracted_quote TEXT,
            confidence TEXT DEFAULT 'medium',
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            queries_run INTEGER,
            findings_count INTEGER,
            categories_covered TEXT,
            duration_seconds REAL,
            notes TEXT
        )
    """)

    conn.commit()
    conn.close()


def add_finding(
    category: str,
    metric_name: str,
    metric_value: str,
    company: str = None,
    subcategory: str = None,
    unit: str = None,
    period: str = None,
    source_url: str = None,
    source_description: str = None,
    extracted_quote: str = None,
    confidence: str = "medium",
    notes: str = None,
    finding_date: str = None,
):
    """Add a research finding to the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO research_findings
           (finding_date, category, subcategory, company, metric_name, metric_value,
            unit, period, source_url, source_description, extracted_quote,
            confidence, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            finding_date or datetime.now().strftime("%Y-%m-%d"),
            category,
            subcategory,
            company,
            metric_name,
            str(metric_value),
            unit,
            period,
            source_url,
            source_description,
            extracted_quote,
            confidence,
            notes,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def log_run(queries_run: int, findings_count: int, categories: list, duration: float, notes: str = None):
    """Log a research pass execution."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO research_log (run_date, queries_run, findings_count, categories_covered, duration_seconds, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            queries_run,
            findings_count,
            json.dumps(categories),
            duration,
            notes,
        ),
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# RESEARCH QUERIES — used by the skill/agent
# ──────────────────────────────────────────────

RESEARCH_QUERIES = {
    "hyperscaler_capex": {
        "category": "capex",
        "queries": [
            "Microsoft Azure AI CAPEX guidance {quarter} {year}",
            "Google Cloud AI infrastructure spending {quarter} {year}",
            "Amazon AWS AI CAPEX {quarter} {year}",
            "Meta AI infrastructure investment {quarter} {year}",
        ],
        "extract_fields": ["company", "capex_amount", "period", "guidance_direction"],
    },
    "ai_revenue": {
        "category": "ai_revenue",
        "queries": [
            "Microsoft AI revenue run rate {year}",
            "Google Cloud AI revenue {quarter} {year}",
            "AWS AI services revenue growth {year}",
            "Meta AI revenue contribution {year}",
        ],
        "extract_fields": ["company", "revenue_amount", "growth_rate", "period"],
    },
    "dc_pipeline": {
        "category": "dc_pipeline",
        "queries": [
            "new data center construction announcements {year}",
            "hyperscale data center MW capacity {year}",
            "data center power capacity planned {year}",
        ],
        "extract_fields": ["company", "location", "capacity_mw", "status", "expected_completion"],
    },
    "frontier_model_adoption": {
        "category": "model_adoption",
        "queries": [
            "ChatGPT monthly active users {year}",
            "Claude AI users subscribers {year}",
            "Gemini AI users {year}",
            "AI assistant paid subscriber count {year}",
        ],
        "extract_fields": ["product", "metric", "value", "date"],
    },
    "dc_demand_forecasts": {
        "category": "dc_demand",
        "queries": [
            "IEA data centre electricity demand forecast {year}",
            "PJM interconnection queue data center {year}",
            "global data center power demand forecast GW {year}",
        ],
        "extract_fields": ["source", "forecast_year", "demand_value", "unit", "region"],
    },
    "open_source_progress": {
        "category": "open_source",
        "queries": [
            "open source LLM benchmark performance vs GPT Claude {year}",
            "Llama Qwen Mistral benchmark results {year}",
            "open source AI model capability gap closing {year}",
        ],
        "extract_fields": ["model", "benchmark", "score", "gap_to_frontier"],
    },
}


def get_research_queries(quarter: str = None, year: str = None) -> dict:
    """Get formatted research queries for the current period."""
    if year is None:
        year = str(datetime.now().year)
    if quarter is None:
        q = (datetime.now().month - 1) // 3 + 1
        quarter = f"Q{q}"

    formatted = {}
    for key, config in RESEARCH_QUERIES.items():
        formatted[key] = {
            "category": config["category"],
            "queries": [
                q.format(quarter=quarter, year=year)
                for q in config["queries"]
            ],
            "extract_fields": config["extract_fields"],
        }
    return formatted


if __name__ == "__main__":
    # Initialize tables
    init_research_tables()
    print("Research tables initialized.")

    # Print queries for current period
    queries = get_research_queries()
    print(f"\nResearch queries for current period:")
    for key, config in queries.items():
        print(f"\n  [{config['category']}]")
        for q in config["queries"]:
            print(f"    - {q}")
