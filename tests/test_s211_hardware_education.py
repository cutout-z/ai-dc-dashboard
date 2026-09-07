"""S2-11 (C13) verification: hardware-education pages without false quantitative authority.

Review reproductions (astra-review-2026-09-04 S2-11):
- supplier-risk scores like 4.75 and probabilities like 5-10%/40-50% were hardcoded
  without displayed inputs, a dated method or a horizon; the app's 4-factor 1-5
  scoring contradicted the vault research's three-factor 1-10 method;
- technology_roadmaps assigned H100/B200 to 4N/4NP in the NVIDIA table but listed
  them under N3/N3E in the Process Node Roadmap (same file) — a self-contradiction
  (4N/4NP are 5nm-family custom nodes, not 3nm); B300 was also listed under N3P;
- Rubin "will make" Blackwell "economically stranded" was stated unconditionally,
  without a workload/cost model.

After the fix (verify criteria):
- retained judgements are qualitative tiers/likelihoods explicitly labelled as
  editorial with an as-of date and a stated basis — no bare numeric scores or
  percentage probabilities;
- every component page carries a dated "Sources & as-of (2026-09)" caption
  (all eight pages previously had no source URL);
- process-node tables are internally consistent: H100/H200 (4N) and B200/B300 (4NP)
  live under the N5 family, Rubin under N3-class, MI300X under N5/N6, MI350 N3P;
- a new-generation release alone never implies existing collateral has no economic
  value — obsolescence statements are conditional on workload/utilization/prices.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPONENTS = REPO / "app" / "views" / "supply_chain" / "components"

ALL_PAGES = [
    "credit_primer.py",
    "accelerator_architecture.py",
    "memory_subsystem.py",
    "advanced_packaging.py",
    "interconnect_networking.py",
    "system_integration.py",
    "supply_chain_mapping.py",
    "technology_roadmaps.py",
]


def _page(name: str) -> str:
    return (COMPONENTS / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- page captions

def test_every_component_page_has_dated_source_caption():
    for name in ALL_PAGES:
        assert "Sources & as-of (2026-09)" in _page(name), f"{name} lacks dated source caption"


def test_every_component_page_labels_judgements_editorial():
    # Each page must carry at least one explicit "editorial"/"judgement"/"est." qualifier
    # on the quantitative content (not only the caption).
    for name in ALL_PAGES:
        text = _page(name)
        assert re.search(r"editorial|judgement|\(est\.\)|approximate", text, re.I), name


# ------------------------------------------------- supply_chain_mapping scores/tiers

def test_supply_chain_mapping_removes_numeric_score_column():
    text = _page("supply_chain_mapping.py")
    assert "Score" not in text or '"Score"' not in text, "numeric Score column removed"
    assert "4.75" not in text and "4.50" not in text, "hardcoded decimal scores gone"
    assert "Score = f(" not in text, "fake scoring formula caption gone"


def test_supply_chain_mapping_uses_qualitative_tiers():
    text = _page("supply_chain_mapping.py")
    assert "Risk Tier" in text
    for tier in ("Maximum", "High", "Elevated", "Moderate", "Low"):
        assert tier in text, f"tier {tier} present"


def test_supply_chain_mapping_removes_numeric_stress_probabilities():
    text = _page("supply_chain_mapping.py")
    for token in ("(5-10%)", "(10-15%)", "(20-30%)", "(40-50%)", "(30-40%)"):
        assert token not in text, f"{token} probability band removed"
    assert "editorial, 12-mo" in text, "stress likelihoods labelled editorial with horizon"


# -------------------------------------------------- technology_roadmaps reconciliation

def _node_table_block(text: str) -> str:
    start = text.index('"Process Node Roadmap"')
    end = text.index("columns=[\"Node\"")
    return text[start:end]


def _node_row(block: str, prefix: str) -> str:
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith('("' + prefix):
            return stripped
    raise AssertionError(f"row starting {prefix!r} not found in process-node table")


def test_roadmaps_process_node_table_no_n3_contradiction():
    text = _page("technology_roadmaps.py")
    block = _node_table_block(text)
    # The N3-family row must NOT carry H100/B200 (they are 4N/4NP = N5-family custom).
    n3_row = _node_row(block, "TSMC N3 family")
    assert "H100" not in n3_row, "H100 not listed under N3"
    assert "B200" not in n3_row, "B200 not listed under N3"
    assert "Rubin" in n3_row, "N3 row carries Rubin (announced)"
    # The N5-family row carries H100/H200/B200/B300 via their real 4N/4NP labels.
    n5_row = _node_row(block, "TSMC N5 family")
    assert "4N" in n5_row and "4NP" in n5_row
    assert "H100/H200" in n5_row and "B200/B300" in n5_row


def test_roadmaps_no_stale_n3_users_rows():
    text = _page("technology_roadmaps.py")
    # Old rows that assigned H100/B200/MI300X to N3/N3E and B300 to N3P are gone.
    assert '"H100, B200, MI300X"' not in text
    assert '"B300, Rubin"' not in text
    assert '"Rubin Ultra, Feynman"' not in text  # Rubin Ultra is N3-class per vendor table


def test_roadmaps_rubin_first_n3_class_announced():
    text = _page("technology_roadmaps.py")
    assert "Rubin is NVIDIA's first announced N3-class part" in text
    assert "2026 (announced)" in text
    assert "not shipped product" in text or "not independently verified" in text


def test_roadmaps_inflection_likelihoods_qualitative():
    text = _page("technology_roadmaps.py")
    assert '"High (90%+)"' not in text
    assert '"High (80%+)"' not in text
    assert '"Moderate (40-60%)"' not in text
    assert "Likelihood (editorial)" in text


def test_roadmaps_obsolescence_conditional_not_automatic():
    text = _page("technology_roadmaps.py")
    assert "will make Blackwell-based collateral economically stranded" not in text
    assert "economically stranded for training workloads" not in text
    assert "depends on workload mix, utilisation" in text
    assert "does not automatically strand the prior one" in text
    assert "no forward-looking statement here asserts automatic" in text.lower() or \
        "no forward-looking statement here asserts automatic" in text


# ------------------------------------------------------- credit_primer share honesty

def test_credit_primer_dependency_share_labelled_editorial():
    text = _page("credit_primer.py")
    assert "NVIDIA Share %" not in text, "unqualified share column removed"
    assert "editorial est." in text
    assert "not audited market data" in text
    assert "100% rows are structural" in text or "structural (proprietary" in text


def test_credit_primer_spof_hidden_score_removed():
    text = _page("credit_primer.py")
    assert '"Score"' not in text, "hidden SPOF Score column removed"
    assert "Dominant Supplier (est. share)" in text


def test_credit_primer_timeline_no_percentage_forecast():
    text = _page("credit_primer.py")
    assert "10-15% training share" not in text, "percentage share forecast removed"
    assert "not probability-weighted forecasts" in text


# ------------------------------------------------------- no unconditional stranding

def test_no_page_claims_new_generation_zeroes_old_collateral():
    # Verify criterion: a new-generation release alone cannot imply existing
    # collateral has no economic value.
    for name in ALL_PAGES:
        text = _page(name)
        assert "has zero standalone memory value" not in text, name
        assert "the GPUs inside do not" not in text, name
        assert "strands the previous generation" not in text, name
        assert "make Blackwell-based collateral economically stranded" not in text, name


# ------------------------------------------------------------------- consistency

def test_h100_b200_process_labels_consistent_across_pages():
    # accelerator_architecture (spec table) and technology_roadmaps (vendor table)
    # must agree that H100/H200 = 4N and B200/B300 = 4NP.
    acc = _page("accelerator_architecture.py")
    road = _page("technology_roadmaps.py")
    for label in ("4nm 4N", "4nm 4NP"):
        assert label in acc
    for label in ("TSMC 4N", "TSMC 4NP", "TSMC 3N (N3-class)"):
        assert label in road
    # N5-family custom labels appear in the reconciled process table.
    assert "N5 family (incl. NVIDIA 4N/4NP)" in road


def test_all_pages_compile():
    import py_compile
    for name in ALL_PAGES:
        py_compile.compile(str(COMPONENTS / name), doraise=True)
