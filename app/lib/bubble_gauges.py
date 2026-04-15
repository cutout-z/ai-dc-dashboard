"""Bubble risk gauges — 5-gauge framework inspired by boomorbubble.ai.

Framework: Azeem Azhar (Exponential View) AI Bubble Dashboard.
Each gauge uses a traffic-light system (green / amber / red).
Rule: 0–1 red = BOOM; 2 red = CAUTION; 3+ red = BUBBLE territory.

Sources:
    boomorbubble.ai, Exponential View (Azeem Azhar & Nathan Warren)
    Historical benchmarks from BEA, FCC, Shiller, Bloomberg, LBNL, S&P Dow Jones

Each gauge returns a dict:
    name, value, value_fmt, unit, zone, direction, benchmark, detail
"""

import logging
import sqlite3
from math import log as ln
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "reference"


# ── Helpers ──────────────────────────────────────────────────

def _zone(value: float, green_max: float, amber_max: float) -> str:
    """Green if value <= green_max, amber if <= amber_max, else red."""
    if value <= green_max:
        return "green"
    if value <= amber_max:
        return "amber"
    return "red"


def _direction(current: float, previous: float | None, lower_is_better: bool = True) -> str:
    if previous is None or previous == 0:
        return "stable"
    delta_pct = (current - previous) / abs(previous)
    if abs(delta_pct) < 0.05:
        return "stable"
    if lower_is_better:
        return "improving" if current < previous else "worsening"
    return "worsening" if current < previous else "improving"


def _empty(name: str, unit: str, benchmark: str) -> dict:
    return {
        "name": name, "value": None, "value_fmt": "N/A", "unit": unit,
        "zone": "gray", "direction": "stable",
        "benchmark": benchmark, "detail": "Insufficient data",
    }


# ── 1. Economic Strain ──────────────────────────────────────

def economic_strain(db_path: str) -> dict:
    """Trailing 4Q hyperscaler CAPEX as % of US GDP.

    Green: <1.2%  |  Amber: 1.2–2.0%  |  Red: >2.0%
    Benchmark: US telecom boom peaked at ~1.3% of GDP (2000).
    """
    conn = sqlite3.connect(db_path)
    try:
        capex = conn.execute("""
            SELECT SUM(capex_usd)/1e9 FROM v_hyperscaler_capex
            WHERE period >= (SELECT DATE(MAX(period), '-1 year') FROM v_hyperscaler_capex)
        """).fetchone()[0]
        capex_prev = conn.execute("""
            SELECT SUM(capex_usd)/1e9 FROM v_hyperscaler_capex
            WHERE period >= (SELECT DATE(MAX(period), '-2 year') FROM v_hyperscaler_capex)
              AND period < (SELECT DATE(MAX(period), '-1 year') FROM v_hyperscaler_capex)
        """).fetchone()[0]
    finally:
        conn.close()

    gdp_path = DATA_DIR / "us_gdp_annual.csv"
    gdp_bn, gdp_year = None, None
    if gdp_path.exists():
        df = pd.read_csv(gdp_path)
        if not df.empty:
            row = df.sort_values("year").iloc[-1]
            gdp_bn = float(row["gdp_nominal_bn"])
            gdp_year = int(row["year"])

    if not capex or not gdp_bn:
        return _empty("Economic Strain", "% of GDP", "Telecom peak: 1.3% (2000)")

    pct = capex / gdp_bn * 100
    prev_pct = (capex_prev / gdp_bn * 100) if capex_prev else None

    return {
        "name": "Economic Strain",
        "value": pct,
        "value_fmt": f"{pct:.1f}%",
        "unit": "% of GDP",
        "zone": _zone(pct, 1.2, 2.0),
        "direction": _direction(pct, prev_pct),
        "benchmark": f"Telecom peak: 1.3% (2000). GDP: {gdp_year} ${gdp_bn / 1000:.1f}T",
        "detail": f"T4Q CAPEX ${capex:.0f}B ÷ GDP ${gdp_bn / 1000:.1f}T",
    }


