"""Audit AU data centre project evidence quality.

This is a triage audit, not a source-verification pass. It classifies each
project row by how auditable the current seed data is and highlights rows that
need primary-source remediation before they should drive charts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_CSV = PROJECT_ROOT / "data" / "au_dc" / "reference" / "projects_seed.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "au_dc" / "processed"
AUDIT_CSV = PROCESSED_DIR / "project_evidence_audit.csv"
AUDIT_MD = PROCESSED_DIR / "project_evidence_audit.md"


VAGUE_EXACT = {
    "press",
    "press estimate",
    "press reports",
    "company website",
}

AGGREGATOR_TERMS = (
    "datacentermap.com",
    "datacenterhawk.com",
    "baxtel.com",
)

NAMED_SECONDARY_TERMS = (
    "data center dynamics",
    "crn.com.au",
    "itbrief.com.au",
    "pr newswire",
    "townsville city council",
    "the urban developer",
)

SPECIFIC_PRIMARY_TERMS = (
    "airtrunk press release",
    "aws announcement",
    "asx",
    "commitment",
    "nsw ssd",
    "planning portal",
    "infratil investor presentation",
    "investor presentation",
    "filings",
    "announcement",
    "expansion",
    "press release",
    "website",
    "nci.org.au",
    "pawsey.org.au",
    "vaultcloud.com.au",
    "infraco.telstra.com.au",
    "leadingedgedc.com",
    "dxn.solutions",
    "vantage-dc.com",
)

ESTIMATE_TERMS = (
    "estimate",
    "industry benchmark",
    "design target",
    "global avg",
    "portfolio avg",
    "inferred",
    "synthesis",
    "placeholder",
)

CAPACITY_BASIS_FIELDS = {
    "it_load_mw": "it_load_mw",
    "gross_power_mw": "gross_power_mw",
    "power_consumption_mw": "power_consumption_mw",
    "grid_connection_mva": "grid_connection_mva",
    "campus_full_build_mw": "campus_full_build_mw",
}

PRIMARY_URL_DOMAINS = (
    "nextdc.com",
    "planningportal.nsw.gov.au",
    "keppel.com",
    "macquariedatacentres.com",
    "macquarietechnologygroup.com",
    "stackinfra.com",
    "cdc.com.au",
    "cdc.com",
    "infratil.com",
    "airtrunk.com",
    "vantage-dc.com",
    "equinix.com",
    "aws.amazon.com",
    "microsoft.com",
    "oracle.com",
    "cloud.google.com",
)

SECONDARY_URL_DOMAINS = (
    "datacenterdynamics.com",
    "datacentremagazine.com",
    "computeforecast.com",
    "crn.com.au",
    "capitalbrief.com",
    "prnewswire.com",
)


@dataclass(frozen=True)
class SourceClassification:
    source_class: str
    evidence_grade: str
    base_issue: str


def _norm(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def classify_source(source: object) -> SourceClassification:
    s = _norm(source)
    if not s:
        return SourceClassification("missing", "E", "No source label.")
    if s in VAGUE_EXACT:
        return SourceClassification("vague_label", "D", "Source label is too broad to audit.")
    if "press estimate" in s or "press reports" in s:
        return SourceClassification("estimate_or_reports", "D", "Capacity appears to be estimated or sourced from unspecified reports.")
    if any(term in s for term in AGGREGATOR_TERMS):
        return SourceClassification("directory_or_aggregator", "C", "Directory sources are useful leads but not primary evidence.")
    if any(term in s for term in NAMED_SECONDARY_TERMS):
        return SourceClassification("named_secondary", "C", "Named secondary source needs primary-source cross-check.")
    if any(term in s for term in SPECIFIC_PRIMARY_TERMS):
        return SourceClassification("label_only_primary_or_filing", "B", "Likely primary/filing source, but no URL/page/evidence text is stored.")
    return SourceClassification("unclassified_label", "D", "Source label could not be classified.")


def _has_url(row: pd.Series) -> bool:
    for col in ("source_url", "evidence_url", "url"):
        if col in row and _norm(row[col]).startswith(("http://", "https://")):
            return True
    return False


def _url_class(row: pd.Series) -> str | None:
    url = ""
    for col in ("source_url", "evidence_url", "url"):
        if col in row and _norm(row[col]).startswith(("http://", "https://")):
            url = _norm(row[col])
            break
    if not url:
        return None

    host = urlparse(url).netloc.removeprefix("www.")
    if any(host == domain or host.endswith(f".{domain}") for domain in PRIMARY_URL_DOMAINS):
        return "primary_url"
    if any(host == domain or host.endswith(f".{domain}") for domain in SECONDARY_URL_DOMAINS):
        return "named_secondary_url"
    if any(domain in host for domain in AGGREGATOR_TERMS):
        return "directory_or_aggregator"
    return "source_url_unclassified"


def audit_projects(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for _, row in df.iterrows():
        source = classify_source(row.get("source"))
        issues = [source.base_issue]
        grade = source.evidence_grade
        source_class = source.source_class

        has_url = _has_url(row)
        url_class = _url_class(row)
        if url_class:
            source_class = url_class

        if not has_url:
            issues.append("No source_url/evidence_url column with a retrievable URL.")
            if grade == "B":
                grade = "C"
        else:
            evidence_quote = _norm(row.get("evidence_quote"))
            capacity_basis = _norm(row.get("capacity_basis"))
            if not evidence_quote:
                issues.append("Source URL is present but no evidence_quote is stored.")
            if not capacity_basis:
                issues.append("Source URL is present but no capacity_basis is stored.")

            if evidence_quote and capacity_basis:
                split_field = CAPACITY_BASIS_FIELDS.get(capacity_basis)
                if split_field and split_field in row and pd.isna(row.get(split_field)):
                    issues.append(f"capacity_basis is {capacity_basis}, but {split_field} is blank.")
                if source_class == "primary_url":
                    grade = "A"
                elif source_class == "named_secondary_url":
                    grade = "B"
                elif source_class == "directory_or_aggregator":
                    grade = "C"
                elif grade in {"C", "D", "E"}:
                    grade = "C"

        facility_mw = row.get("facility_mw")
        critical_it_mw = row.get("critical_it_mw")
        capex_aud_m = row.get("capex_aud_m")
        status = row.get("status")
        operator_type = row.get("operator_type")
        source_label = _norm(row.get("source"))
        pue_source = _norm(row.get("pue_source"))
        remediation_status = _norm(row.get("remediation_status"))

        if pd.isna(facility_mw):
            issues.append("No facility_mw recorded.")
        elif facility_mw >= 50 and grade in {"C", "D", "E"}:
            issues.append("High-MW row lacks audit-grade primary evidence.")

        if operator_type == "Hyperscaler":
            if "estimate" in source_label or row.get("suburb") == "Various":
                issues.append("Hyperscaler regional estimate rather than named physical facility.")
                grade = "D"

        if status == "Under Construction":
            power_secured = _norm(row.get("power_secured"))
            if power_secured not in {"true", "1", "yes", "false", "0", "no"}:
                issues.append("Under-construction row has no explicit power_secured evidence flag.")

        if pd.notna(facility_mw) and pd.isna(critical_it_mw):
            issues.append("No critical_it_mw, so energy/load calculations infer IT load from PUE.")

        if pd.isna(capex_aud_m):
            issues.append("No disclosed capex; downstream model fills estimated capex.")

        if any(term in pue_source for term in ESTIMATE_TERMS):
            issues.append("PUE/WUE is benchmark, design-target, or portfolio/global average, not facility-specific.")

        if "future build" in _norm(row.get("project_name")) or "future build" in _norm(row.get("campus")):
            issues.append("Future-build placeholder label.")
            grade = "E"

        if remediation_status.startswith("quarantined"):
            issues.append("Excluded from project capacity totals pending row-level MW verification.")
            grade = "Q"

        rows.append(
            {
                "project_name": row.get("project_name"),
                "campus": row.get("campus"),
                "operator": row.get("operator"),
                "operator_type": operator_type,
                "state": row.get("state"),
                "nem_region": row.get("nem_region"),
                "status": status,
                "facility_mw": facility_mw,
                "critical_it_mw": critical_it_mw,
                "startup_year": row.get("startup_year"),
                "source": row.get("source"),
                "source_url": row.get("source_url"),
                "source_date": row.get("source_date"),
                "capacity_basis": row.get("capacity_basis"),
                "unverified_capacity_mw": row.get("unverified_capacity_mw"),
                "include_in_project_totals": row.get("include_in_project_totals"),
                "remediation_status": row.get("remediation_status"),
                "remediation_notes": row.get("remediation_notes"),
                "source_class": source_class,
                "evidence_grade": grade,
                "has_source_url": has_url,
                "issue_count": len([i for i in issues if i]),
                "issues": " | ".join(i for i in issues if i),
            }
        )

    audit = pd.DataFrame(rows)
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
    audit["_grade_order"] = audit["evidence_grade"].map(grade_order).fillna(99)
    return audit.sort_values(["_grade_order", "facility_mw"], ascending=[False, False]).drop(columns="_grade_order")


def write_markdown(audit: pd.DataFrame) -> None:
    total_rows = len(audit)
    total_mw = float(audit["facility_mw"].fillna(0).sum())
    rows_with_url = int(audit["has_source_url"].sum())
    high_mw = audit[audit["facility_mw"].fillna(0) >= 50]
    high_mw_weak = high_mw[high_mw["evidence_grade"].isin(["C", "D", "E", "Q"])]
    by_grade = (
        audit.groupby("evidence_grade", dropna=False)
        .agg(rows=("project_name", "count"), mw=("facility_mw", "sum"))
        .reset_index()
        .sort_values("evidence_grade")
    )
    by_source = (
        audit.groupby("source_class", dropna=False)
        .agg(rows=("project_name", "count"), mw=("facility_mw", "sum"))
        .reset_index()
        .sort_values("mw", ascending=False)
    )
    top_risks = audit[
        audit["evidence_grade"].isin(["D", "E", "Q"])
        & (audit["facility_mw"].fillna(0).gt(0) | audit["unverified_capacity_mw"].fillna(0).gt(0))
    ].assign(
        remediation_mw=lambda d: d["facility_mw"].fillna(d["unverified_capacity_mw"])
    ).sort_values("remediation_mw", ascending=False).head(25)

    lines = [
        "# AU DC Project Evidence Audit",
        "",
        "Generated by `scripts/au_dc_project_evidence_audit.py`.",
        "",
        "## Executive Findings",
        "",
        f"- Rows audited: {total_rows}",
        f"- Total recorded facility MW: {total_mw:,.1f}",
        f"- Rows with retrievable source URL stored in the dataset: {rows_with_url}/{total_rows}",
        f"- High-MW rows (>=50 MW): {len(high_mw)} rows, {high_mw['facility_mw'].sum():,.1f} MW",
        f"- High-MW rows with weak, non-primary, or quarantined evidence grade (C/D/E/Q): {len(high_mw_weak)} rows, {high_mw_weak['facility_mw'].sum():,.1f} MW",
        "",
        "Rows graded A/B have row-level source URLs, evidence text, and capacity basis. Rows graded Q are retained as an audit trail but excluded from project capacity totals until remediated.",
        "",
        "## Evidence Grade Definitions",
        "",
        "- A: primary/company/regulator source URL with row-level evidence text and capacity basis.",
        "- B: named secondary source URL with row-level evidence text and capacity basis.",
        "- C: plausible but needs cross-check, usually secondary source, directory, or primary label downgraded because no URL is stored.",
        "- D: vague, estimated, regional, or insufficient source label.",
        "- E: missing source or placeholder/residual row.",
        "- Q: quarantined from project capacity totals pending row-level MW verification.",
        "",
        "## By Evidence Grade",
        "",
        by_grade.to_markdown(index=False),
        "",
        "## By Source Class",
        "",
        by_source.to_markdown(index=False),
        "",
        "## Largest Q Rows To Remediate First",
        "",
        top_risks[
            ["project_name", "operator", "status", "facility_mw", "source", "issues"]
        ].to_markdown(index=False),
        "",
        "## Methodology Problems Identified",
        "",
        "- `facility_mw` mixes IT load, gross facility power, regional capacity, planned campus power, and sometimes network/substation capacity.",
        "- `critical_it_mw` is sparse, so energy calculations often infer IT load from PUE rather than sourced facility data.",
        "- `pue` and `wue` are frequently portfolio averages or design targets, but are displayed beside individual projects.",
        "- Under-construction projects are risk-weighted at 100% even when `power_secured` is blank.",
        "- Proposed hyperscaler rows use regional estimates and `Various` locations, so they are not comparable with named physical campuses.",
        "- CAPEX is mostly modelled from benchmarks, so it should never be aggregated with disclosed market spend.",
        "",
        "## Recommended Remediation Rules",
        "",
        "- Add mandatory `source_url`, `source_date`, `evidence_quote`, `source_page_or_section`, `capacity_basis`, and `last_verified_at` fields before treating a row as verified.",
        "- Split capacity into separate fields: `it_load_mw`, `gross_power_mw`, `grid_connection_mva`, and `campus_full_build_mw`.",
        "- Quarantine D/E rows from default capacity totals until they are remediated.",
        "- Keep regional hyperscaler estimates in a separate demand/market-sizing table, not the physical project table.",
        "- Require explicit power evidence before assigning 100% risk weight to under-construction rows.",
    ]
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    df = pd.read_csv(SEED_CSV)
    audit = audit_projects(df)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_CSV, index=False)
    write_markdown(audit)

    weak = audit[audit["evidence_grade"].isin(["D", "E", "Q"])]
    print(f"Wrote {AUDIT_CSV.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {AUDIT_MD.relative_to(PROJECT_ROOT)}")
    print(f"Rows audited: {len(audit)}")
    print(f"D/E/Q rows: {len(weak)}")
    print(f"D/E/Q MW: {weak['facility_mw'].fillna(weak.get('unverified_capacity_mw')).fillna(0).sum():,.1f}")
    return 1 if not weak.empty else 0


if __name__ == "__main__":
    raise SystemExit(main())
