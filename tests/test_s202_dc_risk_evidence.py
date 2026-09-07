"""S2-02 (B2) verification: DC risk monitor fails closed on evidence gaps.

Covers the Astra review reproductions:
- nine gray signals -> "limited evidence", not green;
- metadata-only equities -> breadth not green;
- 2001 positive-financing stories -> not red;
- global-only warnings -> amber with explicit limited-evidence statement;
- only AU-direct evidence can produce red/green headlines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.lib.dc_risk_signals import (  # noqa: E402
    AU_DIRECT_SIGNALS,
    RiskSignal,
    capital_markets_signal,
    market_breadth_signal,
    overall_status,
)


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


ALL_SIGNAL_NAMES = [
    "Tracked AU/ANZ contracted demand",
    "Project execution and permitting",
    "Hyperscaler commitment",
    "Tracked power procurement composition",
    "Power deliverability",
    "Capital markets",
    "Buildout financing exposure",
    "Market breadth",
    "Model economics",
]


def test_nine_gray_signals_not_green() -> None:
    signals = [_sig(n, "gray") for n in ALL_SIGNAL_NAMES]
    assert len(signals) == 9
    overall = overall_status(signals)
    assert overall["status"] == "gray"
    assert "imited evidence" in overall["label"]
    assert overall["status"] != "green"


def test_two_global_warnings_amber_limited_evidence() -> None:
    # Review reproduction: AU-direct green, red votes from US-heavy queue +
    # news proxy only -> must NOT be red, and must state limited evidence.
    signals = [
        _sig("Tracked AU/ANZ contracted demand", "green"),
        _sig("Project execution and permitting", "green"),
        _sig("Power deliverability", "red"),
        _sig("Capital markets", "red"),
        _sig("Hyperscaler commitment", "green"),
        _sig("Tracked power procurement composition", "green"),
        _sig("Buildout financing exposure", "green"),
        _sig("Market breadth", "green"),
        _sig("Model economics", "green"),
    ]
    overall = overall_status(signals)
    assert overall["status"] == "amber"
    assert "limited evidence" in overall["label"].lower()
    assert "not AU-confirmed" in overall["label"]
    assert overall["status"] != "red"


def test_only_au_direct_can_produce_red() -> None:
    signals = [_sig(n, "red") for n in ALL_SIGNAL_NAMES if n not in AU_DIRECT_SIGNALS]
    signals += [_sig(n, "green") for n in AU_DIRECT_SIGNALS]
    overall = overall_status(signals)
    assert overall["status"] == "amber"  # global reds capped at amber


def test_au_direct_red_produces_red() -> None:
    signals = [_sig(n, "green") for n in ALL_SIGNAL_NAMES]
    signals[1] = _sig("Project execution and permitting", "red")
    overall = overall_status(signals)
    assert overall["status"] == "red"


def test_demoted_coverage_names_cannot_vote_red() -> None:
    # S2-05: the demoted coverage signals are no longer AU-direct voters even if
    # a synthetic caller hands them a red status.
    assert "Tracked AU/ANZ contracted demand" not in AU_DIRECT_SIGNALS
    assert "Tracked power procurement composition" not in AU_DIRECT_SIGNALS
    signals = [_sig(n, "green") for n in ALL_SIGNAL_NAMES]
    signals[0] = _sig("Tracked AU/ANZ contracted demand", "red")
    signals[3] = _sig("Tracked power procurement composition", "red")
    overall = overall_status(signals)
    assert overall["status"] != "red"


def test_green_requires_all_scored_au_direct() -> None:
    signals = [_sig(n, "green") for n in ALL_SIGNAL_NAMES]
    overall = overall_status(signals)
    assert overall["status"] == "green"
    assert "AU-direct" in overall["label"]
    # any gray input blocks green — evidence is incomplete, so no green claim
    signals[-1] = _sig("Model economics", "gray")
    overall = overall_status(signals)
    assert overall["status"] == "gray"
    assert "imited evidence" in overall["label"]
    all_gray_except_au = [_sig(n, "gray") for n in ALL_SIGNAL_NAMES]
    all_gray_except_au[1] = _sig("Project execution and permitting", "green")
    assert overall_status(all_gray_except_au)["status"] == "gray"


def test_metadata_only_equities_not_green() -> None:
    # 14 equities with metadata but zero quote/fundamental observations.
    stocks = [
        {
            "symbol": f"T{i}",
            "name": f"Company {i}",
            "group": "DC Operators" if i % 2 else "Mag 7",
            "returns": {"1M": None, "3M": None, "6M": None, "1Y": None},
            "pct_from_high": None,
        }
        for i in range(14)
    ]
    sig = market_breadth_signal(stocks)
    assert sig.status == "gray"
    assert sig.status != "green"


def test_rich_quotes_still_score() -> None:
    stocks = [
        {
            "symbol": "DC1",
            "name": "DC Operator",
            "group": "DC Operators",
            "returns": {"1M": -2, "3M": -5, "6M": 5, "1Y": 10},
            "pct_from_high": -5,
        },
        {
            "symbol": "MG1",
            "name": "Mag7",
            "group": "Mag 7",
            "returns": {"1M": 1, "3M": 3, "6M": 15, "1Y": 25},
            "pct_from_high": -2,
        },
    ]
    sig = market_breadth_signal(stocks)
    assert sig.status in {"green", "amber", "red"}  # scored, not degraded


def _catalog(tmp_path: Path, rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)
    path = tmp_path / "news_catalog.csv"
    df.to_csv(path, index=False)
    return path


def _row(title: str, summary: str, published: str) -> dict:
    return {
        "title": title,
        "summary": summary,
        "published": published,
        "first_seen_at": published,
        "last_seen_at": published,
        "last_tier": "HIGH",
        "last_bucket": "credit",
        "source": "fixture",
        "url": "https://example.com",
    }


def test_2001_positive_financing_not_red(tmp_path: Path) -> None:
    rows = [
        _row(
            "NEXTDC successfully raised new debt facility",
            "Company raised and upsized financing; closed a new loan facility.",
            "2001-05-01T00:00:00Z",
        )
        for _ in range(10)
    ]
    sig = capital_markets_signal(data_dir=_catalog(tmp_path, rows).parent)
    assert sig.status != "red"
    assert sig.status == "gray"  # outside declared lookback -> no present-tense signal


def test_recent_positive_financing_not_red(tmp_path: Path) -> None:
    now = pd.Timestamp.now(tz="UTC")
    rows = [
        _row(
            "Operator raised new facility",
            "Successfully secured refinancing; closed a new loan.",
            (now - pd.Timedelta(days=10)).isoformat(),
        )
        for _ in range(6)
    ]
    sig = capital_markets_signal(data_dir=_catalog(tmp_path, rows).parent)
    assert sig.status != "red"


def test_never_red_even_with_many_adverse(tmp_path: Path) -> None:
    now = pd.Timestamp.now(tz="UTC")
    rows = [
        _row(
            f"Credit deterioration story {i}",
            "Spreads widened and the deal failed; lenders demanded a haircut.",
            (now - pd.Timedelta(days=i + 1)).isoformat(),
        )
        for i in range(9)
    ]
    sig = capital_markets_signal(data_dir=_catalog(tmp_path, rows).parent)
    assert sig.status == "amber"  # adverse events surface, but never red
    assert "adverse" in sig.value


def test_events_are_dated_and_classified(tmp_path: Path) -> None:
    now = pd.Timestamp.now(tz="UTC")
    rows = [
        _row(
            "Debt facility pulled by lenders",
            "The credit deal failed after lenders halted syndication.",
            (now - pd.Timedelta(days=5)).isoformat(),
        ),
        _row(
            "Neutral credit mention",
            "Routine bond programme paperwork filed.",
            (now - pd.Timedelta(days=6)).isoformat(),
        ),
    ]
    sig = capital_markets_signal(data_dir=_catalog(tmp_path, rows).parent)
    assert any("[adverse]" in e for e in sig.evidence)
    assert any("[neutral]" in e for e in sig.evidence)
    assert any("Lookback: 90 days" in e for e in sig.evidence)
    # dated evidence
    assert any(e[10:20].count("-") == 2 for e in sig.evidence if e.startswith("["))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
