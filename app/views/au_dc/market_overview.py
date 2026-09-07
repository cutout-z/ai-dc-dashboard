"""Market Overview — Headline KPIs, capacity trends, market breakdown."""

import json
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from app.lib.au_dc_charts import (
    capacity_by_region_bar,
    capacity_by_operator_bar,
    operator_capacity_segments,
    market_breakdown_pie,
    capacity_forecast_chart,
    COLOUR_PALETTE,
)
from app.lib.au_dc_excluded_capacity import (
    excluded_capacity_components,
    public_excluded_capacity_overlay,
)
from app.lib.au_dc_methodology import (
    FORECAST_TIMELINE_HELP,
    OPERATOR_CAPACITY_SEGMENTS_HELP,
    RISKED_MW_HELP,
)
from app.lib.au_dc_stage_scope import operating_layers as _operating_layers_fn, operating_stage_summary

AU_DC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc"
DATA_DIR = AU_DC_DIR / "processed"
REFERENCE_DIR = AU_DC_DIR / "reference"

st.title("Market Overview")

# Load data
projects_path = DATA_DIR / "projects.parquet"

if not projects_path.exists():
    st.error("Project database not found. Run `python etl/build_project_db.py` in au-dc-analysis first.")
    st.stop()

projects = pd.read_parquet(projects_path)
if "include_in_project_totals" in projects.columns:
    projects_for_totals = projects[projects["include_in_project_totals"].fillna(True)]
else:
    projects_for_totals = projects
aggregate_guidance_path = REFERENCE_DIR / "operator_aggregate_guidance.csv"
aggregate_guidance = (
    pd.read_csv(aggregate_guidance_path)
    if aggregate_guidance_path.exists()
    else pd.DataFrame()
)
site_leads_path = REFERENCE_DIR / "hyperscaler_site_leads.csv"
site_leads = pd.read_csv(site_leads_path) if site_leads_path.exists() else pd.DataFrame()
spot_check_path = DATA_DIR / "spot_check.json"
spot_check = json.loads(spot_check_path.read_text()) if spot_check_path.exists() else None

if spot_check:
    summary = spot_check.get("summary", {})
    if summary.get("warnings", 0) or summary.get("errors", 0):
        st.warning(
            f"AU DC data quality check: {summary.get('errors', 0)} error(s), "
            f"{summary.get('warnings', 0)} warning(s). Treat project CAPEX and some capacity fields "
            "as mixed-quality public-source data."
        )

st.markdown("### Controls")
risk_view = st.radio(
    "Capacity View",
    ["Unrisked", "Risked"],
    index=0,
    key="au_mkt_risk",
    horizontal=True,
    help=RISKED_MW_HELP,
)
mw_col = "risked_mw" if risk_view == "Risked" else "facility_mw"

# --- KPI Row ---
st.markdown("### Key Metrics")
k1, k2, k3, k4, k5 = st.columns(5)

total_projects = len(projects)
operating = projects_for_totals[projects_for_totals["status"] == "Operating"]
quarantined = total_projects - len(projects_for_totals)
operator_segments = operator_capacity_segments(projects_for_totals, aggregate_guidance)
capacity_segments = operator_segments[
    ["risked", "announced_site_tied", "unassigned_aggregate", "announced_total"]
].sum()
excluded_overlay = public_excluded_capacity_overlay(projects, aggregate_guidance, site_leads)
operating_layers = operating_stage_summary(projects_for_totals)

with k1:
    st.metric("Total Projects", total_projects, delta=f"{quarantined} quarantined" if quarantined else None)
with k2:
    st.metric("Operating DCs", len(operating))
with k3:
    # Operating-stage MW is separated from campus envelopes whose stage
    # allocation is not stored: the headline counts only directly evidenced
    # operating-stage rows, and envelope MW stays visible as its own layer
    # (Eastern Creek / SYD1 / SYD2 / MEL1) instead of silently counting as
    # fully operating-stage (S2-06).
    st.metric(
        "Operating Capacity (stage-evidenced)",
        f"{operating_layers['evidenced_mw']:,.0f} MW",
        delta=(
            f"{operating_layers['campus_envelope_mw']:,.0f} MW campus envelope — "
            "stage split not stored"
            if operating_layers["campus_envelope_mw"] > 0
            else None
        ),
        delta_color="off",
        help=(
            "Directly evidenced operating-stage MW: rows whose stored source "
            "basis is a row-level or campus-current-operating figure. Operating "
            "campus rows with no stored stage split (Eastern Creek, SYD1, SYD2, "
            "MEL1) are shown separately — their row status is the best available "
            "campus label, not proof every MW is currently operating."
        ),
    )
