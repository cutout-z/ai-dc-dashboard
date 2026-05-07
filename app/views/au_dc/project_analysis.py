"""Project Analysis — Full project database with filtering."""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from app.lib.au_dc_charts import COLOUR_PALETTE, CHART_LAYOUT
from app.lib.au_dc_methodology import (
    CAMPUS_SCOPE_HELP,
    CAPEX_ESTIMATION_HELP,
    DISCLOSED_CAPEX_HELP,
    RECORDED_MW_HELP,
    RISKED_MW_HELP,
)

AU_DC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc"
DATA_DIR = AU_DC_DIR / "processed"
REFERENCE_DIR = AU_DC_DIR / "reference"

st.title("Project Analysis")

projects_path = DATA_DIR / "projects.parquet"
if not projects_path.exists():
    st.error("Project database not found.")
    st.stop()

projects = pd.read_parquet(projects_path)
audit_path = DATA_DIR / "project_evidence_audit.csv"
if audit_path.exists():
    audit_cols = [
        "project_name", "campus", "operator", "evidence_grade",
        "source_class", "has_source_url", "issues",
    ]
    audit = pd.read_csv(audit_path, usecols=lambda c: c in audit_cols)
    projects = projects.merge(
        audit,
        on=["project_name", "campus", "operator"],
        how="left",
        suffixes=("", "_audit"),
    )

    no_url = int((projects.get("has_source_url") == False).sum()) if "has_source_url" in projects.columns else len(projects)
    weak_rows = projects[projects.get("evidence_grade", "").isin(["C", "D", "E"])] if "evidence_grade" in projects.columns else projects
    weak_mw = weak_rows["facility_mw"].fillna(0).sum()
    if no_url > 0 or weak_mw > 0:
        st.warning(
            f"Project database is provisional: {no_url}/{len(projects)} rows have no stored source URL, "
            f"and {weak_mw:,.0f} MW is C/D/E evidence grade. Use this page as an audit queue, not a source of truth.",
            icon=":material/warning:",
        )
else:
    st.warning(
        "Project evidence audit has not been generated. Run scripts/au_dc_project_evidence_audit.py before relying on this page.",
        icon=":material/warning:",
    )

# ========================================
# Filters
# ========================================
st.markdown("### Filters")

statuses = ["All"] + sorted(projects["status"].unique().tolist())
regions_list = ["All"] + sorted(projects["nem_region"].unique().tolist())
op_types = ["All"] + sorted(projects["operator_type"].dropna().unique().tolist())

f1, f2, f3 = st.columns(3)
with f1:
    sel_status = st.multiselect("Status", statuses, default=["All"], key="au_proj_status")
with f2:
    sel_region = st.multiselect("Region", regions_list, default=["All"], key="au_proj_region")
with f3:
    sel_op_type = st.multiselect("Operator Type", op_types, default=["All"], key="au_proj_optype")

if "evidence_grade" in projects.columns:
    evidence_grades = ["All"] + sorted(projects["evidence_grade"].dropna().unique().tolist())
else:
    evidence_grades = ["All"]
    sel_evidence = ["All"]

display_mw = projects["facility_mw"].copy()
if "unverified_capacity_mw" in projects.columns:
    display_mw = display_mw.fillna(projects["unverified_capacity_mw"])
projects["_display_mw"] = display_mw.fillna(0)

f4, f5 = st.columns([2, 1])
with f4:
    sel_evidence = st.multiselect(
        "Evidence Grade",
        evidence_grades,
        default=["All"],
        key="au_proj_evidence",
        help="A requires row-level source URL, evidence text, capacity basis, and source date where available.",
    )
with f5:
    min_mw = st.slider("Min MW", 0, int(projects["_display_mw"].max()), 0, key="au_proj_mw")

show_quarantined = st.toggle(
    "Show Quarantined Rows",
    value=False,
    key="au_proj_show_quarantined",
    help="Quarantined rows retain unverified MW for audit trail but are excluded from default project totals.",
)

# Apply filters
filtered = projects.copy()
if "All" not in sel_status:
    filtered = filtered[filtered["status"].isin(sel_status)]
if "All" not in sel_region:
    filtered = filtered[filtered["nem_region"].isin(sel_region)]
if "All" not in sel_op_type:
    filtered = filtered[filtered["operator_type"].isin(sel_op_type)]
if "All" not in sel_evidence and "evidence_grade" in filtered.columns:
    filtered = filtered[filtered["evidence_grade"].isin(sel_evidence)]
if not show_quarantined and "include_in_project_totals" in filtered.columns:
    filtered = filtered[filtered["include_in_project_totals"].fillna(True)]
