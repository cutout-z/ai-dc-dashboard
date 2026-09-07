"""Status-based risk weighting for data centre projects.

Risk weights by development status. For Approved projects, weight depends on
whether grid connection / power is secured (set via power_secured field in seed CSV).
Proposed projects are assigned 0% — announced with no power pathway.
"""

import pandas as pd

RISK_WEIGHTS = {
    "Operating": 1.00,
    "Under Construction": 1.00,    # power & site secured; build in progress
    "Approved_power": 0.75,        # planning approved, power/grid connection secured
    "Approved_no_power": 0.25,     # planning approved, grid connection not yet secured
    "Proposed": 0.00,
    "Announced": 0.00,
    "Unknown": 0.00,
}


def apply_risk_weight(
    df,
    status_col="status",
    mw_col="facility_mw",
    power_secured_col="power_secured",
    stage_mw_col="evidenced_stage_mw",
):
    """Add risked_mw column to a DataFrame based on development status and power_secured flag.

    The status weight is applied to the MW figure the status actually covers:
    when a campus-envelope row also stores a directly evidenced stage-level
    MW figure (``evidenced_stage_mw``, e.g. GreenSquareDC SYD1's 15 MW
    Stage 1 inside a 110 MW campus envelope), the weight applies to that
    stage figure. The campus envelope stays in ``facility_mw`` (recorded /
    announced reference) and is not double-counted as risked capacity.
    Rows without a stored stage figure are weighted on ``facility_mw`` as
    before — no MW is guessed from absence of evidence.
    """
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

    # Risk base: the directly evidenced stage-level MW when stored, otherwise
    # the row-level facility MW figure.
    facility = pd.to_numeric(df.get(mw_col), errors="coerce")
    if stage_mw_col and stage_mw_col in df.columns:
        staged = pd.to_numeric(df[stage_mw_col], errors="coerce")
        base = staged.where(staged.notna(), facility)
    else:
        base = facility
    df["risk_base_mw"] = base.fillna(0.0)
    df["risk_weight"] = df.apply(_weight, axis=1)
    df["risked_mw"] = df["risk_base_mw"] * df["risk_weight"]
    return df