# ── 2. Industry Strain ──────────────────────────────────────

def _parse_ai_revenue() -> tuple[float, float]:
    """Return (frontier_lab_arr_bn, cloud_ai_rev_bn) from reference CSVs."""
    lab_arr = 0.0
    val_path = DATA_DIR / "frontier_lab_valuations.csv"
    if val_path.exists():
        df = pd.read_csv(val_path)
        df_arr = df[df["metric"] == "arr"].sort_values("date")
        for company in df_arr["company"].unique():
            latest = df_arr[df_arr["company"] == company].iloc[-1]
            lab_arr += float(latest["value"])

    cloud_ai = 0.0
    supp_path = DATA_DIR / "ai_supplement.csv"
    if supp_path.exists():
        df_s = pd.read_csv(supp_path)
        for _, row in df_s.iterrows():
            desc = str(row.get("Metric Description", ""))
            if "AI" in desc and "%" not in desc:
                val_str = str(row.get("FY2025E", ""))
                val_str = val_str.replace(">", "").replace(",", "").replace('"', "").strip()
                try:
                    cloud_ai += float(val_str) / 1000  # CSV values in $M → $B
                except (ValueError, TypeError):
                    pass

    return lab_arr, cloud_ai


def _parse_prior_lab_arr(months_back: int = 12) -> float:
    """Get combined frontier lab ARR from ~N months ago."""
    val_path = DATA_DIR / "frontier_lab_valuations.csv"
    if not val_path.exists():
        return 0.0
    df = pd.read_csv(val_path)
    df_arr = df[df["metric"] == "arr"].copy()
    df_arr["date"] = pd.to_datetime(df_arr["date"])
    latest_date = df_arr["date"].max()
    target = latest_date - pd.DateOffset(months=months_back)

    total = 0.0
    for company in df_arr["company"].unique():
        dc = df_arr[df_arr["company"] == company].copy()
        dc["delta"] = abs(dc["date"] - target)
        closest = dc.sort_values("delta").iloc[0]
        if closest["delta"].days < 180:
            total += float(closest["value"])
    return total


def industry_strain(db_path: str) -> dict:
    """AI CAPEX ÷ AI end-customer revenue.

    Revenue = frontier lab ARR + cloud AI services revenue.
    NVIDIA GPU revenue excluded (supply-chain transfer, not end-customer).

    Green: <3x  |  Amber: 3–5x  |  Red: >5x
    Benchmark: Telecom CAPEX/revenue peaked at ~4x (2001).
    """
    conn = sqlite3.connect(db_path)
    try:
        capex = conn.execute("""
            SELECT SUM(capex_usd)/1e9 FROM v_hyperscaler_capex
            WHERE period >= (SELECT DATE(MAX(period), '-1 year') FROM v_hyperscaler_capex)
        """).fetchone()[0]
        capex_prev = conn.execute("""
            SELECT SUM(capex_usd)/1e9 FROM v_hyperscaler_capex
            WHERE period >= (SELECT DATE(MAX(period), '-2 year') FROM v_hyperscaler_capex)
              AND period < (SELECT DATE(MAX(period), '-1 year') FROM v_hyperscaler_capex)
        """).fetchone()[0]
    finally:
        conn.close()

    lab_arr, cloud_ai = _parse_ai_revenue()
    ai_rev = lab_arr + cloud_ai

    if not capex or ai_rev == 0:
        return _empty("Industry Strain", "x ratio", "Telecom peak: 4.0x (2001)")

    ratio = capex / ai_rev

    # Direction: compare to prior-year ratio
    prior_lab = _parse_prior_lab_arr(12)
    prev_ratio = None
    if capex_prev and prior_lab > 0:
        prev_ratio = capex_prev / prior_lab  # conservative (cloud AI wasn't disclosed 12m ago)

    return {
        "name": "Industry Strain",
        "value": ratio,
        "value_fmt": f"{ratio:.1f}x",
        "unit": "x ratio",
        "zone": _zone(ratio, 3.0, 5.0),
        "direction": _direction(ratio, prev_ratio),
        "benchmark": "Telecom peak: 4.0x (2001)",
        "detail": f"CAPEX ${capex:.0f}B ÷ AI Rev ${ai_rev:.0f}B (Labs ${lab_arr:.0f}B + Cloud ${cloud_ai:.0f}B)",
    }


