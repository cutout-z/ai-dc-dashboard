"""Fetch ASX financial data for listed DC operators.

Uses yfinance (via OpenBB or direct) to pull quotes, fundamentals,
and price history for listed operators in operator_types.csv.

Run standalone: python etl/fetch_financials.py
"""

import sys
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent
OPERATOR_CSV = BASE_DIR / "data" / "reference" / "operator_types.csv"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# Map our ticker format (ASX:NXT) to yfinance format (NXT.AX)
EXCHANGE_SUFFIX = {
    "ASX": ".AX",
    "NZX": ".NZ",
    "NASDAQ": "",
    "NYSE": "",
    "TYO": ".T",
}

# Only fetch AU-listed DC operators (most relevant for this dashboard)
AU_TICKERS = ["ASX:NXT", "ASX:GMG", "ASX:MAQ"]


def ticker_to_yfinance(ticker: str) -> str:
    """Convert 'ASX:NXT' format to 'NXT.AX' format."""
    if ":" not in ticker:
        return ticker
    exchange, symbol = ticker.split(":", 1)
    suffix = EXCHANGE_SUFFIX.get(exchange, "")
    return f"{symbol}{suffix}"


def fetch_quotes(tickers: list[str]) -> pd.DataFrame:
    """Fetch latest quotes for given tickers."""
    yf_tickers = [ticker_to_yfinance(t) for t in tickers]
    rows = []
    for orig, yft in zip(tickers, yf_tickers):
        try:
            info = yf.Ticker(yft).info
            rows.append({
                "ticker": orig,
                "yf_ticker": yft,
                "name": info.get("shortName", ""),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "revenue_growth": info.get("revenueGrowth"),
                "profit_margin": info.get("profitMargins"),
                "debt_to_equity": info.get("debtToEquity"),
                "beta": info.get("beta"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "dividend_yield": info.get("dividendYield"),
            })
        except Exception as e:
            print(f"  WARNING: Could not fetch {yft}: {e}")

    return pd.DataFrame(rows)


def fetch_price_history(tickers: list[str], period: str = "1y",
                        interval: str = "1wk") -> pd.DataFrame:
    """Fetch weekly price history for given tickers."""
    frames = []
    for ticker in tickers:
        yft = ticker_to_yfinance(ticker)
        try:
            hist = yf.Ticker(yft).history(period=period, interval=interval)
            hist = hist.reset_index()
            hist["ticker"] = ticker
            hist["yf_ticker"] = yft
            frames.append(hist[["Date", "ticker", "yf_ticker", "Close", "Volume"]])
        except Exception as e:
            print(f"  WARNING: Could not fetch history for {yft}: {e}")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.rename(columns={"Date": "date", "Close": "close", "Volume": "volume"})
    return combined


def main():
    print("=" * 60)
    print("Fetching ASX Financial Data")
    print("=" * 60)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch quotes
    print("\n1. Fetching quotes...")
    quotes = fetch_quotes(AU_TICKERS)
    if not quotes.empty:
        quotes_path = PROCESSED_DIR / "financials_quotes.parquet"
        quotes.to_parquet(quotes_path, index=False)
        print(f"  Saved: {quotes_path.name} ({len(quotes)} rows)")
        for _, row in quotes.iterrows():
            mc = row["market_cap"]
            mc_str = f"A${mc/1e9:.1f}B" if mc and mc > 1e9 else "N/A"
            print(f"  {row['ticker']:10s} {row['name']:35s} ${row['price']:.2f}  MCap: {mc_str}")

    # Fetch price history
    print("\n2. Fetching price history (1yr weekly)...")
    history = fetch_price_history(AU_TICKERS)
    if not history.empty:
        hist_path = PROCESSED_DIR / "financials_history.parquet"
        history.to_parquet(hist_path, index=False)
        print(f"  Saved: {hist_path.name} ({len(history)} rows)")

    print("\nDone.")


if __name__ == "__main__":
    main()
