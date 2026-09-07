"""AU DC capacity-scope helpers (S2-06).

Separates operating-stage MW from campus envelopes and keeps undated
pipeline out of fixed forecast years, so no dashboard view silently treats
a campus envelope as fully operating-stage or pins undated projects to a
delivery year.

Scope taxonomy (capacity_scope is derived in etl/au_dc/build_project_db.py):

- Directly evidenced operating-stage: rows whose stored capacity basis is a
  row-level figure ("Row-level sourced capacity") or a campus figure whose
  own evidence says it is current operating capacity ("Campus current
  operating capacity").
- Operating campus envelope, stage split not stored: Operating rows whose MW
  is a campus-level figure with no stored building/stage allocation. The row
  status is the best available campus label and cannot be read as "every MW
  in this row is currently operating-stage".

Timeline partition (forecast_partition): Operating rows without a sourced
startup year are existing capacity and are shown from chart start (the
existing 2019 convention, retained so installed capacity is not hidden).
Non-operating rows without a sourced startup/delivery year are returned in
the undated bucket — never pinned to a fixed delivery year.
"""

from __future__ import annotations

import pandas as pd

# capacity_scope values that constitute direct evidence of operating-stage MW.
OPERATING_STAGE_EVIDENCED_SCOPES = frozenset(
    {
        "Row-level sourced capacity",
        "Campus current operating capacity",
    }
)

# Operating rows whose MW is a campus envelope with no stored stage split.
UNALLOCATED_OPERATING_SCOPE = "Campus capacity; stage split not stored"

# Year used to display existing (already-operating) rows that lack a sourced
# startup year: before the chart start, so they count from the first year.
EXISTING_CAPACITY_DISPLAY_YEAR = 2019


def _status_mask(df: pd.DataFrame, status: str) -> pd.Series:
    return df["status"].astype(str).str.strip().eq(status)


def _included_mask(df: pd.DataFrame) -> pd.Series:
    if "include_in_project_totals" not in df.columns:
        return pd.Series(True, index=df.index)
    return (
        df["include_in_project_totals"]
        .fillna(True)
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes"])
    )


def _scope_of(df: pd.DataFrame) -> pd.Series:
    if "capacity_scope" not in df.columns:
        return pd.Series("", index=df.index)
    return df["capacity_scope"].fillna("").astype(str).str.strip()


def operating_layers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split Operating rows into two layers.

    Returns (evidenced, campus_envelope):
    - evidenced: Operating rows whose stored MW is directly evidenced as
      operating-stage (row-level or campus-current-operating scope).
    - campus_envelope: Operating rows whose stored MW is a campus envelope
      with no stored stage split (or an unclassified campus-level scope).

    Callers pre-filter for inclusion in project totals as they wish; this
    helper only separates the two operating layers.
    """
    if df.empty or "status" not in df.columns:
        empty = df.iloc[0:0] if not df.empty else df
        return empty, empty
    op = df[_status_mask(df, "Operating")].copy()
    if op.empty:
        return op, op
    scope = _scope_of(op)
    evidenced = op[scope.isin(OPERATING_STAGE_EVIDENCED_SCOPES)].copy()
    campus = op[~scope.isin(OPERATING_STAGE_EVIDENCED_SCOPES)].copy()
    return evidenced, campus


def operating_stage_summary(df: pd.DataFrame) -> dict:
    """Summarise the operating-stage split for KPI display.

    Returns dict:
      evidenced_mw / evidenced_rows   — directly evidenced operating-stage
      campus_envelope_mw / campus_envelope_rows — operating campus envelopes
        with no stored stage split
      campus_envelope_projects        — sorted project names in that layer
      total_operating_mw              — sum of the two layers
    """
    evidenced, campus = operating_layers(df)

    def _mw(layer: pd.DataFrame) -> float:
        if "facility_mw" not in layer.columns:
            return 0.0
        return float(pd.to_numeric(layer["facility_mw"], errors="coerce").fillna(0).sum())

    evidenced_mw = _mw(evidenced)
    campus_mw = _mw(campus)
    return {
        "evidenced_mw": evidenced_mw,
        "evidenced_rows": int(len(evidenced)),
        "campus_envelope_mw": campus_mw,
        "campus_envelope_rows": int(len(campus)),
        "campus_envelope_projects": sorted(
            campus["project_name"].astype(str).tolist()
        ) if "project_name" in campus.columns else [],
        "total_operating_mw": evidenced_mw + campus_mw,
    }


def forecast_partition(
    df: pd.DataFrame,
    existing_capacity_year: int = EXISTING_CAPACITY_DISPLAY_YEAR,
) -> dict:
    """Partition included projects for the delivery timeline.

    - Dated rows: every row with a sourced startup_year, plus Operating rows
      without one (existing capacity shown from chart start — not a forecast).
    - Undated bucket: non-operating rows with no sourced startup/delivery
      year. Their startup_year stays NaN; callers must never pin them to a
      fixed year.

    Returns {"dated": DataFrame, "undated": DataFrame, "undated_mw": float,
             "undated_rows": int}.
    """
    if df.empty or "startup_year" not in df.columns:
        dated = df.copy()
        undated = df.iloc[0:0].copy() if not df.empty else df.copy()
        return {"dated": dated, "undated": undated, "undated_mw": 0.0, "undated_rows": 0}

    work = df.copy()
    year = pd.to_numeric(work["startup_year"], errors="coerce")
    is_operating = _status_mask(work, "Operating")
    has_year = year.notna()

    # Operating rows without a sourced startup year are already built —
    # display them from chart start as existing capacity (previous convention,
    # retained so the installed base is not hidden by an invented future year).
    existing = (~has_year) & is_operating
    if existing.any():
        year = year.copy()
        year[existing] = float(existing_capacity_year)
        work = work.copy()
        work["startup_year"] = year

    has_year = work["startup_year"].notna()
    dated = work[has_year].copy()
    dated["startup_year"] = dated["startup_year"].astype(int)
    undated = work[~has_year].copy()

    undated_mw = 0.0
    if not undated.empty and "facility_mw" in undated.columns:
        undated_mw = float(
            pd.to_numeric(undated["facility_mw"], errors="coerce").fillna(0).sum()
        )
    return {
        "dated": dated,
        "undated": undated,
        "undated_mw": undated_mw,
        "undated_rows": int(len(undated)),
    }


def risk_tier_group(status: str, risk_weight: float | None) -> str:
    """Map a row's status/risk weight to the display tier used by the
    delivery timeline (Operating/UC/Approved split/Proposed)."""
    s = str(status).strip()
    w = float(risk_weight or 0)
    if s == "Operating":
        return "Operating"
    if s == "Under Construction":
        return "Under Construction"
    if s == "Approved" and w >= 0.74:
        return "Approved — Power Secured"
    if s == "Approved":
        return "Approved — Grid Pending"
    return "Proposed"
