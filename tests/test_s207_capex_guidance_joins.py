"""S2-07 (C9) verification: capex period/basis/type joins are comparable-only.

Review reproductions (astra-review-2026-09-04 S2-07):
- Microsoft's ~$190B entry is a CY2026 (calendar-year) disclosure, keyed next
  to a FY2026/June-end analyst run-rate estimate of ~$120B — the old keys
  implied a 58.3% same-period revision and compared a calendar-year amount
  with July–June actuals. After the fix no same-period revision can join the
  two records;
- CY2026 selects January–December actuals (period_bounds), never the
  July–June fiscal window;
- revisions/bridges/deltas are computed only between comparable observations
  (same company + period + record_type + measurement_basis): a change only in
  period, type or lease/PP&E basis never registers as a cut/raise;
- genuine revisions for other issuers (Oracle raises, CoreWeave cut) are
  preserved under the comparable-only grouping;
- measurement basis and management_guidance/analyst_estimate/actual type are
  stored on the records and per-issuer caveats are generated from that
  metadata rather than hard-coded prose.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.lib import capex_guidance_meta as cgm  # noqa: E402
from app.lib.dc_risk_signals import capex_commitment_signal  # noqa: E402

REF = REPO / "data" / "reference"


def _history_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "capex_guidance_history.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _hist_row(
    company: str,
    fiscal_year: str,
    value: float,
    announced: str,
    record_type: str = "management_guidance",
    basis: str = "unspecified",
    notes: str = "",
) -> dict:
    return {
        "ticker": {"Microsoft": "MSFT", "Meta": "META", "Oracle": "ORCL",
                   "CoreWeave": "CRWV", "Alphabet": "GOOGL",
                   "Amazon": "AMZN", "Apple": "AAPL"}.get(company, "XXX"),
        "company": company,
        "fiscal_year": fiscal_year,
        "fy_end_month": 12 if fiscal_year.startswith("CY") else 6,
        "guidance_usd_b": value,
        "announced_date": announced,
        "source": "fixture",
        "notes": notes,
        "record_type": record_type,
        "measurement_basis": basis,
    }


# --- Period semantics -------------------------------------------------------

def test_cy2026_is_calendar_year_jan_dec() -> None:
    assert cgm.parse_period("CY2026", 12) == (date(2026, 1, 1), date(2026, 12, 31))


def test_fy2026_june_end_is_jul2025_jun2026() -> None:
    assert cgm.parse_period("FY2026", 6) == (date(2025, 7, 1), date(2026, 6, 30))


def test_cy_label_requires_december_end_month() -> None:
    # the pre-fix key shape (CY disclosure stored as FY2026 / month 6) is the
    # exact semantic the schema now rejects
    with pytest.raises(ValueError):
        cgm.parse_period("CY2026", 6)
    with pytest.raises(ValueError):
        cgm.parse_period("FY2026", 12)
    with pytest.raises(ValueError):
        cgm.parse_period("F2026", 12)
    with pytest.raises(ValueError):
        cgm.parse_period("CY2026", 0)
    # month 12 given as a string still parses (int coercion)
    assert cgm.parse_period("CY2026", "12") == (date(2026, 1, 1), date(2026, 12, 31))


def test_cy2026_and_fy2026_are_distinct_periods() -> None:
    assert cgm.period_start("CY2026", 12) != cgm.period_start("FY2026", 6)
    assert cgm.period_end("CY2026", 12) != cgm.period_end("FY2026", 6)


# --- Real data-file invariants ----------------------------------------------

def _read_ref(name: str) -> pd.DataFrame:
    date_col = "guidance_date" if name == "capex_guidance.csv" else "announced_date"
    return pd.read_csv(REF / name, parse_dates=[date_col])


def test_data_files_carry_type_and_basis_metadata() -> None:
    for name in ("capex_guidance.csv", "capex_guidance_history.csv"):
        df = _read_ref(name)
        assert {"record_type", "measurement_basis"} <= set(df.columns), name
        assert df["record_type"].isin(cgm.RECORD_TYPES).all(), name
        assert df["measurement_basis"].isin(cgm.MEASUREMENT_BASES).all(), name


def test_data_files_period_keys_validate() -> None:
    for name in ("capex_guidance.csv", "capex_guidance_history.csv"):
        df = _read_ref(name)
        for _, r in df.iterrows():
            start, end = cgm.parse_period(r["fiscal_year"], r["fy_end_month"])
            assert start < end
        cy = df[df["fiscal_year"].str.startswith("CY")]
        assert (cy["fy_end_month"] == 12).all()
        fy = df[df["fiscal_year"].str.startswith("FY")]
        assert (fy["fy_end_month"] != 12).all()


def test_msft_190_is_cy2026_not_fy2026() -> None:
    hist = _read_ref("capex_guidance_history.csv")
    msft_190 = hist[
        (hist["company"] == "Microsoft") & (hist["guidance_usd_b"] == 190.0)
    ]
    assert len(msft_190) == 1
    row = msft_190.iloc[0]
    assert row["fiscal_year"] == "CY2026"
    assert row["fy_end_month"] == 12
    assert row["record_type"] == cgm.MANAGEMENT_GUIDANCE

    guide = _read_ref("capex_guidance.csv")
    g190 = guide[
        (guide["company"] == "Microsoft") & (guide["guidance_usd_b"] == 190.0)
    ]
    assert len(g190) == 1
    assert g190.iloc[0]["fiscal_year"] == "CY2026"
    assert g190.iloc[0]["fy_end_month"] == 12
    # the FY-analyst run-rate is a different period — not stored as a
    # same-period "prior guidance" on the CY2026 record
    assert pd.isna(g190.iloc[0]["prior_guidance_usd_b"]) or g190.iloc[0]["prior_guidance_usd_b"] == ""


def test_msft_analyst_estimate_stays_fy2026() -> None:
    hist = _read_ref("capex_guidance_history.csv")
    msft_120 = hist[
        (hist["company"] == "Microsoft") & (hist["guidance_usd_b"] == 120.0)
    ]
    assert len(msft_120) == 1
    row = msft_120.iloc[0]
    assert row["fiscal_year"] == "FY2026"
    assert row["fy_end_month"] == 6
    assert row["record_type"] == cgm.ANALYST_ESTIMATE


def test_real_history_has_no_same_period_revision_joining_120_and_190() -> None:
    hist = _read_ref("capex_guidance_history.csv")
    hist["notes"] = hist["notes"].fillna("")
    meta = cgm.with_metadata(hist)
    rev = cgm.comparable_revisions(meta)

    msft = rev[rev["company"] == "Microsoft"].copy()
    r190 = msft[(msft["guidance_usd_b"] == 190.0)]
    r120 = msft[(msft["guidance_usd_b"] == 120.0)]
    assert len(r190) == 1 and len(r120) == 1
    # neither record has a comparable prior — the 58.3% "revision" is gone
    assert pd.isna(r190.iloc[0]["prev_guidance"])
    assert pd.isna(r120.iloc[0]["prev_guidance"])
    assert pd.isna(r190.iloc[0]["revision_pct"])
    assert pd.isna(r120.iloc[0]["revision_pct"])


def test_genuine_issuer_chains_preserved_on_real_data() -> None:
    """Comparable-only grouping must not change single-type chains."""
    hist = _read_ref("capex_guidance_history.csv")
    hist["notes"] = hist["notes"].fillna("")
    meta = cgm.with_metadata(hist)
    rev = cgm.comparable_revisions(meta)

    orcl = rev[(rev["company"] == "Oracle") & (rev["fiscal_year"] == "FY2026")]
    vals = orcl.sort_values("announced_date")["guidance_usd_b"].tolist()
    assert vals == [25.0, 35.0, 50.0]
    pcts = orcl.sort_values("announced_date")["revision_pct"].dropna().tolist()
    assert pcts[0] == pytest.approx(40.0)          # 25 -> 35
    assert pcts[1] == pytest.approx(50.0 * 100 / 35.0 - 100)  # 35 -> 50

    crwv = rev[(rev["company"] == "CoreWeave") & (rev["fiscal_year"] == "CY2025")]
    cut = crwv[crwv["guidance_usd_b"] == 13.0]
    assert len(cut) == 1
    assert cut.iloc[0]["prev_guidance"] == pytest.approx(21.5)
    assert cut.iloc[0]["revision_pct"] == pytest.approx(13.0 / 21.5 * 100 - 100)


def test_pre_fix_naive_grouping_would_have_joined_190_to_120() -> None:
    """The +58.3% join is real under the old (company, fiscal_year)-only
    grouping — proving the fixture below is not vacuous."""
    hist = _read_ref("capex_guidance_history.csv")
    hist["notes"] = hist["notes"].fillna("")
    # simulate the pre-fix key shape: 190 stored as FY2026 next to the 120
    pre = hist.copy()
    pre.loc[pre["guidance_usd_b"] == 190.0, ["fiscal_year", "fy_end_month"]] = ["FY2026", 6]
    pre = pre.sort_values(["company", "fiscal_year", "announced_date"])
    pre["naive_prev"] = pre.groupby(["company", "fiscal_year"])["guidance_usd_b"].shift(1)
    pre["naive_pct"] = (pre["guidance_usd_b"] / pre["naive_prev"] - 1) * 100
    join = pre[(pre["company"] == "Microsoft") & (pre["guidance_usd_b"] == 190.0)]
    assert join.iloc[0]["naive_pct"] == pytest.approx(190.0 / 120.0 * 100 - 100)  # +58.3%


# --- Comparability of revisions (fixture level) -----------------------------

def _revision_rows_pre_fix_join_fixture() -> pd.DataFrame:
    """Same period + same basis, but a type change: analyst estimate then a
    lower management-guidance figure. Under (company, fiscal_year)-only
    grouping this reads as a -26% cut; under comparable-only grouping it is
    two unrelated records."""
    return pd.DataFrame([
        _hist_row("Microsoft", "FY2026", 190.0, "2026-01-29",
                  record_type="analyst_estimate", notes="analyst consensus"),
        _hist_row("Microsoft", "FY2026", 140.0, "2026-04-30",
                  record_type="management_guidance", notes="company statement"),
    ])


def test_type_change_alone_is_not_a_revision() -> None:
    df = _revision_rows_pre_fix_join_fixture()
    meta = cgm.with_metadata(df)
    rev = cgm.comparable_revisions(meta)
    assert rev["prev_guidance"].isna().all()
    assert rev["revision_pct"].isna().all()

    # control: the same values within ONE comparable chain still register
    same_chain = pd.DataFrame([
        _hist_row("Microsoft", "FY2026", 190.0, "2026-01-29"),
        _hist_row("Microsoft", "FY2026", 140.0, "2026-04-30"),
    ])
    rev2 = cgm.comparable_revisions(cgm.with_metadata(same_chain))
    cut = rev2[rev2["guidance_usd_b"] == 140.0]
    assert cut.iloc[0]["revision_pct"] == pytest.approx(140.0 / 190.0 * 100 - 100)


def test_basis_change_alone_is_not_a_revision() -> None:
    df = pd.DataFrame([
        _hist_row("Microsoft", "FY2026", 190.0, "2026-01-29",
                  basis="lease_inclusive", notes="incl. finance leases"),
        _hist_row("Microsoft", "FY2026", 140.0, "2026-04-30",
                  basis="pp_e", notes="PP&E capex"),
    ])
    rev = cgm.comparable_revisions(cgm.with_metadata(df))
    assert rev["prev_guidance"].isna().all()


def test_actual_is_never_a_guidance_revision() -> None:
    df = pd.DataFrame([
        _hist_row("Microsoft", "FY2025", 80.0, "2025-01-29"),
        _hist_row("Microsoft", "FY2025", 63.0, "2025-07-22",
                  record_type="actual", basis="pp_e",
                  notes="Actual full-year PP&E capex"),
    ])
    rev = cgm.comparable_revisions(cgm.with_metadata(df))
    actual = rev[rev["record_type"] == cgm.ACTUAL]
    assert pd.isna(actual.iloc[0]["prev_guidance"])
    assert pd.isna(actual.iloc[0]["revision_pct"])


# --- dc_risk_signals end-to-end (no false cut/raise) ------------------------

def test_dc_risk_signal_ignores_type_and_basis_only_changes(tmp_path: Path) -> None:
    # post-fix shape on disk: MSFT FY-analyst 120 (FY2026) + CY2026 mgmt 190 —
    # two different periods, two singletons, no revision; plus a same-period
    # type split and a same-period basis split that a naive reader would cut.
    rows = [
        _hist_row("Microsoft", "FY2026", 120.0, "2026-01-29",
                  record_type="analyst_estimate", notes="analyst consensus"),
        _hist_row("Microsoft", "CY2026", 190.0, "2026-04-30",
                  notes="company statement, calendar 2026"),
        _hist_row("Meta", "CY2026", 190.0, "2026-01-29",
                  record_type="analyst_estimate", notes="analyst consensus"),
        _hist_row("Meta", "CY2026", 140.0, "2026-04-30",
                  notes="company statement"),
        _hist_row("Oracle", "FY2026", 190.0, "2026-01-29",
                  basis="lease_inclusive", notes="incl. finance leases"),
        _hist_row("Oracle", "FY2026", 140.0, "2026-04-30",
                  basis="pp_e", notes="PP&E capex"),
    ]
    path = _history_csv(tmp_path, rows)
    signal = capex_commitment_signal(tmp_path)
    # Nothing comparable was cut or pushed out -> no watch/warning verdict
    assert signal.status not in ("amber", "red"), signal.detail
    assert path.exists()


def test_dc_risk_signal_still_flags_a_genuine_cut(tmp_path: Path) -> None:
    rows = [
        _hist_row("CoreWeave", "CY2025", 21.5, "2025-05-14",
                  notes="Initial CY2025 guidance"),
        _hist_row("CoreWeave", "CY2025", 13.0, "2025-11-10",
                  notes="Revised down — ~40% cut due to third-party DC "
                        "developer delay; slip pushed capex to 2026"),
        _hist_row("CoreWeave", "CY2025", 14.9, "2026-02-26",
                  record_type="actual", notes="Actual full-year result"),
    ]
    _history_csv(tmp_path, rows)
    signal = capex_commitment_signal(tmp_path)
    assert signal.status in ("amber", "red"), signal.detail


# --- Legacy fallback + forward-row selection --------------------------------

def test_with_metadata_legacy_notes_fallback() -> None:
    df = pd.DataFrame([
        {"company": "Microsoft", "fiscal_year": "FY2025",
         "notes": "Actual full-year PP&E capex (total infra incl. finance "
                  "leases ~$97.7B per 10-K)"},
        {"company": "Apple", "fiscal_year": "FY2026",
         "notes": "Analyst consensus ~$14.3B (FactSet)"},
        {"company": "Amazon", "fiscal_year": "CY2026",
         "notes": "Reaffirmed ~$200B"},
    ])
    meta = cgm.with_metadata(df)
    assert list(meta["record_type"]) == [cgm.ACTUAL, cgm.ANALYST_ESTIMATE, cgm.MANAGEMENT_GUIDANCE]
    assert list(meta["measurement_basis"]) == [cgm.PP_E, cgm.UNSPECIFIED, cgm.UNSPECIFIED]


def test_select_forward_row_picks_open_latest_period_not_label_max() -> None:
    rows = [
        {"ticker": "MSFT", "company": "Microsoft", "fiscal_year": "FY2025",
         "fy_end_month": 6, "guidance_usd_b": 63.0, "guidance_date": "2025-07-22",
         "notes": "Actual full-year PP&E capex", "record_type": "actual"},
        {"ticker": "MSFT", "company": "Microsoft", "fiscal_year": "CY2026",
         "fy_end_month": 12, "guidance_usd_b": 190.0, "guidance_date": "2026-04-30",
         "notes": "CY2026 company statement", "record_type": "management_guidance"},
    ]
    # label string-max would pick FY2025 (CY sorts before FY) — the forward
    # row must be the CY2026 disclosure (period ends 2026-12-31)
    fwd = cgm.select_forward_row(rows)
    assert fwd["fiscal_year"] == "CY2026"
    assert fwd["guidance_usd_b"] == 190.0

    # an actual-only list falls back to the latest period
    assert cgm.select_forward_row(rows[:1])["fiscal_year"] == "FY2025"
    assert cgm.select_forward_row([]) is None


def test_select_forward_row_uses_csv_record_type_column() -> None:
    rows = [
        {"ticker": "MSFT", "fiscal_year": "FY2025", "fy_end_month": 6,
         "guidance_usd_b": 63.0, "guidance_date": "2025-07-22",
         "notes": "Actual full-year PP&E capex", "record_type": "actual"},
        {"ticker": "MSFT", "fiscal_year": "FY2026", "fy_end_month": 6,
         "guidance_usd_b": 120.0, "guidance_date": "2026-01-29",
         "notes": "Analyst consensus", "record_type": "analyst_estimate"},
    ]
    fwd = cgm.select_forward_row(rows)
    assert fwd["fiscal_year"] == "FY2026"  # analyst estimate is still a forward row


# --- Caveats generated from metadata ----------------------------------------

def test_caveats_generated_from_real_metadata() -> None:
    hist = _read_ref("capex_guidance_history.csv")
    hist["notes"] = hist["notes"].fillna("")
    caveats = cgm.guidance_caveats(hist)
    msft = next(c for c in caveats if c.startswith("**Microsoft:**"))
    assert "calendar-year (CY) disclosures are tracked separately" in msft
    assert "analyst_estimate" in msft
    assert "pp_e" in msft
    aapl = next(c for c in caveats if c.startswith("**Apple:**"))
    assert "analyst estimates" in aapl
    # no issuer-specific hard-coded amounts in the caveat text (data-driven)
    assert "$120B" not in msft
