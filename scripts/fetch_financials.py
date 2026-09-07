"""
Fetch AI & DC CAPEX + semi bellwether revenue from Yahoo Finance.
Stores quarterly and annual time series in SQLite.
"""

import sqlite3
from collections.abc import Callable

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

# Reporting currency per ticker (yfinance returns values in the company's native currency)
REPORTING_CURRENCY = {
    "MSFT": "USD", "GOOGL": "USD", "AMZN": "USD", "META": "USD",
    "ORCL": "USD", "CRWV": "USD", "AAPL": "USD",
    "NVDA": "USD",  # reports in USD
    "TSM": "TWD",   # TSMC reports in New Taiwan Dollar
    "ASML": "EUR",  # ASML reports in Euro
}


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


def fetch_quarterly_financials(
    ticker: str,
    name: str,
    on_error: Callable[[str], None] | None = None,
) -> list[dict]:
    """Fetch quarterly cash flow and income data for a ticker.

    Endpoint failures are reported via ``on_error`` (called with a one-line
    message) instead of being swallowed as printed warnings; the publisher
    treats any reported failure as a degraded run and aborts publication.
    Without ``on_error`` the legacy print-a-warning behaviour is kept.
    """

    def _report(message: str) -> None:
        if on_error is not None:
            on_error(message)
        else:
            print(f"  Warning: {message}")

    stock = yf.Ticker(ticker)
    records = []
    now = datetime.now().isoformat()

    currency = REPORTING_CURRENCY.get(ticker, "USD")

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
                    "value": capex, "unit": currency, "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        _report(f"{ticker}: quarterly cash flow endpoint failed: {e}")

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
                    "value": revenue, "unit": currency, "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        _report(f"{ticker}: quarterly income endpoint failed: {e}")

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
                    "value": capex, "unit": currency, "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        _report(f"{ticker}: annual cash flow endpoint failed: {e}")

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
                    "value": revenue, "unit": currency, "source": "yahoo_finance",
                    "fetched_at": now,
                })
    except Exception as e:
        _report(f"{ticker}: annual income endpoint failed: {e}")

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