# ── 3. Revenue Momentum ─────────────────────────────────────

def revenue_momentum() -> dict:
    """AI revenue doubling time (years) from frontier lab ARR trajectory.

    Green: <1.0yr  |  Amber: 1.0–2.0yr  |  Red: >2.0yr
    Faster doubling = healthier (revenue catching up to investment).
    """
    val_path = DATA_DIR / "frontier_lab_valuations.csv"
    if not val_path.exists():
        return _empty("Revenue Momentum", "yr doubling", "Healthy: <1yr doubling")

    df = pd.read_csv(val_path)
    df_arr = df[df["metric"] == "arr"].copy()
    df_arr["date"] = pd.to_datetime(df_arr["date"])

    if len(df_arr) < 4:
        return _empty("Revenue Momentum", "yr doubling", "Healthy: <1yr doubling")

    # Combined ARR by month
    df_arr["month"] = df_arr["date"].dt.to_period("M")
    combined = df_arr.groupby("month")["value"].sum().reset_index()
    combined["date"] = combined["month"].dt.to_timestamp()
    combined = combined.sort_values("date")

    if len(combined) < 2:
        return _empty("Revenue Momentum", "yr doubling", "Healthy: <1yr doubling")

    latest = combined.iloc[-1]
    target_date = latest["date"] - pd.DateOffset(months=12)
    combined["delta"] = abs(combined["date"] - target_date)
    prior = combined.sort_values("delta").iloc[0]

    if prior["value"] <= 0 or latest["value"] <= prior["value"]:
        return _empty("Revenue Momentum", "yr doubling", "Healthy: <1yr doubling")

    months_elapsed = (latest["date"] - prior["date"]).days / 30.44
    if months_elapsed <= 0:
        return _empty("Revenue Momentum", "yr doubling", "Healthy: <1yr doubling")

    growth_factor = latest["value"] / prior["value"]
    doubling_months = months_elapsed * ln(2) / ln(growth_factor)
    doubling_years = doubling_months / 12

    return {
        "name": "Revenue Momentum",
        "value": doubling_years,
        "value_fmt": f"{doubling_years:.1f}yr",
        "unit": "yr doubling",
        "zone": _zone(doubling_years, 1.0, 2.0),
        "direction": "stable",
        "benchmark": f"Combined ARR: ${latest['value']:.0f}B (was ${prior['value']:.0f}B {months_elapsed:.0f}mo ago)",
        "detail": f"Frontier lab ARR doubling every {doubling_months:.0f} months",
    }


# ── 4. Valuation Heat ───────────────────────────────────────

def valuation_heat() -> dict:
    """Nasdaq-100 trailing PE vs historical peaks.

    Uses QQQ ETF as live proxy.
    Green: <30x  |  Amber: 30–40x  |  Red: >40x
    Benchmark: Dot-com peak ~175x (Mar 2000). Pre-COVID baseline ~25x (2019).
    """
    pe = None
    source = ""
    try:
        import yfinance as yf
        qqq = yf.Ticker("QQQ")
        info = qqq.info
        pe = info.get("trailingPE")
        if pe:
            source = "QQQ trailing PE"
    except Exception as e:
        log.warning("yfinance QQQ fetch failed: %s", e)

    if not pe:
        return _empty("Valuation Heat", "x PE", "Dot-com peak: 175x (2000)")

    return {
        "name": "Valuation Heat",
        "value": pe,
        "value_fmt": f"{pe:.0f}x",
        "unit": "x PE",
        "zone": _zone(pe, 30, 40),
        "direction": "stable",
        "benchmark": "Dot-com peak: 175x (2000). Pre-COVID: 25x (2019)",
        "detail": f"{source}: {pe:.1f}x",
    }


