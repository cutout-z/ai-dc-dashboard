"""Fast batch quote + returns fetcher using Yahoo Finance v8 spark API.

Ported from market-dashboard. Uses stdlib urllib (no httpx dependency).
Batches of 20 symbols per HTTP call, concurrent via ThreadPoolExecutor.
"""

import json
import logging
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

logger = logging.getLogger("ai_research")

_SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
_TIMEOUT = 15
_BATCH_SIZE = 20

PERIOD_DAYS = {
    "1D": 1,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
    "5Y": 1260,
    "10Y": 2500,
}

PERIOD_LABELS = list(PERIOD_DAYS.keys())


def _format_price(price: Optional[float]) -> Optional[float]:
    if price is None:
        return None
    if price < 1:
        return round(price, 4)
    elif price < 10:
        return round(price, 3)
    return round(price, 2)


def _fetch_spark_batch(symbols: list, time_range: str = "1y") -> dict:
    """Fetch spark data for a batch of up to 20 symbols."""
    try:
        params = urllib.parse.urlencode({
            "symbols": ",".join(symbols),
            "range": time_range,
            "interval": "1d",
        })
        url = f"{_SPARK_URL}?{params}"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning("Yahoo spark returned %d for %d symbols", resp.status, len(symbols))
                return {}
            data = json.loads(resp.read().decode())

        results = {}
        for sym, spark in data.items():
            if not isinstance(spark, dict):
                continue
            closes = spark.get("close") or []
            timestamps = spark.get("timestamp") or []
            if not closes:
                continue
            if timestamps and len(timestamps) == len(closes):
                clean = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
                if clean:
                    ts_clean, close_clean = zip(*clean)
                    results[sym] = {
                        "closes": list(close_clean),
                        "timestamps": list(ts_clean),
                        "chart_prev_close": spark.get("chartPreviousClose"),
                    }
            else:
                clean_closes = [c for c in closes if c is not None]
                if clean_closes:
                    results[sym] = {
                        "closes": clean_closes,
                        "timestamps": [],
                        "chart_prev_close": spark.get("chartPreviousClose"),
                    }
        return results
    except Exception as e:
        logger.warning("Yahoo spark batch failed: %s", e)
        return {}


def run_spark(symbols: list, time_range: str = "10y") -> dict:
    """Fetch spark data for all symbols, batched into groups of 20, concurrent."""
    if not symbols:
        return {}

    batches = [symbols[i:i + _BATCH_SIZE] for i in range(0, len(symbols), _BATCH_SIZE)]

    merged = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_spark_batch, batch, time_range): batch for batch in batches}
        for future in as_completed(futures):
            try:
                merged.update(future.result())
            except Exception as e:
                logger.warning("Spark batch error: %s", e)

    return merged


def compute_returns_from_closes(closes: list) -> dict:
    if len(closes) < 2:
        return {p: None for p in PERIOD_LABELS}
    current = closes[-1]
    returns = {}
    for label, days_back in PERIOD_DAYS.items():
        if len(closes) > days_back:
            past = closes[-(days_back + 1)]
            if past != 0:
                returns[label] = round(((current / past) - 1) * 100, 2)
            else:
                returns[label] = None
        else:
            returns[label] = None
    return returns
