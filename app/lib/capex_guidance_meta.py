"""Period / basis / type metadata for hyperscaler capex guidance records.

S2-07: revisions, bridges and deltas may only join *comparable* observations.
Two observations are comparable only when they share the issuer, the period
(fiscal_year label + fy_end_month) AND the measurement basis AND the record
type. In particular:

- a CY (calendar-year) disclosure is a different period from an FY
  (fiscal-year) estimate even when the label years match — Microsoft's
  ~$190B CY2026 statement (Jan-Dec 2026) is not a revision of the ~$120B
  FY2026 analyst run-rate estimate (Jul 2025 - Jun 2026);
- a PP&E-only (cash) figure is never a revision of a lease-inclusive
  figure (Microsoft FY2025 actual $63B PP&E vs lease-inclusive ~$97.7B);
- an analyst estimate is not a management-guidance revision and a reported
  actual is not a guidance revision.

Values are stored on the CSV rows themselves; the *fallback* resolvers below
only apply to legacy rows / fixtures that predate the metadata columns, and
derive strictly from each row's own notes text.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any

import pandas as pd

# --- Canonical vocabularies -------------------------------------------------

RECORD_TYPES = ("management_guidance", "analyst_estimate", "actual")
MANAGEMENT_GUIDANCE = "management_guidance"
ANALYST_ESTIMATE = "analyst_estimate"
ACTUAL = "actual"

MEASUREMENT_BASES = ("pp_e", "lease_inclusive", "unspecified")
PP_E = "pp_e"
LEASE_INCLUSIVE = "lease_inclusive"
UNSPECIFIED = "unspecified"

# A revision/delta may only be computed within one of these groups.
COMPARABILITY_KEYS = ["company", "fiscal_year", "record_type", "measurement_basis"]

# The actuals served from the financials DB (cash-flow "Capital Expenditure")
# are PP&E additions — the fixed basis a bridge compares guidance against.
ACTUALS_BASIS = PP_E

_PERIOD_RE = re.compile(r"^(FY|CY)(\d{4})$")
_FALLBACK_ACTUAL_RE = re.compile(r"actual full[- ]year", re.I)
_FALLBACK_ANALYST_RE = re.compile(r"analyst (consensus|estimate)|factset", re.I)
_FALLBACK_PPE_RE = re.compile(
    r"pp&e capex|pp&e additions|pp&e purchases|actual full[- ]year pp&e|"
    r"capex \(pp&e\)|pp&e-only",
    re.I,
)
_FALLBACK_LEASE_RE = re.compile(r"financ(e|ing) lease|lease-inclusive", re.I)
_DIRECTIONAL_RE = re.compile(r"directional guidance only|no explicit annual figure", re.I)


def is_record_type(value: Any) -> bool:
    return isinstance(value, str) and value in RECORD_TYPES


def is_measurement_basis(value: Any) -> bool:
    return isinstance(value, str) and value in MEASUREMENT_BASES


def resolve_record_type(raw: Any, notes: Any = "") -> str:
    """Column value wins; otherwise classify from the row's own notes text."""
    if is_record_type(raw):
        return raw
    text = str(notes if notes is not None else "")
    if _FALLBACK_ACTUAL_RE.search(text):
        return ACTUAL
    if _FALLBACK_ANALYST_RE.search(text):
        return ANALYST_ESTIMATE
    return MANAGEMENT_GUIDANCE


def resolve_measurement_basis(raw: Any, notes: Any = "") -> str:
    """Column value wins; otherwise read the basis off the notes text.

    PP&E phrases take precedence over lease phrases so a row whose recorded
    figure is explicitly PP&E ("Actual full-year PP&E capex (total infra incl.
    finance leases ...)") stays pp_e — the lease figure is context, not the
    recorded value.
    """
    if is_measurement_basis(raw):
        return raw
    text = str(notes if notes is not None else "")
    if _FALLBACK_PPE_RE.search(text):
        return PP_E
    if _FALLBACK_LEASE_RE.search(text):
        return LEASE_INCLUSIVE
    return UNSPECIFIED


