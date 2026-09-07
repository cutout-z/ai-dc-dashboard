"""Reusable methodology help text for AU data centre views."""

RISKED_MW_HELP = (
    "Risked MW = the MW the status directly covers, multiplied by a disclosed "
    "status/power confidence weight: Operating 100%, Under Construction 100%, "
    "Approved with power secured 75%, Approved with grid/power pending 25%, "
    "Proposed/Announced 0%. Where a campus-envelope row also stores a directly "
    "evidenced stage figure (e.g. GreenSquareDC SYD1's 15 MW Stage 1 inside a "
    "110 MW campus envelope), the weight applies to that stage MW; the campus "
    "envelope stays visible as announced/reference capacity and is not "
    "double-counted. Weights are disclosed conventions, not calibrated "
    "probabilities. This is a delivery-confidence lens, not contracted demand "
    "or expected load."
)

OPERATOR_CAPACITY_SEGMENTS_HELP = (
    "Top Operators segments: Risked = included named project/campus MW multiplied by "
    "the dashboard delivery-confidence weights (Operating and Under Construction 100%, "
    "Approved with power secured 75%, Approved with grid/power pending 25%, "
    "Proposed/Announced 0%). Announced / site-tied = the remaining included MW tied to "
    "a named project or campus but not counted in Risked MW. Unassigned aggregate = "
    "operator-level pipeline, contract, order-book, or platform guidance not yet mapped "
    "to named project rows."
)

RECORDED_MW_HELP = (
    "Recorded MW is the project capacity currently counted in dashboard totals. "
    "It is called unverified because public sources use different bases: IT load, "
    "gross facility power, power consumption, or full-campus build-out. Rows without "
    "row-level source evidence are quarantined and excluded from this total by default. "
    "Campus/full-build rows may include multiple stages; check Capacity Scope and "
    "Stage Caveat before treating the MW as currently operating. Operating-stage "
    "headlines count only rows with direct stage-level evidence; campus envelopes "
    "with no stored stage split are shown as a separate layer."
)

CAMPUS_SCOPE_HELP = (
    "Campus envelope MW is capacity where the public source reports a campus, full-build, "
    "upon-completion, or power-consumption figure rather than a stage/building-level "
    "current IT-load figure. It is counted in Recorded MW if the row is included, but "
    "the row status may not apply to every building on a staged campus — the campus "
    "envelope is retained as an announced/reference layer, not claimed as "
    "operating-stage MW without stage-level evidence."
)

FORECAST_TIMELINE_HELP = (
    "Cumulative stated capacity by sourced startup year, colour-coded by delivery-confidence "
    "tier. Operating rows without a sourced startup year are existing capacity (shown from "
    "chart start). Non-operating rows with no sourced startup/delivery year are collected in "
    "the Undated bucket — no delivery year is invented, so undated pipeline never creates a "
    "false delivery-year cliff."
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
