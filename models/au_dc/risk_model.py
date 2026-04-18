"""Status-based risk weighting for data centre projects.

Risk weights by development status. For Approved projects, weight depends on
whether grid connection / power is secured (set via power_secured field in seed CSV).
Proposed projects are assigned 0% — announced with no power pathway.
"""

RISK_WEIGHTS = {
    "Operating": 1.00,
    "Under Construction": 1.00,    # power & site secured; build in progress
    "Approved_power": 0.75,        # planning approved, power/grid connection secured
    "Approved_no_power": 0.25,     # planning approved, grid connection not yet secured
    "Proposed": 0.00,
    "Announced": 0.00,
    "Unknown": 0.00,
}


def apply_risk_weight(df, status_col="status", mw_col="facility_mw", power_secured_col="power_secured"):
    """Add risked_mw column to a DataFrame based on development status and power_secured flag."""
    df = df.copy()

    def _weight(row):
        status = row[status_col]
        if status == "Approved":
            secured = row.get(power_secured_col, False)
            # Treat truthy strings ("True", "true", "1") as secured
            if isinstance(secured, str):
                secured = secured.strip().lower() in ("true", "1", "yes")
            return RISK_WEIGHTS["Approved_power"] if secured else RISK_WEIGHTS["Approved_no_power"]
        return RISK_WEIGHTS.get(status, 0.00)

    df["risk_weight"] = df.apply(_weight, axis=1)
    df["risked_mw"] = df[mw_col] * df["risk_weight"]
    return df
