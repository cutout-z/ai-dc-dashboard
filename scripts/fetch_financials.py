"""
Fetch AI & DC CAPEX + semi bellwether revenue from Yahoo Finance.
Stores quarterly and annual time series in SQLite.
"""

import sqlite3
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "ai_research.db"

# All companies tracked for CAPEX
CAPEX_COMPANIES = {
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
    "ORCL": "Oracle",
    "CRWV": "CoreWeave",
    "AAPL": "Apple",
}

# Semi bellwethers — revenue demand signal
SEMI_BELLWETHERS = {
    "TSM": "TSMC",
    "ASML": "ASML",
    "NVDA": "NVIDIA",
}

ALL_TICKERS = {**CAPEX_COMPANIES, **SEMI_BELLWETHERS}


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


def _load_seed_data() -> pd.DataFrame:
    """Load historical quarterly CAPEX from seed CSV (extends yfinance's ~6-quarter limit)."""
    seed_path = Path(__file__).parent.parent / "data" / "reference" / "capex_quarterly_seed.csv"
    if not seed_path.exists():
        return pd.DataFrame()

    df_seed = pd.read_csv(seed_path)
    now = datetime.now().isoformat()
    records = []
    for _, row in df_seed.iterrows():
        records.append({
            "ticker": row["ticker"],
            "company": row["company"],
            "period": row["period"],
            "metric": "capex",
            "frequency": "quarterly",
            "value": abs(float(row["capex_usd"])),
            "unit": "USD",
            "source": f"seed/{row.get('source', 'manual')}",
            "fetched_at": now,
        })
    print(f"  Loaded {len(records)} seed records")
    return pd.DataFrame(records)


def run():
    print("Fetching quarterly + annual financials...")
    all_records = []

    for ticker, name in ALL_TICKERS.items():
        print(f"  {ticker} ({name})...")
        records = fetch_quarterly_financials(ticker, name)
        all_records.extend(records)
        print(f"    {len(records)} records")

    df_api = pd.DataFrame(all_records)
    df_api = df_api.dropna(subset=["value"])

    # Load seed data for historical quarterly CAPEX (back to 2021)
    print("Loading seed data...")
    df_seed = _load_seed_data()

    # Merge: assign calendar quarter key, prefer API data over seed for overlaps
    if not df_seed.empty:
        for df in [df_api, df_seed]:
            df["_quarter"] = pd.to_datetime(df["period"]).dt.to_period("Q").astype(str)

        # API data wins on overlap (ticker + quarter + metric + frequency)
        merge_key = ["ticker", "_quarter", "metric", "frequency"]
        api_keys = set(df_api[merge_key].apply(tuple, axis=1))
        seed_mask = ~df_seed[merge_key].apply(tuple, axis=1).isin(api_keys)
        df_seed_new = df_seed[seed_mask]
        print(f"  {len(df_seed_new)} seed records fill historical gaps")

        df = pd.concat([df_api, df_seed_new], ignore_index=True)
        df = df.drop(columns=["_quarter"])
    else:
        df = df_api

    quarterly = df[df["frequency"] == "quarterly"]
    annual = df[df["frequency"] == "annual"]
    print(f"\nTotal: {len(df)} data points ({len(quarterly)} quarterly, {len(annual)} annual)")

    # Write to SQLite
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("quarterly_financials", conn, if_exists="replace", index=False)

    # Create views — all CAPEX-tracked companies
    capex_tickers = ", ".join(f"'{t}'" for t in CAPEX_COMPANIES)

    conn.execute("DROP VIEW IF EXISTS v_hyperscaler_capex")
    conn.execute(f"""
        CREATE VIEW v_hyperscaler_capex AS
        SELECT ticker, company, period, value as capex_usd
        FROM quarterly_financials
        WHERE metric = 'capex'
          AND frequency = 'quarterly'
          AND ticker IN ({capex_tickers})
        ORDER BY period DESC, ticker
    """)

    conn.execute("DROP VIEW IF EXISTS v_hyperscaler_capex_annual")
    conn.execute(f"""
        CREATE VIEW v_hyperscaler_capex_annual AS
        SELECT ticker, company, period, value as capex_usd
        FROM quarterly_financials
        WHERE metric = 'capex'
          AND frequency = 'annual'
          AND ticker IN ({capex_tickers})
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