def with_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with resolved ``record_type`` and
    ``measurement_basis`` columns (column-first, notes fallback)."""
    out = df.copy()
    out["record_type"] = [
        resolve_record_type(r.get("record_type"), r.get("notes"))
        for _, r in out.iterrows()
    ]
    out["measurement_basis"] = [
        resolve_measurement_basis(r.get("measurement_basis"), r.get("notes"))
        for _, r in out.iterrows()
    ]
    return out


# --- Period handling --------------------------------------------------------

def parse_period(fiscal_year: Any, fy_end_month: Any) -> tuple[date, date]:
    """Return inclusive (period_start, period_end) for a record's period key.

    ``FY<YYYY>`` = the issuer's fiscal year *ending* in YYYY (fy_end_month
    names the month); ``CY<YYYY>`` = the calendar year YYYY, which requires
    fy_end_month == 12. Anything else is rejected rather than silently
    mis-bridged.
    """
    label = str(fiscal_year).strip()
    m = _PERIOD_RE.match(label)
    if not m:
        raise ValueError(
            f"fiscal_year {fiscal_year!r} is not FY<YYYY> or CY<YYYY>"
        )
    prefix, year_str = m.group(1), m.group(2)
    year = int(year_str)
    try:
        end_month = int(fy_end_month)
    except (TypeError, ValueError):
        raise ValueError(
            f"fy_end_month {fy_end_month!r} is not an integer"
        ) from None
    if not 1 <= end_month <= 12:
        raise ValueError(f"fy_end_month {end_month} out of range 1..12")
    if prefix == "CY" and end_month != 12:
        raise ValueError(
            f"CY{year} is a calendar year — fy_end_month must be 12, got {end_month}"
        )
    if prefix == "FY" and end_month == 12:
        raise ValueError(
            f"FY{year} with fy_end_month 12 is a calendar year — use CY{year}"
        )
    if end_month == 12:
        start = date(year, 1, 1)
    else:
        start = date(year - 1, end_month + 1, 1)
    end = date(year, end_month, calendar.monthrange(year, end_month)[1])
    return start, end


def period_end(fiscal_year: Any, fy_end_month: Any) -> date:
    return parse_period(fiscal_year, fy_end_month)[1]


def period_start(fiscal_year: Any, fy_end_month: Any) -> date:
    return parse_period(fiscal_year, fy_end_month)[0]


# --- Comparable revisions ---------------------------------------------------

def comparable_revisions(
    df: pd.DataFrame,
    date_col: str = "announced_date",
    value_col: str = "guidance_usd_b",
) -> pd.DataFrame:
    """Add ``prev_guidance`` / ``revision_pct`` computed *only within*
    comparable chains (issuer + period + record_type + measurement_basis),
    ordered by *date_col*. Callers must pass a frame already carrying the
    metadata columns (see :func:`with_metadata`)."""
    d = df.copy()
    for col in COMPARABILITY_KEYS:
        if col not in d.columns:
            raise KeyError(f"{col!r} missing — run with_metadata() first")
    d = d.sort_values(COMPARABILITY_KEYS + [date_col]).reset_index(drop=True)
    d["prev_guidance"] = d.groupby(COMPARABILITY_KEYS, sort=False)[value_col].shift(1)
    d["revision_pct"] = (d[value_col] / d["prev_guidance"] - 1) * 100
    return d


# --- Forward-row selection (ETL / bridge) -----------------------------------

def select_forward_row(rows: list[dict]) -> dict | None:
    """Pick the open forward-looking guidance row from csv dict-rows.

    Actual rows are never forward guidance; among the remainder the row whose
    period ends latest wins (ties -> most recent guidance_date). Falls back to
    the whole list (actuals included) only when nothing else exists, so a
    closed-period-only ticker still reports sensibly. Returns a copy of the
    csv row or None for an empty list.
    """
    if not rows:
        return None

    def _end(r):
        try:
            return period_end(r.get("fiscal_year", ""), r.get("fy_end_month", ""))
        except ValueError:
            return date.min

    def _guidance_date(r):
        return r.get("guidance_date") or r.get("announced_date") or "1970-01-01"

    with_type = [
        dict(r, **{
            "record_type": resolve_record_type(r.get("record_type"), r.get("notes")),
        })
        for r in rows
    ]
    candidates = [r for r in with_type if r["record_type"] != ACTUAL]
    pool = candidates or with_type
    return max(pool, key=lambda r: (_end(r), _guidance_date(r)))


# --- Data-driven caveats ----------------------------------------------------

def guidance_caveats(df: pd.DataFrame) -> list[str]:
    """Build per-company caveat sentences from the record metadata itself.

    Nothing here is hard-coded per issuer: analyst-estimate rows, directional
    language, CY/FY period mixing on a non-December year-end, and declared
    measurement bases are all read off the frame.
    """
    out: list[str] = []
    meta = with_metadata(df)
    for company in sorted(meta["company"].dropna().unique()):
        sub = meta[meta["company"] == company]
        bits: list[str] = []

        non_actual = sub[sub["record_type"] != ACTUAL]
        if not non_actual.empty and (
            non_actual["notes"].fillna("").str.contains(_DIRECTIONAL_RE).any()
        ):
            bits.append("gives directional guidance only (no explicit annual figure)")

        analyst = non_actual[non_actual["record_type"] == ANALYST_ESTIMATE]
        if not analyst.empty:
            bits.append(
                "some figures are analyst estimates (FactSet/consensus) — "
                "labelled analyst_estimate, never joined to guidance as a revision"
            )

        try:
            end_months = sorted({int(m) for m in sub["fy_end_month"].dropna()})
        except (TypeError, ValueError):
            end_months = []
        labels = sorted({str(fy) for fy in sub["fiscal_year"].dropna()})
        has_cy = any(fy.startswith("CY") for fy in labels)
        has_fy = any(fy.startswith("FY") for fy in labels)
        non_dec = any(m != 12 for m in end_months)
        if non_dec and has_cy and has_fy:
            months = ", ".join(str(m) for m in sorted(end_months))
            bits.append(
                "calendar-year (CY) disclosures are tracked separately from "
                f"fiscal-year (FY) periods (fy_end_month {months}) — a CY year "
                "never joins an FY year as a same-period revision"
            )

        declared = sub[sub["measurement_basis"] != UNSPECIFIED]
        if not declared.empty:
            bases = sorted(declared["measurement_basis"].dropna().unique())
            bits.append(
                "declared measurement basis(es): "
                + ", ".join(bases)
                + " — differing bases are never joined"
            )

        if bits:
            out.append(f"**{company}:** " + "; ".join(bits) + ".")
    return out
