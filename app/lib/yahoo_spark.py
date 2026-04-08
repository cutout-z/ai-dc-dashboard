"""Fast batch quote + returns fetcher using Yahoo Finance v8 spark API.

Ported from market-dashboard. Batches of 20 symbols per HTTP call, all async.
"""

import asyncio
import logging

import httpx

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


def _format_price(price: float | None) -> float | None:
    if price is None:
        return None
    if price < 1:
        return round(price, 4)
    elif price < 10:
        return round(price, 3)
    return round(price, 2)


async def _fetch_spark_batch(client: httpx.AsyncClient, symbols: list[str],
                              time_range: str = "1y") -> dict[str, dict]:
    try:
        resp = await client.get(_SPARK_URL, params={
            "symbols": ",".join(symbols),
            "range": time_range,
            "interval": "1d",
        })
        if resp.status_code != 200:
            logger.warning("Yahoo spark returned %d for %d symbols", resp.status_code, len(symbols))
            return {}

        data = resp.json()
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


async def fetch_all_spark(symbols: list[str], time_range: str = "1y") -> dict[str, dict]:
    if not symbols:
        return {}
    batches = [symbols[i:i + _BATCH_SIZE] for i in range(0, len(symbols), _BATCH_SIZE)]
    async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT) as client:
        tasks = [_fetch_spark_batch(client, batch, time_range) for batch in batches]
        batch_results = await asyncio.gather(*tasks)
    merged = {}
    for result in batch_results:
        merged.update(result)
    return merged


def compute_returns_from_closes(closes: list[float]) -> dict[str, float | None]:
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


def run_spark(symbols: list[str], time_range: str = "10y") -> dict[str, dict]:
    """Sync wrapper for fetch_all_spark — safe to call from Streamlit."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, fetch_all_spark(symbols, time_range))
            return future.result()
    return asyncio.run(fetch_all_spark(symbols, time_range))
