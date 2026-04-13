"""Simple status-based risk weighting for data centre projects.

Based on Oxford Economics "6 in 7" finding — most announced DC capacity
never materialises. Risk weights by development status.
"""

RISK_WEIGHTS = {
    "Operating": 1.00,
    "Under Construction": 0.90,
    "Approved": 0.60,
    "Proposed": 0.25,
    "Announced": 0.25,
    "Unknown": 0.25,
}


def apply_risk_weight(df, status_col="status", mw_col="facility_mw"):
    """Add risked_mw column to a DataFrame based on development status."""
    df = df.copy()
    df["risk_weight"] = df[status_col].map(RISK_WEIGHTS).fillna(0.25)
    df["risked_mw"] = df[mw_col] * df["risk_weight"]
    return df
