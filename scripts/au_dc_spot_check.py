"""AU DC data quality spot check.

Runs after build_project_db.py and validates the projects parquet against
a set of data quality rules. Writes results to processed/spot_check.json
so the Source Health dashboard can surface issues.

Exit codes: 0 = clean, 1 = warnings, 2 = errors
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARQUET = PROJECT_ROOT / "data" / "au_dc" / "processed" / "projects.parquet"
SEED_CSV = PROJECT_ROOT / "data" / "au_dc" / "reference" / "projects_seed.csv"
OUT_JSON = PROJECT_ROOT / "data" / "au_dc" / "processed" / "spot_check.json"

# Sources that are inherently estimates — don't flag these for vague attribution
ESTIMATE_EXEMPT_TYPES = {"Hyperscaler"}

# Sources that are too vague for high-MW colocation/developer projects
VAGUE_SOURCE_PATTERNS = [
    "press estimate",
    "industry benchmark",
    "press reports",
    "press,",
    ", press",
]

# MW threshold above which a vague source is flagged
VAGUE_SOURCE_MW_THRESHOLD = 50


def _is_vague(source: str) -> bool:
    if not source or pd.isna(source):
        return True
    s = str(source).lower().strip()
    return any(p in s for p in VAGUE_SOURCE_PATTERNS)


def run_checks(df: pd.DataFrame, seed_row_count: int) -> list[dict]:
    checks = []

    # ── 1. Seed vs parquet row count ────────────────────────────────────
    if len(df) != seed_row_count:
        checks.append({
            "level": "error",
            "code": "seed_parquet_row_mismatch",
            "message": (
                f"projects.parquet has {len(df)} rows but projects_seed.csv has "
                f"{seed_row_count} rows — ETL may have dropped or duplicated records."
            ),
            "count": abs(len(df) - seed_row_count),
            "projects": [],
        })
    else:
        checks.append({
            "level": "ok",
            "code": "seed_parquet_row_count",
            "message": f"Seed and parquet row counts match ({len(df)} rows).",
            "count": 0,
            "projects": [],
        })

    # ── 2. Missing source attribution ───────────────────────────────────
    no_source = df[df["source"].isna() | (df["source"].astype(str).str.strip() == "")]
    if not no_source.empty:
        checks.append({
            "level": "warn",
            "code": "missing_source",
            "message": f"{len(no_source)} project(s) have no source attribution.",
            "count": len(no_source),
            "projects": no_source["project_name"].tolist()[:10],
        })
    else:
        checks.append({
            "level": "ok",
            "code": "missing_source",
            "message": "All projects have source attribution.",
            "count": 0,
            "projects": [],
        })

    # ── 3. Vague sources for non-hyperscaler projects > threshold ───────
    non_hyper = df[df["operator_type"] != "Hyperscaler"] if "operator_type" in df.columns else df
    high_mw = non_hyper[
        (non_hyper["facility_mw"] >= VAGUE_SOURCE_MW_THRESHOLD) &
        (non_hyper["source"].apply(_is_vague))
    ]
    if not high_mw.empty:
        checks.append({
            "level": "warn",
            "code": "vague_source_high_mw",
            "message": (
                f"{len(high_mw)} non-hyperscaler project(s) with ≥{VAGUE_SOURCE_MW_THRESHOLD} MW "
                f"have vague or missing source attribution."
            ),
            "count": len(high_mw),
            "projects": high_mw[["project_name", "operator", "facility_mw", "source"]].to_dict("records"),
        })
    else:
        checks.append({
            "level": "ok",
            "code": "vague_source_high_mw",
            "message": f"All high-MW non-hyperscaler projects (≥{VAGUE_SOURCE_MW_THRESHOLD} MW) have specific sources.",
            "count": 0,
            "projects": [],
        })

    # ── 4. Missing facility_mw for pipeline projects ─────────────────────
    pipeline_no_mw = df[
        (df["status"].isin(["Under Construction", "Proposed", "Approved"])) &
        (df["facility_mw"].isna() | (df["facility_mw"] == 0))
    ]
    if not pipeline_no_mw.empty:
        checks.append({
            "level": "warn",
            "code": "pipeline_missing_mw",
            "message": (
                f"{len(pipeline_no_mw)} pipeline project(s) (UC/Proposed/Approved) "
                f"have no facility_mw — they won't appear in capacity charts."
            ),
            "count": len(pipeline_no_mw),
            "projects": pipeline_no_mw["project_name"].tolist(),
        })
    else:
        checks.append({
            "level": "ok",
            "code": "pipeline_missing_mw",
            "message": "All pipeline projects have facility_mw populated.",
            "count": 0,
            "projects": [],
        })

    # ── 5. Top operators with zero operating capacity ────────────────────
    top10_unrisked = (
        df.groupby("operator")["facility_mw"].sum()
        .sort_values(ascending=False)
        .head(10)
        .index.tolist()
    )
    op_operating = df[df["status"] == "Operating"].groupby("operator")["facility_mw"].sum()
    top10_no_operating = [
        op for op in top10_unrisked
        if op_operating.get(op, 0) == 0
    ]
    if top10_no_operating:
        checks.append({
            "level": "warn",
            "code": "top_operator_no_operating",
            "message": (
                f"{len(top10_no_operating)} top-10 operator(s) by total MW have zero operating capacity — "
                f"may be correct (pure pipeline) or a data gap."
            ),
            "count": len(top10_no_operating),
            "projects": top10_no_operating,
        })
    else:
        checks.append({
            "level": "ok",
            "code": "top_operator_no_operating",
            "message": "All top-10 operators have some operating capacity.",
            "count": 0,
            "projects": [],
        })

    # ── 6. Status distribution sanity ───────────────────────────────────
    status_counts = df["status"].value_counts(normalize=True)
    operating_share = status_counts.get("Operating", 0)
    if operating_share < 0.30:
        checks.append({
            "level": "warn",
            "code": "low_operating_share",
            "message": (
                f"Only {operating_share:.0%} of projects are Operating — "
                f"unusually low, may indicate missing operating data."
            ),
            "count": int(operating_share * len(df)),
            "projects": [],
        })
    else:
        checks.append({
            "level": "ok",
            "code": "operating_share",
            "message": f"{operating_share:.0%} of projects are Operating (sanity range ≥30%).",
            "count": 0,
            "projects": [],
        })

    # ── 7. Operators with stated large capacity but stale seed source ────
    # Flag entries where source is "CDC 2024 Sustainability Report" or
    # similarly dated >18 months ago for high-MW operating entries
    high_mw_operating = df[
        (df["status"] == "Operating") &
        (df["facility_mw"] >= 100)
    ]
    old_source_patterns = ["2023", "2022", "2021"]
    old_source_entries = high_mw_operating[
        high_mw_operating["source"].apply(
            lambda s: any(p in str(s) for p in old_source_patterns) if pd.notna(s) else False
        )
    ]
    if not old_source_entries.empty:
        checks.append({
            "level": "warn",
            "code": "stale_source_high_mw_operating",
            "message": (
                f"{len(old_source_entries)} operating project(s) with ≥100 MW reference sources from "
                f"2021–2023 — check for updated disclosures."
            ),
            "count": len(old_source_entries),
            "projects": old_source_entries[["project_name", "operator", "facility_mw", "source"]].to_dict("records"),
        })
    else:
        checks.append({
            "level": "ok",
            "code": "stale_source_high_mw_operating",
            "message": "No high-MW operating projects referencing sources older than 2023.",
            "count": 0,
            "projects": [],
        })

    return checks


def main() -> int:
    if not PARQUET.exists():
        print("ERROR: projects.parquet not found — run build_project_db.py first.")
        return 2

    df = pd.read_parquet(PARQUET)
    seed_row_count = sum(1 for _ in open(SEED_CSV)) - 1  # subtract header

    checks = run_checks(df, seed_row_count)

    errors = sum(1 for c in checks if c["level"] == "error")
    warnings = sum(1 for c in checks if c["level"] == "warn")
    oks = sum(1 for c in checks if c["level"] == "ok")

    result = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "project_count": len(df),
        "total_mw_unrisked": float(df["facility_mw"].sum()),
        "total_mw_risked": float(df["risked_mw"].sum()) if "risked_mw" in df.columns else None,
        "checks": checks,
        "summary": {"errors": errors, "warnings": warnings, "ok": oks},
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))

    print(f"\n--- AU DC Spot Check ---")
    print(f"  Projects: {len(df)}  |  Unrisked MW: {df['facility_mw'].sum():,.0f}")
    print(f"  Results: {errors} error(s), {warnings} warning(s), {oks} OK")
    for c in checks:
        icon = {"error": "✗", "warn": "⚠", "ok": "✓"}.get(c["level"], "?")
        print(f"  {icon}  [{c['code']}] {c['message']}")

    if errors:
        return 2
    if warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
