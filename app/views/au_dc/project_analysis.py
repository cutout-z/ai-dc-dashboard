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

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc" / "processed"

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

f4, f5, f6 = st.columns([1.4, 1, 1.2])
with f4:
    sel_evidence = st.multiselect(
        "Evidence Grade",
        evidence_grades,
        default=["All"],
        key="au_proj_evidence",
        help="A requires row-level source URL, evidence text, capacity basis, and source date where available.",
    )
with f5:
    show_quarantined = st.toggle(
        "Show Quarantined Rows",
        value=False,
        key="au_proj_show_quarantined",
        help="Quarantined rows retain unverified MW for audit trail but are excluded from default project totals.",
    )
with f6:
    min_mw = st.slider("Min MW", 0, int(projects["_display_mw"].max()), 0, key="au_proj_mw")

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
    if "capex_estimated" in filtered.columns:
        estimated_mask = filtered["capex_estimated"].fillna(False)
        disclosed_capex = filtered.loc[~estimated_mask, "capex_aud_m"].dropna().sum()
        st.metric(
            "Disclosed CAPEX",
            f"A${disclosed_capex:,.0f}M",
            help=DISCLOSED_CAPEX_HELP,
        )
    else:
        known_capex = filtered["capex_aud_m"].dropna().sum()
        st.metric("Known CAPEX", f"A${known_capex:,.0f}M" if known_capex > 0 else "N/A")
with k5:
    if "capex_estimated" in filtered.columns:
        estimated_mask = filtered["capex_estimated"].fillna(False)
        estimated_capex = filtered.loc[estimated_mask, "capex_aud_m"].dropna().sum()
        st.metric(
            "Modelled CAPEX",
            f"A${estimated_capex:,.0f}M",
            help=CAPEX_ESTIMATION_HELP,
        )
    else:
        st.metric("Modelled CAPEX", "N/A", help=CAPEX_ESTIMATION_HELP)

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
# Project Table
# ========================================
st.markdown("### Project Database")

display_cols = [
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
available = [c for c in display_cols if c in filtered.columns]

st.dataframe(
    filtered[available].sort_values("facility_mw", ascending=False),
    use_container_width=True, hide_index=True, height=600,
    column_config={
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