class PublishValidationError(Exception):
    """Candidate dataset failed validation; publication aborted (S2-03)."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def run(conn=None) -> dict:
    """Fetch, validate, then merge into the existing series (S2-03).

    Last-good keyed observations are preserved: a candidate row replaces an
    existing (ticker, period, metric, frequency) row only when the candidate
    itself is valid. Any endpoint failure or completeness regression aborts
    publication, leaving the previous table untouched.
    """
    print("Fetching quarterly + annual financials...")
    all_records = []
    endpoint_failures: list[str] = []

    for ticker, name in ALL_TICKERS.items():
        print(f"  {ticker} ({name})...")
        records = fetch_quarterly_financials(ticker, name, on_error=endpoint_failures.append)
        all_records.extend(records)
        print(f"    {len(records)} records")

    df_api = pd.DataFrame(all_records)
    if not df_api.empty:
        df_api = df_api.dropna(subset=["value"])

    # Load seed data for historical quarterly CAPEX (back to 2021)
    print("Loading seed data...")
    df_seed = _load_seed_data()

    # Merge: assign calendar quarter key, prefer API data over seed for overlaps
    if not df_seed.empty:
        if not df_api.empty:
            df_api["_quarter"] = pd.to_datetime(df_api["period"]).dt.to_period("Q").astype(str)
        df_seed["_quarter"] = pd.to_datetime(df_seed["period"]).dt.to_period("Q").astype(str)

        # API data wins on overlap (ticker + quarter + metric + frequency)
        merge_key = ["ticker", "_quarter", "metric", "frequency"]
        api_keys = (
            set(df_api[merge_key].apply(tuple, axis=1)) if not df_api.empty else set()
        )
        seed_mask = ~df_seed[merge_key].apply(tuple, axis=1).isin(api_keys)
        df_seed_new = df_seed[seed_mask]
        print(f"  {len(df_seed_new)} seed records fill historical gaps")

        df = pd.concat([df_api, df_seed_new], ignore_index=True)
        if "_quarter" in df.columns:
            df = df.drop(columns=["_quarter"])
    else:
        df = df_api

    quarterly = df[df["frequency"] == "quarterly"] if not df.empty else df
    annual = df[df["frequency"] == "annual"] if not df.empty else df
    print(f"\nTotal: {len(df)} data points ({len(quarterly)} quarterly, {len(annual)} annual)")

    # --- S2-03: transactional publish — keep last-good on any failure --------
    close_conn = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        close_conn = True
    try:
        existing = (
            pd.read_sql("SELECT * FROM quarterly_financials", conn)
            if _table_exists(conn, "quarterly_financials")
            else pd.DataFrame()
        )

        # Validate the candidate transaction before publication.
        problems: list[str] = []
        problems.extend(endpoint_failures)
        if df.empty:
            problems.append("candidate dataset is empty")
        elif not existing.empty:
            # Grouping below needs the standard schema even when every
            # endpoint came back empty (no columns -> no group keys).
            if not set(["ticker", "metric", "frequency"]).issubset(df.columns):
                problems.append(
                    "candidate has no usable schema columns; refusing to publish"
                )
            else:
                cand_groups = df.groupby(["ticker", "metric", "frequency"]).size()
                prev_groups = existing.groupby(["ticker", "metric", "frequency"]).size()
                for key, prev_count in prev_groups.items():
                    if key[0] not in ALL_TICKERS:
                        # Rows from explicitly retired tickers keep flowing through
                        # untouched; only tracked tickers are validated.
                        continue
                    cand_count = int(cand_groups.get(key, 0))
                    if cand_count == 0:
                        if not endpoint_failures:
                            problems.append(
                                f"{key}: series vanished entirely "
                                f"({prev_count} rows -> 0) with no reported fetch failure"
                            )
                        # With a reported endpoint failure the run is already
                        # degraded and will abort below.
                    elif cand_count < prev_count * 0.5:
                        problems.append(
                            f"{key}: candidate lost >50% of observations "
                            f"({prev_count} -> {cand_count})"
                        )

        if problems:
            raise PublishValidationError(problems)

        # Upsert by (ticker, period, metric, frequency): candidate rows win on
        # key overlap; stored rows the candidate does not cover are preserved
        # as last-good observations.
        if not existing.empty:
            existing = existing[df.columns.intersection(existing.columns)]
            key_cols = ["ticker", "period", "metric", "frequency"]
            cand_keys = set(map(tuple, df[key_cols].drop_duplicates().values.tolist()))
            kept = existing[~existing[key_cols].apply(tuple, axis=1).isin(cand_keys)]
            df = pd.concat([df, kept], ignore_index=True)[df.columns]

        # Guard the final table against duplicate publish keys regardless of
        # whether existing history was merged back in.
        key_cols = ["ticker", "period", "metric", "frequency"]
        df = df.drop_duplicates(subset=key_cols, keep="last").reset_index(drop=True)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quarterly_financials (
                ticker TEXT, company TEXT, period TEXT, metric TEXT,
                frequency TEXT, value REAL, unit TEXT, source TEXT, fetched_at TEXT
            )
            """
        )
        conn.execute("DELETE FROM quarterly_financials")
        df.to_sql("quarterly_financials", conn, if_exists="append", index=False)
        conn.commit()
        _create_views(conn)
    except PublishValidationError as exc:
        # Partial failure -> keep old series; publication aborted (degraded).
        conn.rollback()
        print("PUBLICATION ABORTED — previous series preserved. Problems:")
        for p in exc.problems:
            print(f"  - {p}")
        raise
    finally:
        if close_conn:
            conn.close()

    return {
        "status": "ok",
        "rows": len(df),
        "quarterly": len(quarterly),
        "annual": len(annual),
    }


def _create_views(conn: sqlite3.Connection) -> None:
    """Recreate reader views on the given connection (views are stateless)."""
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


if __name__ == "__main__":
    run()