with k4:
    st.metric(
        "Risked Capacity",
        f"{capacity_segments['risked']:,.0f} MW",
        help=RISKED_MW_HELP,
    )
with k5:
    st.metric(
        "Aggregate Announced",
        f"{capacity_segments['announced_total']:,.0f} MW",
        help=(
            "Total announced capacity used by the Top Operators chart: included named project/campus MW "
            "plus unassigned aggregate operator guidance that is not yet mapped to named project rows."
        ),
    )

if operating_layers["campus_envelope_mw"] > 0:
    st.caption(
        "Operating capacity layers: "
        f"{operating_layers['evidenced_mw']:,.0f} MW directly evidenced operating-stage "
        f"({operating_layers['evidenced_rows']} rows) + "
        f"{operating_layers['campus_envelope_mw']:,.0f} MW on operating campuses whose "
        f"stage split is not stored ({operating_layers['campus_envelope_rows']} rows: "
        f"{', '.join(operating_layers['campus_envelope_projects'])}). "
        "Campus envelopes are retained as announced/reference capacity; no stage MW is guessed."
    )

_operating_evidenced, _operating_campus = _operating_layers_fn(projects_for_totals)
if not _operating_campus.empty:
    _cols = [
        c for c in [
            "project_name", "operator", "nem_region", "status", "facility_mw",
            "startup_year", "capacity_scope", "stage_status_caveat",
        ] if c in _operating_campus.columns
    ]
    with st.expander("Operating campus envelopes — stage split not stored"):
        st.caption(
            "Rows below are Operating with campus-level MW but no stored building/stage "
            "allocation. They stay visible as separate rows and are not counted in the "
            "stage-evidenced Operating Capacity headline; see Stage Caveat before treating "
            "their MW as currently operating-stage."
        )
        st.dataframe(
            _operating_campus[_cols].sort_values("facility_mw", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "project_name": "Project",
                "operator": "Operator",
                "nem_region": "Region",
                "status": "Status",
                "facility_mw": st.column_config.NumberColumn("MW (campus)", format="%d"),
                "startup_year": st.column_config.NumberColumn("Startup", format="%d"),
                "capacity_scope": st.column_config.TextColumn("Capacity Scope"),
                "stage_status_caveat": st.column_config.TextColumn("Stage Caveat", width="large"),
            },
        )

st.markdown("### Excluded Public-Source Capacity Signals")
st.caption(
    "Screening overlay for public-source capacity that is deliberately excluded from default project MW totals. "
    "Components can use mixed capacity bases and may overlap until reconciled to named project rows."
)
e1, e2, e3, e4 = st.columns(4)
with e1:
    st.metric(
        "Screening Total",
        f"{excluded_overlay['screening_total_mw']:,.0f} MW",
        help="Quarantined named rows + unmatched aggregate guidance + physical site leads. This is not an additive market-capacity estimate.",
    )
with e2:
    st.metric(
        "Quarantined Project MW",
        f"{excluded_overlay['quarantined_project_mw']:,.0f} MW",
        delta=f"{excluded_overlay['quarantined_project_rows']:,.0f} rows",
        help="Named project rows retained for audit trail but excluded from default totals.",
    )
with e3:
    st.metric(
        "Unmatched Aggregate MW",
        f"{excluded_overlay['unmatched_aggregate_mw']:,.0f} MW",
        delta=f"{excluded_overlay['aggregate_records_with_mw']:,.0f} records",
        help="Public operator or platform guidance not yet mapped to named included project rows.",
    )
with e4:
    st.metric(
        "Physical Lead MW",
        f"{excluded_overlay['sourced_site_lead_mw']:,.0f} MW",
        delta=f"{excluded_overlay['site_leads_with_mw']:,.0f} leads",
        help="Named physical site leads with public MW evidence, excluded pending promotion through the evidence audit.",
    )

