"""Project Analysis — Full project database with filtering."""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

from app.lib.au_dc_charts import COLOUR_PALETTE, CHART_LAYOUT
from app.lib.au_dc_methodology import (
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
st.sidebar.header("Filters")

statuses = ["All"] + sorted(projects["status"].unique().tolist())
sel_status = st.sidebar.multiselect("Status", statuses, default=["All"], key="au_proj_status")

regions_list = ["All"] + sorted(projects["nem_region"].unique().tolist())
sel_region = st.sidebar.multiselect("Region", regions_list, default=["All"], key="au_proj_region")

op_types = ["All"] + sorted(projects["operator_type"].dropna().unique().tolist())
sel_op_type = st.sidebar.multiselect("Operator Type", op_types, default=["All"], key="au_proj_optype")

if "evidence_grade" in projects.columns:
    evidence_grades = ["All"] + sorted(projects["evidence_grade"].dropna().unique().tolist())
    sel_evidence = st.sidebar.multiselect(
        "Evidence Grade",
        evidence_grades,
        default=["All"],
        key="au_proj_evidence",
        help="Current rows are C/D because source URLs and evidence extracts are not yet stored.",
    )
else:
    sel_evidence = ["All"]

show_quarantined = st.sidebar.toggle(
    "Show Quarantined Rows",
    value=False,
    key="au_proj_show_quarantined",
    help="Quarantined rows retain unverified MW for audit trail but are excluded from default project totals.",
)

min_mw = st.sidebar.slider("Min Facility MW", 0, int(projects["facility_mw"].max()), 0, key="au_proj_mw")

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
filtered = filtered[filtered["facility_mw"] >= min_mw]

# ========================================
# KPIs
# ========================================
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Projects Shown", len(filtered))
with k2:
    st.metric(
        "Recorded MW (Unverified)",
        f"{filtered['facility_mw'].sum():,.0f}",
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

st.markdown("### Capacity by Development Status — Projects Shown Only")
st.caption(
    "These MW totals use the current filters and exclude quarantined/unverified rows unless "
    "`Show Quarantined Rows` is enabled. They are not an estimate of the full Australian data centre universe."
)

status_df = filtered.copy()
mw_series = status_df["facility_mw"].fillna(0)
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
# Project Deep Dive
# ========================================
st.markdown("### Project Deep Dive")

project_names = sorted(filtered["project_name"].unique().tolist())
if not project_names:
    st.info("No projects match the current filters.")
    st.stop()
selected_project = st.selectbox("Select Project", project_names, key="au_proj_select")

proj = filtered[filtered["project_name"] == selected_project]
if not proj.empty:
    p = proj.iloc[0]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Core Attributes")
        st.markdown(f"**Operator:** {p.get('operator', 'N/A')}")
        st.markdown(f"**Parent Company:** {p.get('parent_company', 'N/A')}")
        st.markdown(f"**Operator Type:** {p.get('operator_type', 'N/A')}")
        st.markdown(f"**Status:** {p.get('status', 'N/A')}")
        st.markdown(f"**Workload:** {p.get('workload_type', 'N/A')}")
        st.markdown(f"**Power Strategy:** {p.get('power_strategy', 'N/A')}")
        if "evidence_grade" in p:
            st.markdown(f"**Evidence Grade:** {p.get('evidence_grade', 'N/A')}")
            st.markdown(f"**Source Class:** {p.get('source_class', 'N/A')}")
        if pd.notna(p.get("capacity_basis")) and str(p.get("capacity_basis")).strip():
            st.markdown(f"**Capacity Basis:** {p.get('capacity_basis')}")

    with col2:
        st.markdown("#### Location & Timing")
        st.markdown(f"**NEM Region:** {p.get('nem_region', 'N/A')}")
        st.markdown(f"**State:** {p.get('state', 'N/A')}")
        st.markdown(f"**Suburb:** {p.get('suburb', 'N/A')}")
        st.markdown(f"**Startup Year:** {int(p['startup_year']) if pd.notna(p.get('startup_year')) else 'N/A'}")
        st.markdown(f"**Full Capacity:** {int(p['full_capacity_year']) if pd.notna(p.get('full_capacity_year')) else 'N/A'}")

    with col3:
        st.markdown("#### Technical & Economics")
        st.markdown(f"**Facility Power:** {p.get('facility_mw', 'N/A'):,.0f} MW" if pd.notna(p.get('facility_mw')) else "**Facility Power:** N/A")
        st.markdown(f"**Critical IT Power:** {p.get('critical_it_mw', 'N/A'):,.0f} MW" if pd.notna(p.get('critical_it_mw')) else "**Critical IT Power:** N/A")
        split_capacity = [
            ("Sourced IT Load", p.get("it_load_mw")),
            ("Sourced Gross Power", p.get("gross_power_mw")),
            ("Sourced Power Consumption", p.get("power_consumption_mw")),
            ("Sourced Campus Full Build", p.get("campus_full_build_mw")),
        ]
        for label, value in split_capacity:
            if pd.notna(value):
                st.markdown(f"**{label}:** {value:,.0f} MW")
        st.metric(
            "Risk Weight",
            f"{p.get('risk_weight', 'N/A'):.0%}" if pd.notna(p.get('risk_weight')) else "N/A",
            help=RISKED_MW_HELP,
        )
        st.metric(
            "Risked MW",
            f"{p.get('risked_mw', 'N/A'):,.0f} MW" if pd.notna(p.get('risked_mw')) else "N/A",
            help=RISKED_MW_HELP,
        )
        capex = p.get('capex_aud_m')
        capex_est = p.get('capex_estimated', False)
        if pd.notna(capex):
            est_label = " (estimated)" if capex_est else ""
            st.metric("CAPEX", f"A${capex:,.0f}M{est_label}", help=CAPEX_ESTIMATION_HELP)
        else:
            st.metric("CAPEX", "Not disclosed", help=CAPEX_ESTIMATION_HELP)
        st.markdown(f"**Size Class:** {p.get('size_class', 'N/A')}")

    # Efficiency metrics
    project_pue = p.get("pue") if pd.notna(p.get("pue")) else None
    project_wue = p.get("wue") if pd.notna(p.get("wue")) else None
    pue_source = p.get("pue_source", "")

    if project_pue or project_wue:
        st.markdown("---")
        st.markdown("#### Efficiency Metrics")
        eff1, eff2 = st.columns(2)
        with eff1:
            st.metric("PUE", f"{project_pue:.2f}" if project_pue else "N/A")
        with eff2:
            st.metric("WUE (L/kWh)", f"{project_wue:.2f}" if project_wue else "N/A")
        if pue_source:
            st.caption(f"Source: {pue_source}")

    # Estimated energy consumption
    if pd.notna(p.get("facility_mw")):
        st.markdown("---")
        st.markdown("#### Estimated Energy Metrics")
        default_pue = project_pue if project_pue else 1.4
        pue = st.slider("PUE (adjust to override)", 1.05, 2.0, float(default_pue), 0.01, key="au_proj_pue")
        it_mw = p["critical_it_mw"] if pd.notna(p.get("critical_it_mw")) else p["facility_mw"] / pue
        facility_mw = p["facility_mw"]
        annual_gwh = facility_mw * 8760 / 1000

        e1, e2, e3 = st.columns(3)
        with e1:
            st.metric("Max Annual Energy", f"{annual_gwh:,.0f} GWh")
        with e2:
            st.metric("Equivalent Homes", f"{annual_gwh * 1000 / 6.5:,.0f}")
        with e3:
            st.metric("Estimated IT MW", f"{it_mw:,.0f} MW")

    st.markdown(f"**Source:** {p.get('source', 'N/A')}")
    if pd.notna(p.get("source_url")) and str(p.get("source_url")).strip():
        st.link_button("Open Source", str(p.get("source_url")))
    audit_issues = p.get("issues")
    if pd.notna(audit_issues) and str(audit_issues).strip():
        st.warning(str(audit_issues), icon=":material/warning:")

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