# ── 5. Funding Quality ──────────────────────────────────────

def funding_quality() -> dict:
    """AI funding mix — debt share + circular financing prevalence.

    Circular = investor is also a major customer/supplier (e.g. Nvidia investing
    in companies that buy Nvidia GPUs).

    Green: <30% debt, ≤1 circular  |  Amber: 30–50% debt OR 2 circular  |  Red: >50% debt OR 3+ circular
    """
    deals_path = DATA_DIR / "funding_deals.csv"
    if not deals_path.exists():
        return _empty("Funding Quality", "score", "Dot-com: 50% of IPOs below issue within 2yr")

    df = pd.read_csv(deals_path)
    if df.empty:
        return _empty("Funding Quality", "score", "Dot-com: 50% of IPOs below issue within 2yr")

    # Exclude mega-commitments (hybrid) — count deployed capital only
    df_deployed = df[df["type"] != "hybrid"].copy()
    total = df_deployed["amount_bn"].sum()
    debt = df_deployed[df_deployed["type"] == "debt"]["amount_bn"].sum()
    circular_count = int(df_deployed["is_circular"].astype(bool).sum())
    total_deals = len(df_deployed)

    debt_pct = (debt / total * 100) if total > 0 else 0

    debt_zone = _zone(debt_pct, 30, 50)
    circ_zone = "green" if circular_count <= 1 else ("amber" if circular_count <= 2 else "red")
    zone_order = {"green": 0, "amber": 1, "red": 2}
    worst = max(debt_zone, circ_zone, key=lambda z: zone_order[z])

    return {
        "name": "Funding Quality",
        "value": debt_pct,
        "value_fmt": f"{debt_pct:.0f}% debt",
        "unit": "% debt-funded",
        "zone": worst,
        "direction": "worsening",
        "benchmark": f"{circular_count} circular deals out of {total_deals} tracked",
        "detail": f"${debt:.0f}B debt / ${total:.0f}B total ({debt_pct:.0f}%). "
                  f"{circular_count} circular financing arrangements.",
    }


# ── Aggregate ────────────────────────────────────────────────

ZONE_COLORS = {
    "green": "#22c55e",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "gray": "#6b7280",
}

DIRECTION_ARROWS = {
    "improving": "↓",
    "stable": "→",
    "worsening": "↑",
}


def all_gauges(db_path: str) -> list[dict]:
    """Compute all 5 gauges."""
    results = []
    for fn in [
        lambda: economic_strain(db_path),
        lambda: industry_strain(db_path),
        revenue_momentum,
        valuation_heat,
        lambda: funding_quality(),
    ]:
        try:
            results.append(fn())
        except Exception as e:
            log.error("Gauge computation failed: %s", e)
            results.append(_empty("Error", "", str(e)))
    return results


def overall_assessment(gauges: list[dict]) -> dict:
    """Overall boom/bubble classification.

    0–1 red = BOOM (healthy expansion)
    2 red   = CAUTION (warning signs emerging)
    3+ red  = BUBBLE (elevated risk)
    """
    reds = sum(1 for g in gauges if g["zone"] == "red")
    ambers = sum(1 for g in gauges if g["zone"] == "amber")

    if reds >= 3:
        return {"label": "BUBBLE", "color": "#ef4444",
                "detail": f"{reds} red, {ambers} amber — elevated risk"}
    if reds >= 2:
        return {"label": "CAUTION", "color": "#f59e0b",
                "detail": f"{reds} red, {ambers} amber — warning signs emerging"}
    return {"label": "BOOM", "color": "#22c55e",
            "detail": f"{reds} red, {ambers} amber — healthy expansion"}
