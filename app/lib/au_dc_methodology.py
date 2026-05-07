"""Reusable methodology help text for AU data centre views."""

RISKED_MW_HELP = (
    "Risked MW = facility MW multiplied by a status/power confidence weight: "
    "Operating 100%, Under Construction 100%, Approved with power secured 75%, "
    "Approved with grid/power pending 25%, Proposed/Announced 0%. "
    "This is a delivery-confidence lens, not contracted demand or expected load."
)

RECORDED_MW_HELP = (
    "Recorded MW is the project capacity currently counted in dashboard totals. "
    "It is called unverified because public sources use different bases: IT load, "
    "gross facility power, power consumption, or full-campus build-out. Rows without "
    "row-level source evidence are quarantined and excluded from this total by default."
)

CAPEX_ESTIMATION_HELP = (
    "CAPEX is disclosed where filings or project announcements provide a figure. "
    "If missing, capex_aud_m is modelled from facility MW using operator-type benchmarks: "
    "Hyperscaler A$8m/MW, Colocation A$12m/MW, Developer A$15m/MW, "
    "Telecom/Technology A$18m/MW. Estimated rows are flagged and should not be "
    "treated as disclosed market spend."
)

DISCLOSED_CAPEX_HELP = (
    "Disclosed CAPEX only sums rows where the public source provided a project CAPEX figure. "
    "The delta, where shown, is the additional modelled CAPEX for rows without a disclosed figure."
)
