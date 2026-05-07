"""Build the master project database from seed CSV + enrichment.

Reads the seed CSV (manually curated from public sources), applies risk
model, and outputs projects.parquet for the dashboard.
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models.au_dc.risk_model import apply_risk_weight
from models.au_dc.capex_model import estimate_capex

BASE_DIR = PROJECT_ROOT
SEED_CSV = BASE_DIR / "data" / "au_dc" / "reference" / "projects_seed.csv"
OPERATOR_CSV = BASE_DIR / "data" / "au_dc" / "reference" / "operator_types.csv"
PROCESSED_DIR = BASE_DIR / "data" / "au_dc" / "processed"

STAGED_CAMPUS_NOTES = {
    "CDC Marsden Park": (
        "Staged campus envelope: NSW approval covers six buildings and 504MW power "
        "consumption; Infratil's 26 Mar 2026 CDC presentation shows MP1/the first "
        "of six buildings complete. No stage-level MW was disclosed."
    ),
    "CDC Eastern Creek": (
        "Staged campus: CDC states EC1-EC4 are operational and EC5-EC6 are under "
        "construction. The >200MW figure is campus-level; no building-level MW split "
        "is stored."
    ),
    "CDC Brooklyn Campus": (
        "Staged campus: CDC states BK1 is operational while remaining Brooklyn "
        "facilities are under construction. The >350MW figure is upon-completion "
        "campus capacity; no stage-level MW split is stored."
    ),
}


def _derive_capacity_scope(row: pd.Series) -> str:
    """Classify whether a MW figure is row-level current capacity or a campus envelope."""
    basis = str(row.get("capacity_basis") or "").strip()
    status = str(row.get("status") or "").strip()
    evidence = str(row.get("evidence_quote") or "").lower()

    if basis in {"unsupported_legacy_split", "pending_row_level_source", "unverified_pipeline_estimate"}:
        return "Quarantined/unverified"
    if basis == "power_consumption_mw":
        return "Campus power-consumption envelope"
    if basis == "campus_full_build_mw":
        if "current capacity (operating)" in evidence:
            return "Campus current operating capacity"
        if status == "Operating" and "upon completion" not in evidence and "under construction" not in evidence:
            return "Campus capacity; stage split not stored"
        return "Campus full-build envelope"
    if basis in {"it_load_mw", "gross_power_mw"}:
        return "Row-level sourced capacity"
    if basis == "facility_exists_no_mw_disclosed":
        return "Facility exists; no MW disclosed"
    return "Unclassified"


def _derive_stage_status_caveat(row: pd.Series) -> str:
    campus = str(row.get("campus") or "").strip()
    project = str(row.get("project_name") or "").strip()
    key = campus if campus in STAGED_CAMPUS_NOTES else project
    if key in STAGED_CAMPUS_NOTES:
        return STAGED_CAMPUS_NOTES[key]

    scope = str(row.get("capacity_scope") or "")
    if scope in {
        "Campus full-build envelope",
        "Campus power-consumption envelope",
        "Campus capacity; stage split not stored",
    }:
        return (
            "Campus-level MW: row status is the best available project/campus status, "
            "but public data may not disclose each building or stage separately."
        )
    return ""


def build():
    print("=" * 60)
    print("Building Project Database")
    print("=" * 60)

    # Load seed data
    df = pd.read_csv(SEED_CSV)
    print(f"  Loaded {len(df)} projects from seed CSV")

    # Clean numeric columns
    numeric_cols = [
        "facility_mw", "critical_it_mw", "capex_aud_m", "startup_year",
        "full_capacity_year", "pue", "wue", "it_load_mw", "gross_power_mw",
        "power_consumption_mw", "grid_connection_mva", "campus_full_build_mw",
        "unverified_capacity_mw",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "include_in_project_totals" in df.columns:
        df["include_in_project_totals"] = (
            df["include_in_project_totals"]
            .fillna(True)
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(["true", "1", "yes"])
        )
    else:
        df["include_in_project_totals"] = True

    # Apply risk model
    df = apply_risk_weight(df, status_col="status", mw_col="facility_mw")

    df["capacity_scope"] = df.apply(_derive_capacity_scope, axis=1)
    df["stage_status_caveat"] = df.apply(_derive_stage_status_caveat, axis=1)

    # Estimate CAPEX where not disclosed
    df = estimate_capex(df)

    # Enrich with operator type from reference table
    operators = pd.read_csv(OPERATOR_CSV)
    df = df.merge(
        operators[["operator", "listed", "ticker"]],
        on="operator",
        how="left",
        suffixes=("", "_ref"),
    )

    # Size classification
    df["size_class"] = pd.cut(
        df["facility_mw"],
        bins=[0, 10, 50, 200, float("inf")],
        labels=["Small (<10MW)", "Mid-size (10-50MW)", "Large (50-200MW)", "Hyperscale (>200MW)"],
    )

    # Save
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "projects.parquet"
    df.to_parquet(out_path, index=False)
    print(f"  Saved: {out_path.name} ({len(df)} rows)")

    # Summary
    print("\n--- Summary ---")
    print(f"  Total projects: {len(df)}")
    print(f"  Total facility MW (unrisked): {df['facility_mw'].sum():,.0f}")
    print(f"  Total facility MW (risked):   {df['risked_mw'].sum():,.0f}")
    print(f"\n  By status:")
    for status, group in df.groupby("status"):
        print(f"    {status}: {len(group)} projects, {group['facility_mw'].sum():,.0f} MW")
    print(f"\n  By operator:")
    for op, group in df.groupby("operator"):
        print(f"    {op}: {len(group)} projects, {group['facility_mw'].sum():,.0f} MW")


if __name__ == "__main__":
    build()
    # Run data quality spot check after every build
    import importlib.util, subprocess
    spot_check = PROJECT_ROOT / "scripts" / "au_dc_spot_check.py"
    if spot_check.exists():
        subprocess.run([sys.executable, str(spot_check)], check=False)
