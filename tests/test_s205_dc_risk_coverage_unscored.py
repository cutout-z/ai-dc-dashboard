"""S2-05 (C7) verification: coverage ratios demoted to unscored context.

Review reproductions:
- "95% firm/PPA" (138.2 GW firm/PPA of 145.2 GW tracked procurement
  disclosures) must no longer be a green/amber/red coverage verdict;
- "49% contracted demand" (1,667 MW CDC/NEXTDC disclosures over 3,380.65 MW
  named-project base) must no longer be a green quality verdict;
- outputs renamed, absolute sourced amounts preserved, ratio/colour removed
  until numerator and denominator populations match;
- adding unrelated supply-chain PPAs or new uncontracted projects cannot
  improve/worsen operational coverage (there is no coverage colour to move);
- AU/NZ-vs-AU geography mismatch and speculative supply stay visible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.lib.dc_risk_signals import (  # noqa: E402
    AU_DIRECT_SIGNALS,
    STATUS_LABELS,
    RiskSignal,
    contracted_demand_signal,
    overall_status,
    power_procurement_coverage_signal,
)

DEMAND_NAME = "Tracked AU/ANZ contracted demand"
PROCUREMENT_NAME = "Tracked power procurement composition"


def _procurement_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "dc_power_sourcing.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _sourcing_row(
    company: str,
    gw: float,
    status: str,
    source_type: str = "Renewable PPA (Tracked)",
    announced: str = "2025-01-01",
    details: str = "",
) -> dict:
    return {
        "company": company,
        "source_type": source_type,
        "capacity_gw": gw,
        "status": status,
        "counterparty": "fixture",
        "announced_date": announced,
        "details": details,
        "reference": "fixture",
    }


# --- Procurement composition -------------------------------------------------

def test_95pct_contracted_status_is_unscored_context(tmp_path: Path) -> None:
    # Review reproduction: 138.2 / 145.2 GW = 95% "firm/PPA". Includes an
    # undelivered speculative fusion PPA and a supply-chain clean-energy row.
    rows = [
        _sourcing_row("Microsoft", 40.0, "Contracted"),
        _sourcing_row("Amazon", 35.0, "Contracted"),
        _sourcing_row("Google", 30.0, "Contracted"),
        _sourcing_row("Meta", 20.0, "Contracted"),
        _sourcing_row("Apple", 10.0, "Contracted", "Clean Energy (Total incl Supply Chain)"),
        _sourcing_row("Oracle", 1.0, "PPA", "Nuclear (Fusion)", details="Speculative fusion PPA"),
        _sourcing_row("Microsoft", 0.05, "PPA", "Nuclear (Fusion)", details="Speculative timeline"),
        _sourcing_row("Amazon", 0.62, "MOU", "Nuclear (SMR)"),
        _sourcing_row("CoreWeave", 1.3, "Pending"),
        _sourcing_row("Oracle", 1.0, "Planned", "Nuclear (SMR)"),
        _sourcing_row("Meta", 4.0, "Agreement", "Nuclear (TerraPower)"),
        _sourcing_row("Microsoft", 2.0, "Actual"),
    ]
    sig = power_procurement_coverage_signal(data_dir=_procurement_csv(tmp_path, rows).parent)
    assert sig.name == PROCUREMENT_NAME
    assert sig.status == "context", "95% contracted-status mix must be unscored context, not green"
    assert sig.status not in {"green", "amber", "red"}
    assert STATUS_LABELS[sig.status] == "Context only"
    # absolute amounts preserved; the old ratio-headline is gone
    assert "GW" in sig.value
    assert not sig.value.endswith("% firm/PPA")
    assert "%" not in sig.value, "value should carry absolute GW, not a percentage headline"
    # detail states the population mismatch and the firm-supply caveat
    assert "not matched" in sig.detail.lower() or "different populations" in sig.detail.lower()
    assert "firm available supply" in sig.detail.lower()
    # speculative supply remains visible per row (table carries status/details)
    assert sig.table is not None
    blob = sig.table.to_string()
    assert "Speculative fusion PPA" in blob
    assert "MOU" in blob


def test_low_contracted_status_mix_also_unscored_context(tmp_path: Path) -> None:
    # Old logic: <50% firm share -> red. New logic: still unscored context.
    rows = [
        _sourcing_row("A", 1.0, "Contracted"),
        _sourcing_row("B", 9.0, "MOU"),
        _sourcing_row("C", 10.0, "Planned"),
    ]
    sig = power_procurement_coverage_signal(data_dir=_procurement_csv(tmp_path, rows).parent)
    assert sig.status == "context"
    assert sig.status != "red"


def test_adding_supply_chain_or_uncontracted_rows_cannot_move_coverage(tmp_path: Path) -> None:
    base = [
        _sourcing_row("Microsoft", 40.0, "Contracted"),
        _sourcing_row("Amazon", 35.0, "Contracted"),
    ]
    base_dir = _procurement_csv(tmp_path, base).parent
    sig = power_procurement_coverage_signal(data_dir=base_dir)
    assert sig.status == "context"

    # Adding an unrelated supply-chain PPA or a newly discovered uncontracted
    # project cannot falsely improve/worsen operational coverage: the signal
    # has no coverage colour to move, and absolute composition is what changes.
    grown = base + [
        _sourcing_row("Apple", 12.0, "Contracted", "Clean Energy (Total incl Supply Chain)"),
        _sourcing_row("CoreWeave", 8.0, "Pending"),
    ]
    grown_dir = tmp_path / "grown"
    grown_dir.mkdir()
    sig2 = power_procurement_coverage_signal(data_dir=_procurement_csv(grown_dir, grown).parent)
    assert sig2.status == "context"
    assert sig2.status == sig.status


def test_procurement_missing_file_is_gray_empty(tmp_path: Path) -> None:
    sig = power_procurement_coverage_signal(data_dir=tmp_path)
    assert sig.status == "gray"
    assert sig.value == "No score"
    assert sig.name == PROCUREMENT_NAME


# --- Contracted demand -------------------------------------------------------

def _operator_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "operator_aggregate_guidance.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _operator_row(
    operator: str,
    geography: str,
    contracted: float | None,
    named: float | None,
    forward: float | None = None,
    new: float | None = None,
) -> dict:
    return {
        "operator": operator,
        "announcement_date": "2026-05-08",
        "last_verified_at": "2026-05-08",
        "geography": geography,
        "contracted_capacity_mw": contracted,
        "forward_order_book_mw": forward,
        "new_contract_mw": new,
        "named_project_mw_in_db": named,
        "source": "fixture",
        "evidence_summary": "fixture disclosure",
        "treatment_notes": "fixture",
    }


def test_49pct_contracted_demand_is_unscored_context(tmp_path: Path) -> None:
    # Review reproduction: 1,667 MW contracted (CDC AU/NZ 1,000 + NEXTDC
    # portfolio 667) over 3,380.65 MW named-project base -> old green verdict.
    rows = [
        _operator_row("CDC Data Centres", "Australia and New Zealand", 1000.0, 1789.0, new=555.0),
        _operator_row("NEXTDC", "NEXTDC portfolio", 667.0, 1591.65, forward=544.0, new=250.0),
    ]
    sig = contracted_demand_signal(au_dc_dir=_operator_csv(tmp_path, rows).parent)
    assert sig.name == DEMAND_NAME
    assert sig.status == "context", "49% contracted demand must be unscored context, not green"
    assert sig.status not in {"green", "amber", "red"}
    # absolute sourced disclosure preserved in value
    assert "1,667MW" in sig.value
    # no coverage/quality ratio claim anywhere in the output strings
    for field in (sig.value, sig.detail):
        assert "% of named project MW" not in field
        assert "coverage" not in field.lower() or "no coverage" in field.lower()
    assert "not matched" in sig.detail
    # geography mismatch stays visible in the underlying rows
    assert sig.table is not None
    geos = sig.table["geography"].astype(str).tolist()
    assert "Australia and New Zealand" in geos
    assert "NEXTDC portfolio" in geos


def test_zero_contracted_still_context_when_disclosures_exist(tmp_path: Path) -> None:
    rows = [
        _operator_row("NEXTDC", "NEXTDC portfolio", None, None, forward=544.0),
    ]
    sig = contracted_demand_signal(au_dc_dir=_operator_csv(tmp_path, rows).parent)
    assert sig.status == "context"
    assert "544MW" in sig.value or "544MW" in sig.detail


def test_contracted_demand_missing_file_is_gray_empty(tmp_path: Path) -> None:
    sig = contracted_demand_signal(au_dc_dir=tmp_path)
    assert sig.status == "gray"
    assert sig.value == "No score"
    assert sig.name == DEMAND_NAME


# --- Aggregate semantics -----------------------------------------------------

def _sig(name: str, status: str) -> RiskSignal:
    return RiskSignal(
        name=name,
        status=status,
        value="x",
        detail="",
        why_it_matters="",
        watch_for="",
        evidence=[],
    )


def _mix(context_names: list[str], au_status: str = "green") -> list[RiskSignal]:
    names = [
        DEMAND_NAME,
        "Project execution and permitting",
        "Hyperscaler commitment",
        PROCUREMENT_NAME,
        "Power deliverability",
        "Capital markets",
        "Buildout financing exposure",
        "Market breadth",
        "Model economics",
    ]
    return [
        _sig(n, "context" if n in context_names else au_status if n == "Project execution and permitting" else "green")
        for n in names
    ]


def test_context_signals_withhold_green_headline() -> None:
    # Everything else green, AU project execution green, but the two demoted
    # coverage dimensions unscored -> aggregate colour withheld (gray), not green.
    overall = overall_status(_mix([DEMAND_NAME, PROCUREMENT_NAME]))
    assert overall["status"] == "gray"
    assert "colour withheld" in overall["label"].lower() or "unscored" in overall["label"].lower()
    assert overall["status"] != "green"


def test_context_signal_cannot_turn_headline_red_or_amber() -> None:
    overall = overall_status(_mix([DEMAND_NAME, PROCUREMENT_NAME]))
    assert overall["status"] not in {"red", "amber"}


def test_demoted_names_not_au_direct_voters() -> None:
    assert DEMAND_NAME not in AU_DIRECT_SIGNALS
    assert PROCUREMENT_NAME not in AU_DIRECT_SIGNALS


def test_gray_still_outranks_context_in_detail_branch() -> None:
    signals = _mix([DEMAND_NAME, PROCUREMENT_NAME])
    signals[5] = _sig("Capital markets", "gray")
    overall = overall_status(signals)
    assert overall["status"] == "gray"
    assert "imited evidence" in overall["label"]
    assert "Unscored context: 2" in overall["detail"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
