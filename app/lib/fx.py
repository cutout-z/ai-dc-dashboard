"""Historical FX rates via Yahoo Finance spark API.

Used to convert foreign-currency revenue (TWD, EUR) to USD using the rate
that applied on (or nearest to) each reporting date.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from app.lib.yahoo_spark import _fetch_spark_batch


@st.cache_data(ttl=86400, show_spinner=False)
def fx_daily_series(pair: str = "USDTWD=X", time_range: str = "10y") -> pd.Series:
    """Daily FX close series for a Yahoo pair ticker (e.g. 'USDTWD=X', 'USDEUR=X').

    Returns a pandas Series indexed by date (tz-naive) with close prices
    expressed as 'quote-currency per 1 USD'. E.g. USDTWD=X is TWD per USD.
    """
    data = _fetch_spark_batch([pair], time_range=time_range)
    entry = data.get(pair)
    if not entry or not entry.get("closes") or not entry.get("timestamps"):
        return pd.Series(dtype="float64")

    idx = pd.to_datetime(entry["timestamps"], unit="s").normalize()
    return pd.Series(entry["closes"], index=idx).sort_index()


def convert_to_usd(values: pd.Series, dates: pd.Series, pair: str) -> pd.Series:
    """Convert a Series of foreign-currency `values` to USD using pair FX closes.

    `dates` is a Series of datetimes aligned with `values`. For each date we
    use the most recent on-or-before FX close (forward-fill). Returns NaN
    for rows where no FX rate is available.
    """
    fx = fx_daily_series(pair)
    if fx.empty:
        return pd.Series([float("nan")] * len(values), index=values.index)

    # Reindex to the target dates using as-of join (nearest prior)
    d = pd.to_datetime(dates).dt.normalize()
    rates = fx.reindex(fx.index.union(d)).sort_index().ffill().reindex(d)
    rates.index = values.index
    return values / rates
