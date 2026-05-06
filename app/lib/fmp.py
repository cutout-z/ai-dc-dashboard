"""Financial Modeling Prep (FMP) API client for ai-research.

Key loading order:
  1. FMP_API_KEY environment variable  (cloud/production)
  2. ~/.openbb_platform/user_settings.json  (local dev / OpenBB config)
  3. macOS Keychain  (security find-generic-password -s fmp_api_key -w)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import httpx

FMP_BASE   = "https://financialmodelingprep.com/api"    # legacy v3/v4 (deprecated Aug 2025)
FMP_STABLE = "https://financialmodelingprep.com/stable"  # new stable endpoints

_OPENBB_SETTINGS = Path.home() / ".openbb_platform" / "user_settings.json"
_FMP_API_KEY: str | None = None


def get_fmp_key() -> str | None:
    global _FMP_API_KEY
    if _FMP_API_KEY:
        return _FMP_API_KEY

    env_key = os.environ.get("FMP_API_KEY")
    if env_key:
        _FMP_API_KEY = env_key
        return _FMP_API_KEY

    try:
        settings = json.loads(_OPENBB_SETTINGS.read_text())
        key = settings.get("credentials", {}).get("fmp_api_key")
        if key:
            _FMP_API_KEY = key
            return _FMP_API_KEY
    except (OSError, json.JSONDecodeError):
        pass

    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "fmp_api_key", "-w"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            key = result.stdout.strip()
            if key:
                _FMP_API_KEY = key
                return _FMP_API_KEY
    except Exception:
        pass

    return None


def _get_sync(path: str, **params) -> dict | list | None:
    """Synchronous GET against the legacy FMP_BASE (v3/v4)."""
    key = get_fmp_key()
    if not key:
        return None
    try:
        resp = httpx.get(
            f"{FMP_BASE}{path}",
            params={"apikey": key, **params},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _get_stable(endpoint: str, **params) -> dict | list | None:
    """Synchronous GET against the FMP stable API (post-Aug 2025)."""
    key = get_fmp_key()
    if not key:
        return None
    try:
        resp = httpx.get(
            f"{FMP_STABLE}/{endpoint}",
            params={"apikey": key, **params},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_earnings_dates(symbol: str) -> list[dict]:
    """Upcoming and recent earnings dates for a single symbol.

    Returns list of dicts with keys: date, symbol, eps, epsEstimated, revenue,
    revenueEstimated, time (bmo/amc), updatedFromDate, fiscalDateEnding.
    """
    data = _get_sync(f"/v3/historical/earning_calendar/{symbol}", limit=10)
    return data if isinstance(data, list) else []


def get_earnings_calendar_range(from_date: str, to_date: str) -> list[dict]:
    """Earnings calendar for a date range (YYYY-MM-DD)."""
    data = _get_sync("/v3/earning_calendar", **{"from": from_date, "to": to_date})
    return data if isinstance(data, list) else []


def get_analyst_estimates(symbol: str, period: str = "annual", limit: int = 6) -> list[dict]:
    """Annual or quarterly analyst consensus estimates (revenue, EBITDA, EPS).

    Returns list sorted newest-first. Each dict has keys:
      symbol, date (fiscal year end), revenueLow/High/Avg,
      ebitdaLow/High/Avg, epsLow/High/Avg,
      netIncomeLow/High/Avg, numAnalystsRevenue, numAnalystsEps.
    """
    data = _get_stable("analyst-estimates", symbol=symbol, period=period, limit=limit)
    return data if isinstance(data, list) else []


def get_price_target_consensus(symbol: str) -> dict:
    """Aggregated price target consensus (high, low, consensus/mean, median).

    Returns dict with keys: symbol, targetHigh, targetLow,
    targetConsensus, targetMedian.
    """
    data = _get_stable("price-target-consensus", symbol=symbol)
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return {}


def get_price_targets(symbol: str, limit: int = 15) -> list[dict]:
    """Individual analyst price targets with firm/analyst name and date.

    Returns list sorted newest-first. Each dict has keys:
      symbol, publishedDate, analystName, analystCompany,
      priceTarget, priceWhenPosted, newsPublisher.
    """
    data = _get_stable("price-target-news", symbol=symbol, limit=limit)
    return data if isinstance(data, list) else []


def get_upgrades_downgrades(symbol: str, limit: int = 10) -> list[dict]:
    """Recent analyst grade changes (upgrades, downgrades, initiations, maintains).

    Returns list sorted newest-first. Each dict has keys:
      symbol, date, gradingCompany, previousGrade, newGrade,
      action (upgrade/downgrade/initiated/maintain/reiterated).
    """
    data = _get_stable("grades", symbol=symbol, limit=limit)
    return data if isinstance(data, list) else []
