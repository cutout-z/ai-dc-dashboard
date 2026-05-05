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

FMP_BASE = "https://financialmodelingprep.com/api"

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
    """Synchronous GET — used in ETL scripts and Streamlit (non-async context)."""
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
