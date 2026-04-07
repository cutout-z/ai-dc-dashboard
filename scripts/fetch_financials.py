"""
Fetch hyperscaler CAPEX + semi bellwether revenue from Yahoo Finance.
Stores quarterly time series in SQLite.
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


def fetch_quarterly_financials(ticker: str, name: str) -> list[dict]:
    """Fetch quarterly cash flow and income data for a ticker."""
    stock = yf.Ticker(ticker)
    records = []

    # Cash flow for CAPEX
    try:
        cf = stock.quarterly_cashflow
        if cf is not None and not cf.empty:
            for date_col in cf.columns:
                period = date_col.strftime("%Y-%m-%d") if hasattr(date_col, "strftime") else str(date_col)
                capex = None
                for label in ["Capital Expenditure", "CapitalExpenditure"]:
                    if label in cf.index:
                        val = cf.loc[label, date_col]
                        if pd.notna(val):
                            capex = abs(float(val))
                            break

                records.append({
                    "ticker": ticker,
                    "company": name,
                    "period": period,
                    "metric": "capex",
                    "value": capex,
                    "unit": "USD",
                    "source": "yahoo_finance",
                    "fetched_at": datetime.now().isoformat(),
                })
    except Exception as e:
        print(f"  Warning: cash flow fetch failed for {ticker}: {e}")

    # Income statement for revenue
    try:
        inc = stock.quarterly_income_stmt
        if inc is not None and not inc.empty:
            for date_col in inc.columns:
                period = date_col.strftime("%Y-%m-%d") if hasattr(date_col, "strftime") else str(date_col)
                revenue = None
                for label in ["Total Revenue", "TotalRevenue"]:
                    if label in inc.index:
                        val = inc.loc[label, date_col]
                        if pd.notna(val):
                            revenue = float(val)
                            break

                records.append({
                    "ticker": ticker,
                    "company": name,
                    "period": period,
                    "metric": "revenue",
                    "value": revenue,
                    "unit": "USD",
                    "source": "yahoo_finance",
                    "fetched_at": datetime.now().isoformat(),
                })
    except Exception as e:
        print(f"  Warning: income fetch failed for {ticker}: {e}")

    return records


def run():
    print("Fetching quarterly financials...")
    all_records = []

    for ticker, name in ALL_TICKERS.items():
        print(f"  {ticker} ({name})...")
        records = fetch_quarterly_financials(ticker, name)
        all_records.extend(records)
        print(f"    {len(records)} records")

    df = pd.DataFrame(all_records)

    # Drop rows where value is None
    df = df.dropna(subset=["value"])

    print(f"\nTotal: {len(df)} data points")

    # Write to SQLite
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("quarterly_financials", conn, if_exists="replace", index=False)

    # Create CAPEX summary view
    conn.execute("DROP VIEW IF EXISTS v_hyperscaler_capex")
    conn.execute("""
        CREATE VIEW v_hyperscaler_capex AS
        SELECT ticker, company, period, value as capex_usd
        FROM quarterly_financials
        WHERE metric = 'capex'
          AND ticker IN ('MSFT', 'GOOGL', 'AMZN', 'META')
        ORDER BY period DESC, ticker
    """)

    conn.execute("DROP VIEW IF EXISTS v_semi_revenue")
    conn.execute("""
        CREATE VIEW v_semi_revenue AS
        SELECT ticker, company, period, value as revenue_usd
        FROM quarterly_financials
        WHERE metric = 'revenue'
          AND ticker IN ('TSM', 'ASML', 'NVDA')
        ORDER BY period DESC, ticker
    """)

    conn.commit()
    conn.close()
    print(f"Written to {DB_PATH}")


if __name__ == "__main__":
    run()
