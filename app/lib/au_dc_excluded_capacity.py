"""Public-source excluded capacity overlays for AU data-centre views."""

from __future__ import annotations

import pandas as pd


def _number_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _excluded_mask(df: pd.DataFrame) -> pd.Series:
    if "include_in_project_totals" not in df.columns:
        return pd.Series(True, index=df.index)
    return ~(
        df["include_in_project_totals"]
        .fillna(False)
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes"])
    )


def _row_capacity_mw(df: pd.DataFrame) -> pd.Series:
    """Use facility MW first, then IT MW, to avoid double-counting a lead row."""
    facility_mw = _number_series(df, "facility_mw")
    it_mw = _number_series(df, "critical_it_mw")
    return facility_mw.where(facility_mw.gt(0), it_mw)


def public_excluded_capacity_overlay(
    projects: pd.DataFrame,
    aggregate_guidance: pd.DataFrame | None = None,
    site_leads: pd.DataFrame | None = None,
) -> dict[str, float | int]:
    """Summarise public-source capacity excluded from default project totals.

    This is a lead-screening overlay, not an additive market-capacity estimate.
    Components can use different capacity bases and may overlap until reconciled
    to named project rows.
    """
    if projects.empty:
        quarantined_project_mw = 0.0
        quarantined_project_rows = 0
    else:
        quarantined_projects = projects[_excluded_mask(projects)].copy()
        quarantined_project_rows = len(quarantined_projects)
        quarantined_project_mw = _number_series(
            quarantined_projects, "unverified_capacity_mw"
        ).sum()

    if aggregate_guidance is None or aggregate_guidance.empty:
        unmatched_aggregate_mw = 0.0
        aggregate_records = 0
    else:
        excluded_guidance = aggregate_guidance[_excluded_mask(aggregate_guidance)].copy()
        unmatched = _number_series(excluded_guidance, "unmatched_capacity_mw")
        unmatched_aggregate_mw = unmatched.sum()
        aggregate_records = int(unmatched.gt(0).sum())

    if site_leads is None or site_leads.empty:
        sourced_site_lead_mw = 0.0
        site_leads_with_mw = 0
    else:
        excluded_site_leads = site_leads[_excluded_mask(site_leads)].copy()
        lead_mw = _row_capacity_mw(excluded_site_leads)
        sourced_site_lead_mw = lead_mw.sum()
        site_leads_with_mw = int(lead_mw.gt(0).sum())

    return {
        "quarantined_project_mw": float(quarantined_project_mw),
        "quarantined_project_rows": int(quarantined_project_rows),
        "unmatched_aggregate_mw": float(unmatched_aggregate_mw),
        "aggregate_records_with_mw": int(aggregate_records),
        "sourced_site_lead_mw": float(sourced_site_lead_mw),
        "site_leads_with_mw": int(site_leads_with_mw),
        "screening_total_mw": float(
            quarantined_project_mw + unmatched_aggregate_mw + sourced_site_lead_mw
        ),
    }


def excluded_capacity_components(overlay: dict[str, float | int]) -> pd.DataFrame:
    """Return a chart/table-ready breakdown for the excluded capacity overlay."""
    return pd.DataFrame(
        [
            {
                "component": "Quarantined named project rows",
                "mw": overlay["quarantined_project_mw"],
                "rows": overlay["quarantined_project_rows"],
                "treatment": "Named rows retained for audit, excluded from default project totals.",
            },
            {
                "component": "Unmatched aggregate guidance",
                "mw": overlay["unmatched_aggregate_mw"],
                "rows": overlay["aggregate_records_with_mw"],
                "treatment": "Operator or platform guidance not yet mapped to named project rows.",
            },
            {
                "component": "Physical site leads",
                "mw": overlay["sourced_site_lead_mw"],
                "rows": overlay["site_leads_with_mw"],
                "treatment": "Named physical leads kept outside project totals pending promotion.",
            },
        ]
    )