with st.expander("Excluded capacity breakdown", icon=":material/search:"):
    st.dataframe(
        excluded_capacity_components(excluded_overlay),
        use_container_width=True,
        hide_index=True,
        column_config={
            "component": "Component",
            "mw": st.column_config.NumberColumn("MW", format="%d"),
            "rows": st.column_config.NumberColumn("Rows / Records", format="%d"),
            "treatment": st.column_config.TextColumn("Treatment", width="large"),
        },
    )

with st.expander("Data sources & methodology", icon=":material/info:"):
    st.markdown(
        """
**Coverage note:** This dataset tracks publicly announced projects and facilities, but the current project
table is provisional rather than audit-grade. It will not capture
every data centre — undisclosed hyperscaler on-premises deployments, small enterprise facilities (<10 MW),
and government classified infrastructure are not included. Figures reflect publicly available information
at the time of last update.

**Project database**
Manually curated from named public sources: ASX/NZX announcements, company IR pages, NSW/VIC/QLD State
Significant Development (SSD) portals, Data Center Dynamics, datacentermap.com, datacenterhawk.com, and
press releases. The project seed now stores source URLs, source dates, page or section references,
evidence extracts, capacity basis, and remediation notes where available. Rows still vary in evidence
quality because public disclosures mix precise site-level MW, campus envelopes, power-consumption figures,
and announced pipeline capacity. Rows flagged as quarantined are retained for audit trail but excluded
from default project totals.
Updated periodically as announcements are made; there is no automated refresh.

**Capacity methodology**
- *Announced capacity*: included named project/campus MW plus separately tracked unassigned aggregate
  operator guidance. The Top Operators chart and Key Metrics split this into Risked, Announced / site-tied,
  and Unassigned aggregate segments to avoid mixing named project rows with operator-level pipeline guidance.
- *Unrisked*: included project MW at the disclosed capacity basis. The database distinguishes IT load,
  gross facility power, campus full-build MW, and power-consumption envelopes where the source allows.
  Quarantined legacy estimates and no-MW facility leads are excluded from default totals.
- *Operating-stage vs campus envelope*: operating-stage headlines count only rows with direct
  stage-level evidence. Operating campuses whose MW is a campus envelope with no stored stage split
  (Eastern Creek, SYD1, SYD2, MEL1) are shown as a separate envelope layer — their status is a campus
  label, not proof every MW is currently operating-stage. No stage MW is guessed.
- *Risked*: a delivery-confidence lens (not a calibrated probability). The disclosed status weight is
  applied to the MW the status directly covers — the directly evidenced stage figure where one is stored
  (e.g. GreenSquareDC SYD1's 15 MW Stage 1 inside its 110 MW campus envelope), otherwise the row-level
  facility figure. Campus envelopes stay visible as announced/reference capacity and are not
  double-counted.

  | Status | Weight | Rationale |
  |---|---|---|
  | Operating | 100% | Built and running |
  | Under Construction | 100% | Power and site secured; build in progress |
  | Approved — power secured | 75% | Planning approved and grid connection confirmed |
  | Approved — grid connection pending | 25% | Planning approved; grid connection not yet secured |
  | Proposed | 0% | Announced only; no power pathway confirmed |

- Where only a partial phase is funded, the figure reflects what has been disclosed (not full campus aspiration)
- *Power secured* status is manually assessed from public disclosures; defaults to unconfirmed if not explicitly announced
- *Timeline*: capacity is placed by sourced startup year only. Pipeline rows with no sourced
  startup/delivery year are shown in an "Undated" bucket rather than being assigned a forecast year.

**CAPEX methodology**
CAPEX is disclosed only where public filings or announcements provide a figure. Where missing, the model
fills `capex_aud_m` using operator-type benchmarks; those rows are flagged as estimated in the Project
Analysis page and should not be read as disclosed market spend.

**Other providers that track Australian DC builds**
[Data Center Dynamics](https://www.datacenterdynamics.com/en/market/australasia/) ·
[datacentermap.com](https://www.datacentermap.com/australia/) ·
[datacenterhawk.com](https://datacenterhawk.com/market/australia) ·
[AIIA Data Centre Industry Report](https://www.aiia.com.au/)
        """,
        unsafe_allow_html=False,
    )

