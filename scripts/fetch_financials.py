"""
Fetch hyperscaler CAPEX + semi bellwether revenue from Yahoo Finance.
Stores quarterly and annual time series in SQLite.
"""

import sqlite3
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"

# Hyperscalers — the core CAPEX signal
HYPERSCALERS = {
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
}

# Semi bellwethers — demand signal
SEMI_BELLWETHERS = {
    "TSM": "TSMC",
    "ASML": "ASML",
    "NVDA": "NVIDIA",
}

ALL_TICKERS = {**HYPERSCALERS, **SEMI_BELLWETHERS}


def _extract_capex(cf_df, date_col) :
    """Extract CAPEX value from a cash flow DataFrame column."""
    for label in ["Capital Expenditure", "CapitalExpenditure"]:
        if label in cf_df.index:
            val = cf_df.loc[label, date_col]
            if pd.notna(val):
                return abs(float(val))
    return None


def _extract_revenue(inc_df, date_col) :
    """Extract revenue from an income statement DataFrame column."""
    for label in ["Total Revenue", "TotalRevenue"]:
        if label in inc_df.index:
            val = inc_df.loc[label, date_col]
            if pd.notna(val):
                return float(val)
    return None


def fetch_quarterly_financials(ticker: str, name: str) -> list[dict]:
    """Fetch quarterly cash flow and income data for a ticker."""
    stock = yf.Ticker(ticker)
    records = []
    now = datetime.now().isoformat()

    # Quarterly cash flow for CAPEX
    try:
        cf = stock.quarterly_cashflow
        if cf is not None and not cf.empty:
            for date_col in cf.columns:
                period = date_col.strftime("%Y-%m-%d") if hasattr(date_col, "strftime") else str(date_col)
                capex = _extract_capex(cf, date_col)
                records.append({
                    "ticker": ticker, "company": name, "period": period,
                    "metric": "capex", "frequency": "quarterly",
                    "value": capex, "unit": "USD", "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        print(f"  Warning: quarterly cash flow failed for {ticker}: {e}")

    # Quarterly income for revenue
    try:
        inc = stock.quarterly_income_stmt
        if inc is not None and not inc.empty:
            for date_col in inc.columns:
                period = date_col.strftime("%Y-%m-%d") if hasattr(date_col, "strftime") else str(date_col)
                revenue = _extract_revenue(inc, date_col)
                records.append({
                    "ticker": ticker, "company": name, "period": period,
                    "metric": "revenue", "frequency": "quarterly",
                    "value": revenue, "unit": "USD", "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        print(f"  Warning: quarterly income failed for {ticker}: {e}")

    # Annual cash flow for CAPEX (longer history)
    try:
        cf_annual = stock.cashflow
        if cf_annual is not None and not cf_annual.empty:
            for date_col in cf_annual.columns:
                period = date_col.strftime("%Y-%m-%d") if hasattr(date_col, "strftime") else str(date_col)
                capex = _extract_capex(cf_annual, date_col)
                records.append({
                    "ticker": ticker, "company": name, "period": period,
                    "metric": "capex", "frequency": "annual",
                    "value": capex, "unit": "USD", "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        print(f"  Warning: annual cash flow failed for {ticker}: {e}")

    # Annual income for revenue
    try:
        inc_annual = stock.income_stmt
        if inc_annual is not None and not inc_annual.empty:
            for date_col in inc_annual.columns:
                period = date_col.strftime("%Y-%m-%d") if hasattr(date_col, "strftime") else str(date_col)
                revenue = _extract_revenue(inc_annual, date_col)
                records.append({
                    "ticker": ticker, "company": name, "period": period,
                    "metric": "revenue", "frequency": "annual",
                    "value": revenue, "unit": "USD", "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        print(f"  Warning: annual income failed for {ticker}: {e}")

    return records


def run():
    print("Fetching quarterly + annual financials...")
    all_records = []

    for ticker, name in ALL_TICKERS.items():
        print(f"  {ticker} ({name})...")
        records = fetch_quarterly_financials(ticker, name)
        all_records.extend(records)
        print(f"    {len(records)} records")

    df = pd.DataFrame(all_records)
    df = df.dropna(subset=["value"])

    quarterly = df[df["frequency"] == "quarterly"]
    annual = df[df["frequency"] == "annual"]
    print(f"\nTotal: {len(df)} data points ({len(quarterly)} quarterly, {len(annual)} annual)")

    # Write to SQLite
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("quarterly_financials", conn, if_exists="replace", index=False)

    # Create views
    conn.execute("DROP VIEW IF EXISTS v_hyperscaler_capex")
    conn.execute("""
        CREATE VIEW v_hyperscaler_capex AS
        SELECT ticker, company, period, value as capex_usd
        FROM quarterly_financials
        WHERE metric = 'capex'
          AND frequency = 'quarterly'
          AND ticker IN ('MSFT', 'GOOGL', 'AMZN', 'META')
        ORDER BY period DESC, ticker
    """)

    conn.execute("DROP VIEW IF EXISTS v_hyperscaler_capex_annual")
    conn.execute("""
        CREATE VIEW v_hyperscaler_capex_annual AS
        SELECT ticker, company, period, value as capex_usd
        FROM quarterly_financials
        WHERE metric = 'capex'
          AND frequency = 'annual'
          AND ticker IN ('MSFT', 'GOOGL', 'AMZN', 'META')
        ORDER BY period DESC, ticker
    """)

    conn.execute("DROP VIEW IF EXISTS v_semi_revenue")
    conn.execute("""
        CREATE VIEW v_semi_revenue AS
        SELECT ticker, company, period, value as revenue_usd
        FROM quarterly_financials
        WHERE metric = 'revenue'
          AND frequency = 'quarterly'
          AND ticker IN ('TSM', 'ASML', 'NVDA')
        ORDER BY period DESC, ticker
    """)

    conn.commit()
    conn.close()
    print(f"Written to {DB_PATH}")


if __name__ == "__main__":
    run()
