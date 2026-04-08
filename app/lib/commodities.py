"""DC / AI input commodities — prices and returns via Yahoo spark API."""

import streamlit as st

from app.lib.yahoo_spark import run_spark, compute_returns_from_closes, _format_price

DC_COMMODITIES = {
    "Energy": [
        {"symbol": "NG=F",  "name": "Natural Gas (Henry Hub)", "relevance": "Primary US DC power fuel"},
        {"symbol": "TTF=F", "name": "Dutch TTF Gas",           "relevance": "European DC power cost driver"},
        {"symbol": "CL=F",  "name": "WTI Crude Oil",           "relevance": "General energy benchmark"},
        {"symbol": "URA",   "name": "Uranium ETF",             "relevance": "Nuclear baseload for DC power"},
    ],
    "Metals & Materials": [
        {"symbol": "HG=F",  "name": "Copper",          "relevance": "Electrical infrastructure, cabling"},
        {"symbol": "ALI=F", "name": "Aluminum",         "relevance": "Heat sinks, enclosures, racks"},
        {"symbol": "LIT",   "name": "Lithium ETF",      "relevance": "Backup battery storage"},
        {"symbol": "REMX",  "name": "Rare Earths ETF",  "relevance": "GPU/chip manufacturing inputs"},
        {"symbol": "SLX",   "name": "Steel ETF",        "relevance": "DC structural construction"},
    ],
    "Semiconductor Proxies": [
        {"symbol": "SOXX", "name": "iShares Semiconductor ETF", "relevance": "Chip supply chain sentiment"},
        {"symbol": "SMH",  "name": "VanEck Semiconductor ETF",  "relevance": "Alternative semi proxy"},
    ],
    "Power & Utility": [
        {"symbol": "XLU", "name": "Utilities Select Sector SPDR", "relevance": "DC power cost proxy"},
    ],
}

# Flat list of all symbols for batch fetching
ALL_SYMBOLS = [item["symbol"] for group in DC_COMMODITIES.values() for item in group]

# Key commodities for the metrics row
KEY_METRICS = ["NG=F", "HG=F", "URA", "SOXX"]


@st.cache_data(ttl=600)
def fetch_commodity_overview() -> dict:
    """Fetch all DC/AI commodity prices and returns."""
    spark_data = run_spark(ALL_SYMBOLS, time_range="5y")

    result = {}
    for category, items in DC_COMMODITIES.items():
        cat_data = []
        for item in items:
            sym = item["symbol"]
            sd = spark_data.get(sym)

            if sd and sd["closes"] and len(sd["closes"]) >= 2:
                price = sd["closes"][-1]
                prev = sd["closes"][-2]
                change_pct = round((price / prev - 1) * 100, 2) if prev else None
                returns = compute_returns_from_closes(sd["closes"])
                closes = sd["closes"]
                timestamps = sd.get("timestamps", [])
            else:
                price = None
                change_pct = None
                returns = {}
                closes = []
                timestamps = []

            cat_data.append({
                **item,
                "price": _format_price(price),
                "change_pct": change_pct,
                "returns": returns,
                "closes": closes,
                "timestamps": timestamps,
            })
        result[category] = cat_data

    return result
