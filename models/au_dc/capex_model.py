"""CAPEX estimation model for data centre projects.

Applies industry benchmarks to estimate construction costs where
actual CAPEX is not disclosed. Benchmarks are per MW of facility power.
"""

# A$/MW benchmarks by operator type (2024-25 estimates)
# Sources: Oxford Economics, CEFC/Baringa, ASX filings, industry analysis
CAPEX_BENCHMARKS = {
    "Hyperscaler": 8.0,    # $8M/MW — highly optimised, massive scale
    "Colocation": 12.0,    # $12M/MW — mid-range colo/wholesale
    "Developer": 15.0,     # $15M/MW — premium/campus developer
    "Telecom": 18.0,       # $18M/MW — smaller, higher per-unit cost
    "Technology": 18.0,    # $18M/MW — similar to telecom scale
}

DEFAULT_BENCHMARK = 12.0  # fallback for unknown operator types


def estimate_capex(df, operator_type_col="operator_type", mw_col="facility_mw",
                   capex_col="capex_aud_m"):
    """Add estimated CAPEX where actual is not disclosed.

    Adds columns:
    - capex_estimated (bool): True if the value is an estimate
    - capex_aud_m: filled in with estimate where previously null
    """
    df = df.copy()
    df["capex_estimated"] = df[capex_col].isna()

    for idx in df[df["capex_estimated"]].index:
        op_type = df.loc[idx, operator_type_col]
        mw = df.loc[idx, mw_col]
        if pd.isna(mw) or mw <= 0:
            continue
        benchmark = CAPEX_BENCHMARKS.get(op_type, DEFAULT_BENCHMARK)
        df.loc[idx, capex_col] = round(mw * benchmark)

    return df


# Need pandas for the isna check
import pandas as pd