st.markdown("---")

# --- Capacity Trends ---
st.markdown("### Installed Capacity")
col1, col2 = st.columns(2)

with col1:
    fig = capacity_by_region_bar(projects_for_totals, title=f"Capacity by Region ({risk_view})")
    if risk_view == "Risked":
        agg = projects_for_totals.groupby(["nem_region", "status"])["risked_mw"].sum().reset_index()
        fig = px.bar(agg, x="nem_region", y="risked_mw", color="status",
                     color_discrete_map=COLOUR_PALETTE, title="Capacity by Region (Risked)",
                     labels={"risked_mw": "Capacity (MW)", "nem_region": "NEM Region"},
                     barmode="stack")
        fig.update_layout(
            template=st.session_state.get("plotly_template", "plotly_dark"),
            margin=dict(l=40, r=20, t=40, b=80),
            legend=dict(orientation="h", yanchor="top", y=-0.2, x=0),
        )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.caption(
        "Risked, announced site-tied, and unassigned aggregate operator capacity.",
        help=OPERATOR_CAPACITY_SEGMENTS_HELP,
    )
    fig = capacity_by_operator_bar(projects_for_totals, aggregate_guidance=aggregate_guidance)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("### Forecast Pipeline by Risk Category")
fig = capacity_forecast_chart(projects_for_totals)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Cumulative stated capacity by sourced startup year, colour-coded by certainty tier. "
    "Operating rows with no sourced startup year are existing capacity (shown from chart "
    "start). Pipeline with no sourced startup/delivery year sits in the Undated bucket — "
    "no delivery year is invented, so undated pipeline never creates a false 2028 cliff. "
    "Power secured status for Approved projects based on public disclosures.",
    help=FORECAST_TIMELINE_HELP,
)

st.markdown("---")

# --- Market Breakdown ---
st.markdown("### Market Breakdown")
b1, b2, b3 = st.columns(3)

with b1:
    fig = market_breakdown_pie(projects_for_totals, "operator_type", mw_col, "By Operator Type")
    st.plotly_chart(fig, use_container_width=True)
with b2:
    fig = market_breakdown_pie(projects_for_totals, "size_class", mw_col, "By Project Size")
    st.plotly_chart(fig, use_container_width=True)
with b3:
    fig = market_breakdown_pie(projects_for_totals, "status", mw_col, "By Development Status")
    st.plotly_chart(fig, use_container_width=True)

b4, b5, _ = st.columns(3)
with b4:
    fig = market_breakdown_pie(projects_for_totals, "workload_type", mw_col, "By Workload Type")
    st.plotly_chart(fig, use_container_width=True)
with b5:
    fig = market_breakdown_pie(projects_for_totals, "power_strategy", mw_col, "By Power Strategy")
    st.plotly_chart(fig, use_container_width=True)

st.info(
    "**Source — Manually curated Australian DC project database.**  \n"
    "This is a public-source project database with row-level evidence fields where available, but it is "
    "still provisional and should not be treated as an exhaustive market census. Rows refer to ASX/NZX "
    "announcements, company IR pages, NSW/VIC/QLD State Significant "
    "Development (SSD) portals, "
    "[Data Center Dynamics](https://www.datacenterdynamics.com/en/market/australasia/), "
    "[datacentermap.com](https://www.datacentermap.com/australia/), "
    "[datacenterhawk.com](https://datacenterhawk.com/market/australia), and operator press releases, "
    "with source URLs, dates, evidence extracts, capacity basis, and remediation notes stored where available. "
    "Capacity is public-source curated and may still mix IT load, gross facility power, campus full-build power, "
    "and campus power-consumption envelopes. Quarantined rows and separate hyperscaler announcement/site-lead "
    "tables are excluded from default project MW totals unless promoted into the project database. CAPEX may be "
    "estimated where not disclosed. Coverage excludes undisclosed hyperscaler on-premises deployments, "
    "enterprise facilities <10 MW, and classified government infrastructure. "
    "Updated periodically as announcements are made — there is no automated refresh.  \n"
    "See *Data sources & methodology* above for capacity weighting rules.",
    icon=":material/info:",
)
