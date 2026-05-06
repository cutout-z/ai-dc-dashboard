"""Refresh analyst consensus data and save as JSON for Streamlit Cloud.

Run locally before pushing to update consensus estimates. Uses FMP API for:
  - Revenue, EBITDA, EPS estimates (current + next fiscal year)
  - Price target consensus (mean, high, low)
  - Individual analyst price targets (firm, analyst, date — last 5)
  - Upgrade/downgrade history (last 5)

FMP key is loaded from env FMP_API_KEY, ~/.openbb_platform/user_settings.json,
or macOS Keychain (security add-generic-password -s fmp_api_key).

Usage:
    python etl/refresh_consensus.py
"""

from __future__ import annotations

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lib.fmp import (  # noqa: E402
    get_analyst_estimates,
    get_fmp_key,
    get_price_target_consensus,
    get_price_targets,
    get_upgrades_downgrades,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OUT_PATH = Path(__file__).parent.parent / "data" / "reference" / "consensus.json"

COMPANIES = {
    "AAPL":  {"name": "Apple",           "ccy_scale": 1.0},
    "MSFT":  {"name": "Microsoft",       "ccy_scale": 1.0},
    "GOOGL": {"name": "Alphabet",        "ccy_scale": 1.0},
    "AMZN":  {"name": "Amazon",          "ccy_scale": 1.0},
    "NVDA":  {"name": "NVIDIA",          "ccy_scale": 1.0},
    "META":  {"name": "Meta",            "ccy_scale": 1.0},
    "TSLA":  {"name": "Tesla",           "ccy_scale": 1.0},
    "ORCL":  {"name": "Oracle",          "ccy_scale": 1.0},
    "AMD":   {"name": "AMD",             "ccy_scale": 1.0},
    "TSM":   {"name": "TSMC",            "ccy_scale": 1 / 32.0},
    "PLTR":  {"name": "Palantir",        "ccy_scale": 1.0},
    "EQIX":  {"name": "Equinix",         "ccy_scale": 1.0},
    "DLR":   {"name": "Digital Realty",  "ccy_scale": 1.0},
    "AMT":   {"name": "American Tower",  "ccy_scale": 1.0},
}


def _fetch_one(ticker: str, ccy_scale: float) -> tuple[str, dict]:
    scale = ccy_scale / 1e6
    today = datetime.now(timezone.utc).date().isoformat()

    estimates = get_analyst_estimates(ticker, period="annual", limit=6)
    pt_consensus = get_price_target_consensus(ticker)
    pt_targets = get_price_targets(ticker, limit=15)
    upgrades = get_upgrades_downgrades(ticker, limit=10)

    # ── Analyst estimates: identify current-year (0y) and next-year (1y) ──────
    # FMP returns newest-first; sort ascending by fiscal year end date.
    estimates_sorted = sorted(estimates, key=lambda x: x.get("date", ""))
    # Forward periods = fiscal years that haven't ended yet.
    forward = [e for e in estimates_sorted if e.get("date", "") >= today]
    if len(forward) < 2:
        # Fall back to the two most recent entries (catches companies with
        # non-calendar fiscal years where "current" FY already ended).
        forward = estimates_sorted[-2:]

    est_0y = forward[0] if len(forward) > 0 else {}
    est_1y = forward[1] if len(forward) > 1 else {}

    def _s(v):
        """Scale raw units → $M, round to 1dp."""
        try:
            return round(float(v) * scale, 1) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _f(v, dp: int = 4):
        try:
            return round(float(v), dp) if v is not None else None
        except (TypeError, ValueError):
            return None

    # Revenue
    rev_0y_avg  = _s(est_0y.get("revenueAvg"))
    rev_0y_low  = _s(est_0y.get("revenueLow"))
    rev_0y_high = _s(est_0y.get("revenueHigh"))
    rev_1y_avg  = _s(est_1y.get("revenueAvg"))
    rev_1y_low  = _s(est_1y.get("revenueLow"))
    rev_1y_high = _s(est_1y.get("revenueHigh"))
    rev_n = int(est_0y.get("numAnalystsRevenue") or 0) or None

    rev_growth = None
    if rev_0y_avg and rev_1y_avg and rev_0y_avg != 0:
        rev_growth = _f((rev_1y_avg - rev_0y_avg) / rev_0y_avg)

    # EPS
    eps_0y_avg = _f(est_0y.get("epsAvg"), dp=4)
    eps_1y_avg = _f(est_1y.get("epsAvg"), dp=4)
    eps_n = int(est_0y.get("numAnalystsEps") or 0) or None

    # EBITDA
    ebitda_0y_avg  = _s(est_0y.get("ebitdaAvg"))
    ebitda_0y_low  = _s(est_0y.get("ebitdaLow"))
    ebitda_0y_high = _s(est_0y.get("ebitdaHigh"))
    ebitda_1y_avg  = _s(est_1y.get("ebitdaAvg"))
    ebitda_1y_low  = _s(est_1y.get("ebitdaLow"))
    ebitda_1y_high = _s(est_1y.get("ebitdaHigh"))

    # Net income estimates (used to extend income statement in financials view)
    ni_0y_avg = _s(est_0y.get("netIncomeAvg"))
    ni_1y_avg = _s(est_1y.get("netIncomeAvg"))

    # ── Price targets ─────────────────────────────────────────────────────────
    def _pt(key):
        v = pt_consensus.get(key)
        try:
            return round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None

    pt_mean = _pt("targetConsensus")
    pt_low  = _pt("targetLow")
    pt_high = _pt("targetHigh")

    # Current price = priceWhenPosted on the most recent analyst note
    pt_current = None
    if pt_targets:
        most_recent = sorted(pt_targets, key=lambda x: x.get("publishedDate", ""), reverse=True)
        try:
            pt_current = round(float(most_recent[0].get("priceWhenPosted")), 2)
        except (TypeError, ValueError):
            pass

    # Individual analyst targets (newest 5)
    pt_analysts = []
    for t in sorted(pt_targets, key=lambda x: x.get("publishedDate", ""), reverse=True)[:5]:
        entry = {
            "firm":     t.get("analystCompany") or t.get("newsPublisher"),
            "analyst":  t.get("analystName"),
            "price":    t.get("priceTarget"),
            "date":     (t.get("publishedDate") or "")[:10],
        }
        pt_analysts.append(entry)

    # Upgrades / downgrades (newest 5) — stable/grades uses "date" not "publishedDate"
    upgrades_downgrades = []
    for u in sorted(upgrades, key=lambda x: x.get("date", ""), reverse=True)[:5]:
        entry = {
            "firm":       u.get("gradingCompany"),
            "action":     u.get("action"),
            "new_grade":  u.get("newGrade"),
            "prev_grade": u.get("previousGrade"),
            "date":       (u.get("date") or "")[:10],
        }
        upgrades_downgrades.append(entry)

    result = {
        # Revenue estimates
        "rev_0y_avg":  rev_0y_avg,
        "rev_0y_low":  rev_0y_low,
        "rev_0y_high": rev_0y_high,
        "rev_1y_avg":  rev_1y_avg,
        "rev_1y_low":  rev_1y_low,
        "rev_1y_high": rev_1y_high,
        "rev_n":       rev_n,
        "rev_growth":  rev_growth,
        # EPS estimates
        "eps_0y_avg":  eps_0y_avg,
        "eps_1y_avg":  eps_1y_avg,
        "eps_n":       eps_n,
        # EBITDA estimates (new)
        "ebitda_0y_avg":  ebitda_0y_avg,
        "ebitda_0y_low":  ebitda_0y_low,
        "ebitda_0y_high": ebitda_0y_high,
        "ebitda_1y_avg":  ebitda_1y_avg,
        "ebitda_1y_low":  ebitda_1y_low,
        "ebitda_1y_high": ebitda_1y_high,
        # Net income estimates
        "ni_0y_avg": ni_0y_avg,
        "ni_1y_avg": ni_1y_avg,
        # Price targets
        "pt_current": pt_current,
        "pt_mean":    pt_mean,
        "pt_low":     pt_low,
        "pt_high":    pt_high,
        # Analyst detail (new)
        "pt_analysts":        pt_analysts,
        "upgrades_downgrades": upgrades_downgrades,
    }

    scalar_fields = {k: v for k, v in result.items()
                     if k not in ("rev_n", "eps_n", "pt_analysts", "upgrades_downgrades")}
    has_data = any(v is not None for v in scalar_fields.values())

    if has_data:
        logger.info("  %s: OK (pt_mean=%s  rev_0y=%s  ebitda_0y=%s)",
                    ticker, pt_mean, rev_0y_avg, ebitda_0y_avg)
        return ticker, result
    else:
        logger.warning("  %s: no data returned from FMP", ticker)
        return ticker, {}


def main():
    if not get_fmp_key():
        logger.error(
            "No FMP API key found — set FMP_API_KEY env var, add to "
            "~/.openbb_platform/user_settings.json, or store in Keychain "
            "(security add-generic-password -s fmp_api_key -w <key>)"
        )
        sys.exit(1)

    logger.info("Fetching FMP analyst consensus for %d companies...", len(COMPANIES))

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_fetch_one, ticker, meta["ccy_scale"]): ticker
            for ticker, meta in COMPANIES.items()
        }
        for future in as_completed(futures):
            ticker, data = future.result()
            if data:
                results[ticker] = data

    output = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source":  "fmp",
        "data":    results,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2))
    logger.info("Wrote %d companies to %s", len(results), OUT_PATH)


if __name__ == "__main__":
    main()
