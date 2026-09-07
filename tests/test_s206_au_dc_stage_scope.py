"""S2-06 (C8) verification: campus envelope / operating-stage separation,
stage-level risk weighting, and the Undated pipeline bucket.

Review reproductions:
- Eastern Creek's campus envelope cannot silently become entirely
  operating-stage MW: Operating rows whose MW is a campus envelope with no
  stored stage split are separated from directly evidenced operating-stage MW
  and stay visible as their own layer (755 MW across Eastern Creek /
  SYD1 / SYD2 / MEL1 on live data);
- a fixture with a 110 MW campus envelope and a 15 MW construction stage
  cannot show 110 MW as that stage's 100%-weighted capacity — the risk weight
  applies to the evidenced stage MW (15), the envelope (110) remains in
  facility_mw and is not double-counted;
- undated pipeline rows are bucketed as "Undated" (never pinned to 2028), so
  no delivery-year cliff is invented; dated rows still accumulate by sourced
  startup year and recorded totals reconcile without invented splits;
- risk weights remain the disclosed conventions (unchanged table), applied to
  the MW the status directly covers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lib.au_dc_stage_scope import (  # noqa: E402
    EXISTING_CAPACITY_DISPLAY_YEAR,
    OPERATING_STAGE_EVIDENCED_SCOPES,
    forecast_partition,
    operating_layers,
    operating_stage_summary,
    risk_tier_group,
)
from models.au_dc.risk_model import RISK_WEIGHTS, apply_risk_weight  # noqa: E402


def _project(
    name: str,
    status: str,
    facility_mw: float | None,
    scope: str,
    startup_year: float | None = None,
    risk_weight: float = 1.0,
    evidenced_stage_mw: float | None = None,
    include: bool = True,
) -> dict:
    row = {
        "project_name": name,
        "operator": "Fixture Co",
        "status": status,
        "facility_mw": facility_mw,
        "capacity_scope": scope,
        "startup_year": startup_year,
        "risk_weight": risk_weight,
        "include_in_project_totals": include,
    }
    if evidenced_stage_mw is not None:
        row["evidenced_stage_mw"] = evidenced_stage_mw
    return row


# --- Operating-stage vs campus envelope -----------------------------------

def test_operating_stage_split_separates_evidenced_from_campus_envelope():
    df = pd.DataFrame([
        _project("S3", "Operating", 80.0, "Row-level sourced capacity", 2020),
        _project("Vantage MEL1", "Operating", 64.0, "Row-level sourced capacity"),
        _project("Fyshwick", "Operating", 45.0, "Campus current operating capacity", 2010),
        _project("Eastern Creek", "Operating", 200.0, "Campus capacity; stage split not stored", 2018),
        _project("SYD1", "Operating", 121.0, "Campus capacity; stage split not stored", 2018),
        _project("MEL1", "Operating", 276.0, "Campus capacity; stage split not stored", 2020),
        _project("S4", "Proposed", 350.0, "Row-level sourced capacity", 2028, risk_weight=0.0),
    ])

    evidenced, campus = operating_layers(df)
    assert set(evidenced["project_name"]) == {"S3", "Vantage MEL1", "Fyshwick"}
    assert set(campus["project_name"]) == {"Eastern Creek", "SYD1", "MEL1"}

    summary = operating_stage_summary(df)
    # 80 + 64 + 45 = 189 evidenced; 200 + 121 + 276 = 597 campus envelope
    assert summary["evidenced_mw"] == pytest.approx(189.0)
    assert summary["evidenced_rows"] == 3
    assert summary["campus_envelope_mw"] == pytest.approx(597.0)
    assert summary["campus_envelope_rows"] == 3
    assert summary["campus_envelope_projects"] == ["Eastern Creek", "MEL1", "SYD1"]
    # Recorded total reconciles: the envelope is not inside the evidenced total
    assert summary["total_operating_mw"] == pytest.approx(189.0 + 597.0)


def test_four_campus_rows_stay_visible_and_755_mw_is_not_operating_stage():
    """Live-data reproduction: the four ambiguous operating rows (755 MW) can
    never silently become entirely operating-stage MW."""
    df = pd.DataFrame([
        _project("Eastern Creek", "Operating", 200.0, "Campus capacity; stage split not stored", 2018),
        _project("SYD1", "Operating", 121.0, "Campus capacity; stage split not stored", 2018),
        _project("SYD2", "Operating", 158.0, "Campus capacity; stage split not stored", 2021),
        _project("MEL1", "Operating", 276.0, "Campus capacity; stage split not stored", 2020),
        _project("S3", "Operating", 80.0, "Row-level sourced capacity", 2020),
    ])

    evidenced, campus = operating_layers(df)
    # All four ambiguous rows stay visible separately in the campus layer
    assert sorted(campus["project_name"]) == ["Eastern Creek", "MEL1", "SYD1", "SYD2"]
    assert campus["facility_mw"].sum() == pytest.approx(755.0)
    # None of the 755 MW leaks into the directly evidenced operating-stage layer
    assert evidenced["facility_mw"].sum() == pytest.approx(80.0)

    summary = operating_stage_summary(df)
    assert summary["campus_envelope_mw"] == pytest.approx(755.0)
    assert summary["campus_envelope_rows"] == 4
    assert summary["evidenced_mw"] == pytest.approx(80.0)
    assert summary["total_operating_mw"] == pytest.approx(835.0)  # no double count


# --- Risk model: stage-level base ------------------------------------------

def test_risk_weight_applies_to_evidenced_stage_not_campus_envelope():
    """GreenSquare reproduction: 110 MW campus envelope vs 15 MW Stage 1 under
    construction must risk-weight 15 MW, not the whole envelope."""
    df = pd.DataFrame([
        _project("GreenSquareDC SYD1", "Under Construction", 110.0,
                 "Campus full-build envelope", 2026, evidenced_stage_mw=15.0),
        _project("Doma Minchinbury", "Under Construction", 62.0,
                 "Row-level sourced capacity", 2028),
        _project("Eastern Creek", "Operating", 200.0,
                 "Campus capacity; stage split not stored", 2018),
        _project("Marsden Park", "Approved", 504.0,
                 "Campus power-consumption envelope", None, risk_weight=0.25),
        _project("S7", "Proposed", 550.0, "Campus full-build envelope", None, risk_weight=0.0),
    ])
    df["power_secured"] = [False, True, True, False, False]

    out = apply_risk_weight(df)
    gs = out[out["project_name"] == "GreenSquareDC SYD1"].iloc[0]

    # The construction stage's 100% weight applies to the evidenced 15 MW stage
    assert gs["risk_weight"] == pytest.approx(1.0)
    assert gs["risk_base_mw"] == pytest.approx(15.0)
    assert gs["risked_mw"] == pytest.approx(15.0)
    # The 110 MW campus envelope remains in facility_mw (recorded/announced)
    assert gs["facility_mw"] == pytest.approx(110.0)
    assert out["risked_mw"].sum() == pytest.approx(15.0 + 62.0 + 200.0 + 126.0)


def test_risk_weights_are_unchanged_disclosed_conventions():
    assert RISK_WEIGHTS == {
        "Operating": 1.00,
        "Under Construction": 1.00,
        "Approved_power": 0.75,
        "Approved_no_power": 0.25,
        "Proposed": 0.00,
        "Announced": 0.00,
        "Unknown": 0.00,
    }
    # Rows without stage evidence keep the legacy behaviour: weighted on
    # facility_mw (no MW is guessed from absence of a stage split).
    df = pd.DataFrame([
        _project("Eastern Creek", "Operating", 200.0, "Campus capacity; stage split not stored", 2018),
        _project("S4", "Proposed", 350.0, "Row-level sourced capacity", 2028, risk_weight=0.0),
    ])
    out = apply_risk_weight(df)
    assert out.loc[out["project_name"] == "Eastern Creek", "risked_mw"].iloc[0] == pytest.approx(200.0)
    assert out.loc[out["project_name"] == "S4", "risked_mw"].iloc[0] == pytest.approx(0.0)


# --- Undated bucket (no 2028 cliff) ----------------------------------------

def test_forecast_partition_buckets_undated_pipeline():
    df = pd.DataFrame([
        _project("Marsden Park", "Approved", 504.0, "Campus power-consumption envelope",
                 None, risk_weight=0.25),
        _project("S7", "Proposed", 550.0, "Campus full-build envelope", None, risk_weight=0.0),
        _project("Keppel Morwell", "Proposed", 720.0, "Row-level sourced capacity",
                 None, risk_weight=0.0),
        _project("S4", "Proposed", 350.0, "Row-level sourced capacity", 2028, risk_weight=0.0),
        _project("Eastern Creek", "Operating", 200.0, "Campus capacity; stage split not stored", 2018),
        _project("Vantage MEL1", "Operating", 64.0, "Row-level sourced capacity", None),
    ])

    part = forecast_partition(df)
    dated = part["dated"]
    undated = part["undated"]

    # Undated bucket = the three non-operating rows with no sourced year
    assert set(undated["project_name"]) == {"Marsden Park", "S7", "Keppel Morwell"}
    assert part["undated_rows"] == 3
    assert part["undated_mw"] == pytest.approx(504.0 + 550.0 + 720.0)
    # Nothing in the undated bucket was given a fabricated delivery year
    assert undated["startup_year"].isna().all()

    # Dated: 2028-dated pipeline stays dated; operating-without-year is treated
    # as existing capacity from chart start, not as undated pipeline
    assert set(dated["project_name"]) == {"S4", "Eastern Creek", "Vantage MEL1"}
    years = dated.set_index("project_name")["startup_year"]
    assert years["S4"] == 2028
    assert years["Vantage MEL1"] == EXISTING_CAPACITY_DISPLAY_YEAR
    # Recorded totals reconcile without invented splits
    assert part["undated_mw"] + dated["facility_mw"].sum() == pytest.approx(
        504.0 + 550.0 + 720.0 + 350.0 + 200.0 + 64.0
    )


def test_forecast_partition_no_pinned_2028_for_undated_rows():
    """Regression: the old code pinned every undated non-operating row to 2028,
    creating a delivery cliff. No row may be assigned 2028 unless a source gave
    it 2028."""
    df = pd.DataFrame([
        _project("Marsden Park", "Approved", 504.0, "Campus power-consumption envelope",
                 None, risk_weight=0.25),
        _project("S4", "Proposed", 350.0, "Row-level sourced capacity", 2028, risk_weight=0.0),
    ])
    part = forecast_partition(df)
    undated_years = set(part["undated"]["startup_year"].dropna())
    assert undated_years == set()  # undated row kept its NaN
    dated_2028 = set(
        part["dated"].loc[part["dated"]["startup_year"] == 2028, "project_name"]
    )
    assert dated_2028 == {"S4"}  # only the genuinely 2028-dated row


# --- risk tier groups ------------------------------------------------------

def test_risk_tier_group_mapping():
    assert risk_tier_group("Operating", 1.0) == "Operating"
    assert risk_tier_group("Under Construction", 1.0) == "Under Construction"
    assert risk_tier_group("Approved", 0.75) == "Approved — Power Secured"
    assert risk_tier_group("Approved", 0.25) == "Approved — Grid Pending"
    assert risk_tier_group("Proposed", 0.0) == "Proposed"
    assert risk_tier_group("Announced", 0.0) == "Proposed"
    assert risk_tier_group("Unknown", None) == "Proposed"