filtered = filtered[filtered["_display_mw"] >= min_mw]

metric_mw = (
    filtered["_display_mw"]
    if show_quarantined
    else filtered["facility_mw"].fillna(0)
)

# ========================================
# KPIs
# ========================================
k1, k2, k3, k4, k5 = st.columns(5)
campus_scope_mask = (
    filtered.get("capacity_scope", pd.Series("", index=filtered.index))
    .fillna("")
    .astype(str)
    .str.contains("Campus", case=False, na=False)
    & ~filtered.get("capacity_scope", pd.Series("", index=filtered.index))
    .fillna("")
    .astype(str)
    .eq("Campus current operating capacity")
)
with k1:
    st.metric("Projects Shown", len(filtered))
with k2:
    st.metric(
        "Recorded MW (Unverified)",
        f"{metric_mw.sum():,.0f}",
        help=RECORDED_MW_HELP,
    )
with k3:
    st.metric("Risked MW (Provisional)", f"{filtered['risked_mw'].sum():,.0f}", help=RISKED_MW_HELP)
with k4:
    pipeline_filtered = filtered[filtered["status"] != "Operating"]
    if "capex_estimated" in filtered.columns:
        estimated_mask = pipeline_filtered["capex_estimated"].fillna(False)
        disclosed_capex = pipeline_filtered.loc[~estimated_mask, "capex_aud_m"].dropna().sum()
        st.metric(
            "Pipeline Disclosed CAPEX",
            f"A${disclosed_capex:,.0f}M",
            help=f"{DISCLOSED_CAPEX_HELP} Operating rows are excluded from this top-line KPI.",
        )
    else:
        known_capex = pipeline_filtered["capex_aud_m"].dropna().sum()
        st.metric("Pipeline Known CAPEX", f"A${known_capex:,.0f}M" if known_capex > 0 else "N/A")
with k5:
    if "capex_estimated" in filtered.columns:
        estimated_mask = pipeline_filtered["capex_estimated"].fillna(False)
        estimated_capex = pipeline_filtered.loc[estimated_mask, "capex_aud_m"].dropna().sum()
        st.metric(
            "Pipeline Modelled CAPEX",
            f"A${estimated_capex:,.0f}M",
            help=f"{CAPEX_ESTIMATION_HELP} Operating rows are excluded from this top-line KPI.",
        )
    else:
        st.metric("Pipeline Modelled CAPEX", "N/A", help=CAPEX_ESTIMATION_HELP)

if "capacity_scope" in filtered.columns and campus_scope_mask.any():
    campus_scope_mw = metric_mw.loc[campus_scope_mask].sum()
    st.info(
        f"{campus_scope_mw:,.0f} MW across {int(campus_scope_mask.sum())} shown rows is campus-envelope MW. "
        "For staged campuses, the status is a best available campus/project label and may not apply to every building. "
        "Use the Capacity Scope and Stage Caveat columns before treating these MW as current operating capacity.",
        icon=":material/info:",
    )

st.markdown("### Capacity by Development Status — Projects Shown Only")
st.caption(
    "These MW totals use the current filters and exclude quarantined/unverified rows unless "
    "`Show Quarantined Rows` is enabled. They are not an estimate of the full Australian data centre universe. "
    "For campus-envelope rows, status is applied at row level because public stage-level MW is not always disclosed."
)

status_df = filtered.copy()
mw_series = status_df["_display_mw"] if show_quarantined else status_df["facility_mw"].fillna(0)
power_secured = (
    status_df.get("power_secured", pd.Series(False, index=status_df.index))
    .fillna(False)
    .astype(str)
    .str.strip()
    .str.lower()
    .isin(["true", "1", "yes"])
)

status_metrics = [
    (
        "Operating",
        mw_series[status_df["status"].eq("Operating")].sum(),
        "Built and operating capacity in the projects currently shown, not the full market.",
    ),
    (
        "Under Construction",
        mw_series[status_df["status"].eq("Under Construction")].sum(),
        "Under-construction capacity in the projects currently shown. Quarantined/unverified rows are excluded by default.",
    ),
    (
        "Approved + Power",
        mw_series[status_df["status"].eq("Approved") & power_secured].sum(),
        "Approved projects currently shown where public evidence or the seed flag indicates grid/power is secured.",
    ),
    (
        "Approved, Power Pending",
        mw_series[status_df["status"].eq("Approved") & ~power_secured].sum(),
        "Approved projects currently shown without explicit public evidence that grid/power is secured.",
    ),
    (
        "Announced / Proposed",
        mw_series[status_df["status"].isin(["Announced", "Proposed"])].sum(),
        "Announced or proposed capacity in the projects currently shown. These rows carry 0% risk weight until a power pathway is confirmed.",
    ),
]

