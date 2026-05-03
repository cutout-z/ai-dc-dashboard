"""News materiality scoring — source trust, ticker relevance, recency decay.

Attaches a composite materiality score (0.0–1.0) to each news item without
changing the UI.  The score is ready for a future sort-by-materiality toggle.

Composite formula:
    score = w_recency * recency + w_trust * source_trust + w_ticker * ticker_match

Default weights: recency 0.40, trust 0.25, ticker 0.35.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

# ──────────────────────────────────────────────
# Source trust map
# ──────────────────────────────────────────────
# Tier 1 (1.0)  — Company blogs / IRs (first-party)
# Tier 2 (0.85) — Tier-1 financial press
# Tier 3 (0.70) — Domain-specific trade press
# Tier 4 (0.55) — General tech press
# Tier 5 (0.40) — Aggregators / unknown (default)
#
# Keys are lowercase substrings matched against the RSS source field.

_SOURCE_TRUST: dict[str, float] = {
    # Tier 1 — first-party
    "anthropic": 1.0,
    "openai": 1.0,
    "nvidia blog": 1.0,
    "nvidia newsroom": 1.0,
    "google ai blog": 1.0,
    "deepmind": 1.0,
    "meta ai": 1.0,
    "microsoft blog": 1.0,
    "microsoft azure": 1.0,
    "amazon science": 1.0,
    "amazon web services": 1.0,
    "oracle": 1.0,
    "tsmc": 1.0,
    "sec.gov": 1.0,
    # Tier 2 — financial press
    "bloomberg": 0.85,
    "financial times": 0.85,
    "reuters": 0.85,
    "wall street journal": 0.85,
    "wsj": 0.85,
    "cnbc": 0.85,
    "the information": 0.85,
    "nikkei": 0.85,
    "barron": 0.85,
    "ft.com": 0.85,
    # Tier 3 — trade press
    "datacenterdynamics": 0.70,
    "the register": 0.70,
    "semianalysis": 0.70,
    "anandtech": 0.70,
    "tom's hardware": 0.70,
    "utility dive": 0.70,
    "latitude media": 0.70,
    "hpcwire": 0.70,
    "servethehome": 0.70,
    "electrek": 0.70,
    # Tier 4 — general tech
    "techcrunch": 0.55,
    "the verge": 0.55,
    "ars technica": 0.55,
    "wired": 0.55,
    "mit technology review": 0.55,
    "venturebeat": 0.55,
    "engadget": 0.55,
    "zdnet": 0.55,
    "cnet": 0.55,
}

_DEFAULT_TRUST = 0.40


def get_source_trust(source: str) -> float:
    """Return trust score for a news source name (case-insensitive substring match)."""
    lower = source.lower()
    for key, score in _SOURCE_TRUST.items():
        if key in lower:
            return score
    return _DEFAULT_TRUST


# ──────────────────────────────────────────────
# Ticker matcher
# ──────────────────────────────────────────────
# Tracked entities from equities.py MAG7_AI_STOCKS + ANZ_EARNINGS_TICKERS
# plus key private companies from the news buckets.

_TRACKED_PATTERNS: dict[str, list[re.Pattern]] = {
    # Mag 7
    "AAPL":  [re.compile(r"\bApple\b"), re.compile(r"\bAAPL\b")],
    "MSFT":  [re.compile(r"\bMicrosoft\b"), re.compile(r"\bMSFT\b"), re.compile(r"\bAzure\b")],
    "GOOGL": [re.compile(r"\bAlphabet\b"), re.compile(r"\bGOOGL?\b"), re.compile(r"\bGoogle\b")],
    "AMZN":  [re.compile(r"\bAmazon\b"), re.compile(r"\bAMZN\b"), re.compile(r"\bAWS\b")],
    "NVDA":  [re.compile(r"\bNVIDIA\b", re.I), re.compile(r"\bNVDA\b"), re.compile(r"\bJensen Huang\b")],
    "META":  [re.compile(r"\bMeta Platforms\b"), re.compile(r"\bMETA\b"), re.compile(r"\bMeta\b(?!\s*data)")],
    "TSLA":  [re.compile(r"\bTesla\b"), re.compile(r"\bTSLA\b")],
    # AI Infra
    "ORCL":  [re.compile(r"\bOracle\b"), re.compile(r"\bORCL\b")],
    "AMD":   [re.compile(r"\bAMD\b"), re.compile(r"\bAdvanced Micro\b")],
    "TSM":   [re.compile(r"\bTSMC\b"), re.compile(r"\bTSM\b")],
    "PLTR":  [re.compile(r"\bPalantir\b"), re.compile(r"\bPLTR\b")],
    # DC Operators
    "EQIX":  [re.compile(r"\bEquinix\b"), re.compile(r"\bEQIX\b")],
    "DLR":   [re.compile(r"\bDigital Realty\b"), re.compile(r"\bDLR\b")],
    "AMT":   [re.compile(r"\bAmerican Tower\b"), re.compile(r"\bAMT\b")],
    # ANZ
    "NXT.AX": [re.compile(r"\bNextDC\b", re.I)],
    "IFT.NZ": [re.compile(r"\bInfratil\b"), re.compile(r"\bCDC Data Centres\b")],
    "MQG.AX": [re.compile(r"\bMacquarie\b")],
    "GMG.AX": [re.compile(r"\bGoodman Group\b")],
    # Key privates (from news buckets)
    "OpenAI":    [re.compile(r"\bOpenAI\b"), re.compile(r"\bSam Altman\b")],
    "Anthropic": [re.compile(r"\bAnthropic\b"), re.compile(r"\bDario Amodei\b")],
    "xAI":       [re.compile(r"\bxAI\b"), re.compile(r"\bElon Musk\b.*\bAI\b")],
    "DeepSeek":  [re.compile(r"\bDeepSeek\b")],
    "Mistral":   [re.compile(r"\bMistral\b")],
    "CoreWeave": [re.compile(r"\bCoreWeave\b"), re.compile(r"\bCRWV\b")],
}

# Adjacent entities — relevant but not directly tracked
_ADJACENT_PATTERNS: dict[str, list[re.Pattern]] = {
    "ASML":     [re.compile(r"\bASML\b")],
    "AVGO":     [re.compile(r"\bBroadcom\b"), re.compile(r"\bAVGO\b")],
    "INTC":     [re.compile(r"\bIntel\b"), re.compile(r"\bINTC\b")],
    "MU":       [re.compile(r"\bMicron\b"), re.compile(r"\bMU\b")],
    "SMCI":     [re.compile(r"\bSuper Micro\b"), re.compile(r"\bSMCI\b")],
    "ARM":      [re.compile(r"\bArm Holdings\b"), re.compile(r"\bARM\b")],
    "SK Hynix": [re.compile(r"\bSK [Hh]ynix\b"), re.compile(r"\bHBM\b")],
    "Samsung":  [re.compile(r"\bSamsung\b.*\bsemiconductor\b", re.I)],
    "AirTrunk": [re.compile(r"\bAirTrunk\b")],
    "SoftBank": [re.compile(r"\bSoftBank\b"), re.compile(r"\bStargate\b")],
}


def get_ticker_relevance(text: str) -> float:
    """Score ticker relevance of text (headline + summary).

    Returns 1.0 for tracked entity match, 0.5 for adjacent, 0.0 for none.
    """
    for patterns in _TRACKED_PATTERNS.values():
        for pat in patterns:
            if pat.search(text):
                return 1.0
    for patterns in _ADJACENT_PATTERNS.values():
        for pat in patterns:
            if pat.search(text):
                return 0.5
    return 0.0


# ──────────────────────────────────────────────
# Recency decay
# ──────────────────────────────────────────────

_HALF_LIFE_HOURS = 12.0
_DECAY_CONSTANT = 0.693 / _HALF_LIFE_HOURS  # ln(2) / half-life


def get_recency_score(published: datetime | None) -> float:
    """Exponential decay score. 1.0 at publish time, 0.5 at 12h, ~0.25 at 24h."""
    if published is None:
        return 0.3  # unknown age — slight penalty
    now = datetime.now(timezone.utc)
    age_hours = max((now - published).total_seconds() / 3600, 0)
    return math.exp(-_DECAY_CONSTANT * age_hours)


# ──────────────────────────────────────────────
# Composite score
# ──────────────────────────────────────────────

def score_news_item(
    title: str,
    summary: str,
    source: str,
    published: datetime | None,
    *,
    recency_weight: float = 0.40,
    trust_weight: float = 0.25,
    ticker_weight: float = 0.35,
) -> float:
    """Compute materiality score for a single news item (0.0–1.0)."""
    recency = get_recency_score(published)
    trust = get_source_trust(source)
    ticker = get_ticker_relevance(f"{title} {summary}")
    return round(
        recency_weight * recency + trust_weight * trust + ticker_weight * ticker,
        3,
    )


# ──────────────────────────────────────────────
# Materiality tiers
# ──────────────────────────────────────────────

TIER_HIGH_THRESHOLD = 0.65
TIER_MEDIUM_THRESHOLD = 0.40

TIER_COLORS = {
    "HIGH":   "#ef4444",  # red
    "MEDIUM": "#f59e0b",  # amber
    "LOW":    "#6b7280",  # grey
}

TIER_LABELS = {
    "HIGH":   "🔴 HIGH",
    "MEDIUM": "🟡 MEDIUM",
    "LOW":    "⚪ LOW",
}


def get_materiality_tier(score: float) -> str:
    """Classify a materiality score into HIGH / MEDIUM / LOW."""
    if score >= TIER_HIGH_THRESHOLD:
        return "HIGH"
    if score >= TIER_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"
