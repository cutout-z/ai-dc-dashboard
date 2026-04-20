"""Build DC demand forecasts from reference CSV.

Reads the manually extracted forecast data (from Oxford Economics, AEMO IASR,
CEFC/Baringa reports) and outputs dc_demand.parquet.
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FORECAST_CSV = BASE_DIR / "data" / "au_dc" / "reference" / "dc_demand_forecasts.csv"
PROCESSED_DIR = BASE_DIR / "data" / "au_dc" / "processed"


def build():
    print("=" * 60)
    print("Building DC Demand Forecasts")
    print("=" * 60)

    df = pd.read_csv(FORECAST_CSV)
    print(f"  Loaded {len(df)} forecast data points")

    # Compute DC share of total NEM demand
    df["dc_share_pct"] = (df["dc_consumption_twh"] / df["total_nem_demand_twh"] * 100).round(2)

    # Compute YoY growth within each scenario
    for scenario in df["scenario"].unique():
        mask = df["scenario"] == scenario
        df.loc[mask, "dc_yoy_growth_pct"] = (
            df.loc[mask, "dc_consumption_twh"].pct_change() * 100
        ).round(1)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "dc_demand.parquet"
    df.to_parquet(out_path, index=False)
    print(f"  Saved: {out_path.name} ({len(df)} rows)")

    # Summary
    print("\n--- Summary ---")
    for scenario in df["scenario"].unique():
        sdf = df[df["scenario"] == scenario]
        last = sdf.iloc[-1]
        print(f"  {scenario}: {sdf['year'].min()}-{sdf['year'].max()}, "
              f"DC demand {sdf['dc_consumption_twh'].iloc[0]:.1f} -> {last['dc_consumption_twh']:.1f} TWh "
              f"({last['dc_share_pct']:.1f}% of NEM)")


if __name__ == "__main__":
    build()