s1, s2, s3, s4, s5 = st.columns(5)
for col, (label, value, help_text) in zip([s1, s2, s3, s4, s5], status_metrics):
    with col:
        st.metric(label, f"{value:,.0f} MW", help=help_text)

st.markdown("---")

# ========================================
# Hyperscaler Announcements
# ========================================
hyperscaler_path = REFERENCE_DIR / "hyperscaler_announcements.csv"
if hyperscaler_path.exists():
    hyperscaler_announcements = pd.read_csv(hyperscaler_path)

    st.markdown("### Hyperscaler & AI Demand Announcements")
    st.caption(
        "These are capex, footprint, cloud-region, or tenant/partner announcements. "
        "They are deliberately excluded from project MW totals unless a named physical "
        "project with row-level MW evidence exists in the project database."
    )

    h1, h2, h3 = st.columns(3)
    with h1:
        st.metric("Announcements", f"{len(hyperscaler_announcements):,.0f}")
    with h2:
        announcement_capex = hyperscaler_announcements["capex_aud_m"].dropna().sum()
        st.metric(
            "Announced CAPEX",
            f"A${announcement_capex:,.0f}M",
            help="Capex disclosed in hyperscaler/AI demand announcements. This is not added to project CAPEX totals.",
        )
    with h3:
        linked_mw = hyperscaler_announcements["linked_project_mw"].dropna().sum()
        st.metric(
            "Linked Project MW",
            f"{linked_mw:,.0f} MW",
            help="MW already represented in the project database through a linked operator/project row.",
        )

    hyperscaler_cols = [
        "announcement_name", "provider", "announcement_type", "announced_cities",
        "announcement_date", "capex_aud_m", "site_count_before", "site_count_after",
        "linked_project", "linked_operator", "linked_project_mw", "capacity_basis",
        "source_url", "secondary_source_url", "evidence_summary", "notes",
    ]
    available_hyperscaler_cols = [
        c for c in hyperscaler_cols if c in hyperscaler_announcements.columns
    ]
    st.dataframe(
        hyperscaler_announcements[available_hyperscaler_cols].sort_values(
            "announcement_date", ascending=False
        ),
        use_container_width=True,
        hide_index=True,
        height=260,
        column_config={
            "announcement_name": st.column_config.TextColumn("Announcement", width="medium"),
            "provider": "Provider",
            "announcement_type": st.column_config.TextColumn("Type", width="medium"),
            "announced_cities": "Cities / Regions",
            "announcement_date": "Date",
            "capex_aud_m": st.column_config.NumberColumn("CAPEX (A$M)", format="%d"),
            "site_count_before": st.column_config.NumberColumn("Sites Before", format="%d"),
            "site_count_after": st.column_config.NumberColumn("Sites After", format="%d"),
            "linked_project": "Linked Project",
            "linked_operator": "Linked Operator",
            "linked_project_mw": st.column_config.NumberColumn("Linked MW", format="%d"),
            "capacity_basis": "Basis",
            "source_url": st.column_config.LinkColumn("Source", display_text="open"),
            "secondary_source_url": st.column_config.LinkColumn("Capacity Source", display_text="open"),
            "evidence_summary": st.column_config.TextColumn("Evidence Summary", width="large"),
            "notes": st.column_config.TextColumn("Treatment", width="large"),
        },
    )

    st.markdown("---")

# ========================================
# Project Table
# ========================================
st.markdown("### Project Database")

table_df = filtered.copy()
if "include_in_project_totals" in table_df.columns:
    table_df["_row_status"] = table_df["include_in_project_totals"].fillna(True).map(
        {True: "Included", False: "Quarantined"}
    )
else:
    table_df["_row_status"] = "Included"
table_df["_quarantine_sort"] = table_df["_row_status"].eq("Quarantined").astype(int)

if show_quarantined and "include_in_project_totals" in table_df.columns:
    quarantined_count = int(table_df["_row_status"].eq("Quarantined").sum())
    included_count = int(table_df["_row_status"].eq("Included").sum())
    st.caption(
        f"Sorted by row status: {included_count} included rows first, "
        f"then {quarantined_count} quarantined rows."
    )

