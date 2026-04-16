"""Refresh llm_leaderboard.json from llm-stats.com.

Scrapes the top 30 from both:
  - https://llm-stats.com/leaderboards/llm-leaderboard  (closed/commercial)
  - https://llm-stats.com/leaderboards/open-llm-leaderboard  (open-weight)

Combines, deduplicates (keeps first occurrence by composite score), and writes
top 30 to data/reference/llm_leaderboard.json.

Run manually or via the /ai-research skill.
"""

import datetime
import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "llm_leaderboard.json"


def _parse_pct(v: str):
    if not v or v in ("—", "–", "-", ""):
        return None
    return float(v.rstrip("%")) if v.endswith("%") else None


def _parse_price(v: str):
    if not v or v in ("—", "–", "-", ""):
        return None
    return float(v.lstrip("$").replace(",", ""))


def _parse_ctx(v: str):
    if not v or v in ("—", "–", "-", ""):
        return None
    v = v.upper().replace(",", "")
    if v.endswith("M"):
        return int(float(v[:-1]) * 1000)
    if v.endswith("K"):
        return int(float(v[:-1]))
    try:
        return int(float(v))
    except ValueError:
        return None


def _parse_speed(v: str):
    if not v or v in ("—", "–", "-", ""):
        return None
    m = re.match(r"(\d+)", v)
    return int(m.group(1)) if m else None


def _parse_score(v: str):
    if not v or v in ("—", "–", "-", ""):
        return None
    try:
        return int(v.replace(",", ""))
    except ValueError:
        return None


BOARDS = [
    ("llm",  "https://llm-stats.com/leaderboards/llm-leaderboard"),
    ("open", "https://llm-stats.com/leaderboards/open-llm-leaderboard"),
]


def scrape() -> list[dict]:
    all_models: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for board_name, url in BOARDS:
            page.goto(url, wait_until="networkidle", timeout=30_000)
            time.sleep(3)

            rows = page.evaluate("""() => {
                const rows = document.querySelectorAll("table tbody tr");
                return Array.from(rows).slice(0, 30).map(row => {
                    const cells = row.querySelectorAll("td");
                    return Array.from(cells).map(c => c.innerText.trim());
                });
            }""")

            for row in rows:
                if len(row) < 48:
                    continue
                name = row[1]
                if not name or name in all_models:
                    continue

                all_models[name] = {
                    "name": name,
                    "org": row[47],
                    "source_board": board_name,
                    "composite_score": _parse_score(row[8]),
                    "context_k": _parse_ctx(row[4]),
                    "input_price": _parse_price(row[5]),
                    "output_price": _parse_price(row[6]),
                    "speed_cps": _parse_speed(row[7]),
                    "gpqa": _parse_pct(row[20]),
                    "aime_2025": _parse_pct(row[21]),
                    "swe_bench": _parse_pct(row[22]),
                    "hle": _parse_pct(row[31]),
                }

        browser.close()

    sorted_models = sorted(
        all_models.values(),
        key=lambda x: x["composite_score"] or 0,
        reverse=True,
    )[:30]

    for i, m in enumerate(sorted_models, 1):
        m["rank"] = i

    return sorted_models


def main():
    print("Scraping llm-stats.com leaderboards...")
    models = scrape()
    print(f"  {len(models)} models scraped")

    payload = {
        "_meta": {
            "source_boards": [url for _, url in BOARDS],
            "updated": datetime.date.today().isoformat(),
            "note": "Combined top 30 from LLM + Open LLM leaderboards, ranked by Code Arena composite score.",
        },
        "models": models,
    }

    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"  Written to {OUT_PATH}")
    for m in models:
        print(f"  {m['rank']:2d}. {m['name']:<35} ({m['org']}) score={m['composite_score']} [{m['source_board']}]")


if __name__ == "__main__":
    main()