display_cols = [
    "_row_status",
    "project_name", "operator", "parent_company", "operator_type",
    "nem_region", "state", "suburb", "status", "size_class",
    "facility_mw", "critical_it_mw", "risked_mw", "unverified_capacity_mw",
    "include_in_project_totals", "remediation_status",
    "startup_year", "full_capacity_year", "capex_aud_m", "capex_estimated",
    "power_strategy", "workload_type", "financial_sponsor",
    "evidence_grade", "source_class", "has_source_url", "capacity_basis",
    "capacity_scope", "stage_status_caveat",
    "it_load_mw", "gross_power_mw", "power_consumption_mw", "campus_full_build_mw",
    "source_date", "source", "source_url", "issues", "remediation_notes",
]
available = [c for c in display_cols if c in table_df.columns]
sort_cols = ["_quarantine_sort", "_display_mw", "project_name"]
sort_ascending = [True, False, True]

st.dataframe(
    table_df.sort_values(sort_cols, ascending=sort_ascending)[available],
    use_container_width=True, hide_index=True, height=600,
    column_config={
        "_row_status": st.column_config.TextColumn(
            "Row Status",
            help="Included rows count in default totals. Quarantined rows are audit-trail rows excluded from default totals.",
        ),
        "project_name": "Project", "operator": "Operator", "parent_company": "Parent",
        "operator_type": "Type", "nem_region": "Region", "state": "State",
        "suburb": "Suburb", "status": "Status", "size_class": "Size",
        "facility_mw": st.column_config.NumberColumn("Facility MW", format="%d"),
        "critical_it_mw": st.column_config.NumberColumn("IT MW", format="%d"),
        "risked_mw": st.column_config.NumberColumn("Risked MW", format="%d", help=RISKED_MW_HELP),
        "unverified_capacity_mw": st.column_config.NumberColumn("Quarantined MW", format="%d"),
        "include_in_project_totals": st.column_config.CheckboxColumn("In Totals?", default=True),
        "remediation_status": "Remediation",
        "startup_year": st.column_config.NumberColumn("Startup", format="%d"),
        "full_capacity_year": st.column_config.NumberColumn("Full Capacity", format="%d"),
        "capex_aud_m": st.column_config.NumberColumn("CAPEX (A$M)", format="%d", help=CAPEX_ESTIMATION_HELP),
        "capex_estimated": st.column_config.CheckboxColumn("CAPEX Est?", default=False, help=CAPEX_ESTIMATION_HELP),
        "power_strategy": "Power Strategy", "workload_type": "Workload",
        "financial_sponsor": "Sponsor",
        "evidence_grade": st.column_config.TextColumn(
            "Evidence",
            help="A requires source URL and row-level evidence text. Current rows are C/D until remediated.",
        ),
        "source_class": "Source Class",
        "has_source_url": st.column_config.CheckboxColumn("URL?", default=False),
        "capacity_basis": "Capacity Basis",
        "capacity_scope": st.column_config.TextColumn("Capacity Scope", help=CAMPUS_SCOPE_HELP),
        "stage_status_caveat": st.column_config.TextColumn("Stage Caveat", width="large"),
        "it_load_mw": st.column_config.NumberColumn("Sourced IT MW", format="%d"),
        "gross_power_mw": st.column_config.NumberColumn("Sourced Gross MW", format="%d"),
        "power_consumption_mw": st.column_config.NumberColumn("Sourced Consumption MW", format="%d"),
        "campus_full_build_mw": st.column_config.NumberColumn("Sourced Campus MW", format="%d"),
        "source_date": "Source Date",
        "source": "Source",
        "source_url": st.column_config.LinkColumn("Source URL", display_text="open"),
        "issues": st.column_config.TextColumn("Audit Issues", width="large"),
        "remediation_notes": st.column_config.TextColumn("Remediation Notes", width="large"),
    },
)

st.markdown("---")

# ========================================
# Charts
# ========================================
st.markdown("### Visualisations")

tab1, tab2 = st.tabs(["By Size Class", "Timeline"])

with tab1:
    size_agg = filtered.groupby(["size_class", "status"])["facility_mw"].sum().reset_index()
    fig = px.bar(
        size_agg, x="size_class", y="facility_mw", color="status",
        color_discrete_map=COLOUR_PALETTE,
        title="Capacity by Size Class",
        labels={"facility_mw": "Capacity (MW)", "size_class": ""},
        barmode="stack",
    )
    fig.update_layout(**CHART_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    timeline = filtered.dropna(subset=["startup_year"])
    if not timeline.empty:
        timeline_agg = timeline.groupby(["startup_year", "status"])["facility_mw"].sum().reset_index()
        fig = px.bar(
            timeline_agg, x="startup_year", y="facility_mw", color="status",
            color_discrete_map=COLOUR_PALETTE,
            title="Capacity by Startup Year",
            labels={"facility_mw": "Capacity (MW)", "startup_year": "Year"},
            barmode="stack",
        )
        fig.update_layout(**CHART_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No startup year data available for timeline chart.")
