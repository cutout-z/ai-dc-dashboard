"""News materiality scoring — source trust, ticker relevance, recency decay.

Attaches a composite materiality score (0.0–1.0) to each news item without
changing the UI.  The score is ready for a future sort-by-materiality toggle.

Composite formula:
    score = event + source + entity + magnitude + recency - noise penalties

HIGH is reserved for material thesis events: contracts, capex/power/MW,
regulatory action, funding/IPO/valuation, export controls, or supply constraints.
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
    "european commission": 1.0,
    "eu commission": 1.0,
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
    "australian financial review": 0.85,
    "afr": 0.85,
    "the australian": 0.85,
    "nz herald": 0.75,
    "newsroom": 0.75,
    "businessdesk": 0.75,
    "capital brief": 0.70,
    "the post": 0.70,
    # Tier 3 — trade press
    "datacenterdynamics": 0.70,
    "data center dynamics": 0.70,
    "data center knowledge": 0.70,
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
    "tipranks": 0.45,
    "yahoo finance": 0.45,
    "investing.com": 0.45,
    "verdict": 0.25,
    "the daily star": 0.25,
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
    # ANZ data-centre operators and listed owners. Diversified listed owners
    # only match when the headline/summary ties them to data-centre activity.
    "NXT.AX": [re.compile(r"\bNextDC\b", re.I), re.compile(r"\bNXT\.AX\b", re.I)],
    "IFT.NZ": [
        re.compile(r"\bCDC Data Centres\b", re.I),
        re.compile(r"\bInfratil\b.{0,140}\b(CDC|data cent(?:er|re)|hyperscale)\b", re.I),
        re.compile(r"\b(CDC|data cent(?:er|re)|hyperscale)\b.{0,140}\bInfratil\b", re.I),
    ],
    "MQG.AX": [
        re.compile(r"\bMacquarie Data Centres\b", re.I),
        re.compile(r"\bMacquarie\b.{0,140}\b(data cent(?:er|re)|hyperscale|cloud services)\b", re.I),
    ],
    "GMG.AX": [
        re.compile(r"\bGoodman\b.{0,140}\b(data cent(?:er|re)|hyperscale|AI infrastructure)\b", re.I),
        re.compile(r"\b(data cent(?:er|re)|hyperscale|AI infrastructure)\b.{0,140}\bGoodman\b", re.I),
    ],
    "AirTrunk": [re.compile(r"\bAirTrunk\b", re.I)],
    "Keppel DC": [re.compile(r"\bKeppel Data Centres?\b", re.I), re.compile(r"\bKeppel DC\b", re.I)],
    "Stack Infrastructure": [re.compile(r"\bStack Infrastructure\b", re.I)],
    "Fujitsu DC": [re.compile(r"\bFujitsu\b.{0,140}\b(data cent(?:er|re)|hyperscale|cloud)\b", re.I)],
    "Vantage Data Centers": [re.compile(r"\bVantage Data Cent(?:ers|res)\b", re.I)],
    "Doma Infrastructure": [re.compile(r"\bDoma Infrastructure Group\b", re.I)],
    "DigiCo": [re.compile(r"\bDigiCo Infrastructure REIT\b", re.I), re.compile(r"\bDigiCo\b.{0,140}\bdata cent(?:er|re)\b", re.I)],
    "Telstra InfraCo": [re.compile(r"\bTelstra InfraCo\b", re.I), re.compile(r"\bTelstra\b.{0,140}\bdata cent(?:er|re)\b", re.I)],
    "Leading Edge DC": [re.compile(r"\bLeading Edge Data Centres?\b", re.I)],
    "NCI": [re.compile(r"\bNCI\b.{0,140}\bdata cent(?:er|re)\b", re.I)],
    # Key privates (from news buckets)
    "OpenAI":    [re.compile(r"\bOpenAI\b"), re.compile(r"\bSam Altman\b")],
    "Anthropic": [re.compile(r"\bAnthropic\b"), re.compile(r"\bDario Amodei\b")],
    "xAI":       [re.compile(r"\bxAI\b"), re.compile(r"\bElon Musk\b.*\bAI\b")],
    "DeepSeek":  [re.compile(r"\bDeepSeek\b")],
    "Mistral":   [re.compile(r"\bMistral\b")],
    "CoreWeave": [re.compile(r"\bCoreWeave\b"), re.compile(r"\bCRWV\b")],
    "Cerebras": [re.compile(r"\bCerebras\b")],
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
# Event materiality
# ──────────────────────────────────────────────

_HIGH_EVENT_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"\b(signs?|signed|inks?|contract|deal|agreement|partnership|wins?|loses?|lost|cancell?ed|terminated|renegotiated)\b"
        r".{0,90}\b(\$|bn|billion|cloud|renewable|ppa|mw|gw|data cent(?:er|re)|ai infrastructure|capacity reservation)\b",
        re.I,
    ),
    re.compile(
        r"\b(\$|bn|billion|cloud|renewable|ppa|mw|gw|data cent(?:er|re)|ai infrastructure|capacity reservation)\b"
        r".{0,90}\b(signs?|signed|inks?|contract|deal|agreement|partnership|wins?|loses?|lost|cancell?ed|terminated|renegotiated)\b",
        re.I,
    ),
    re.compile(
        r"\b(eu commission|european commission|ftc|doj|cma|regulator|antitrust|probe|investigation|in talks with)\b"
        r".{0,120}\b(openai|anthropic|microsoft|google|amazon|apple|meta|nvidia|ai model|cloud)\b",
        re.I,
    ),
    re.compile(
        r"\b(ipo|valuation|funding|fundraise|raises?|raise|debt|bond|burn rate|cash burn|losses|margin)\b"
        r".{0,100}\b(\$|bn|billion|ai demand|cerebras|coreweave|openai|anthropic|xai|revenue)\b",
        re.I,
    ),
    re.compile(
        r"\b(capex|capital expenditure|investment|campus|build|expansion|delay|delayed|pause|paused|cut|cuts)\b"
        r".{0,100}\b(\$|bn|billion|mw|gw|data cent(?:er|re)|ai infrastructure|hyperscale)\b",
        re.I,
    ),
    re.compile(
        r"\b(export controls?|chip curbs?|sanctions?|licen[cs]e|ban)\b"
        r".{0,100}\b(china|nvidia|huawei|smic|gpu|ai chip)\b",
        re.I,
    ),
    re.compile(
        r"\b(cowos|hbm|advanced packaging|blackwell|gpu)\b"
        r".{0,100}\b(shortage|bottleneck|supply|capacity|allocation|orders?)\b",
        re.I,
    ),
    re.compile(
        r"\b(price cut|price war|pricing pressure|margin compression|utili[sz]ation|overcapacity|oversupply|demand slowdown)\b",
        re.I,
    ),
    re.compile(
        r"\b(power constraint|grid constraint|interconnection queue|ppa|renewable|nuclear|gas power)\b"
        r".{0,100}\b(data cent(?:er|re)|ai infrastructure|hyperscale|mw|gw)\b",
        re.I,
    ),
]

_MEDIUM_EVENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(earnings|revenue|guidance|margin|forecast|outlook)\b", re.I),
    re.compile(r"\b(results?|shares?|stock|record high|profit|dividend|upgrade|downgrade)\b", re.I),
    re.compile(r"\b(acquisition|acquires?|sells?|sale|stake|asset sale|takeover)\b", re.I),
    re.compile(r"\b(secures?|awarded|customer|tenant|lease|pre-commitment)\b", re.I),
    re.compile(r"\b(model release|benchmark|gpqa|swe-bench|mmlu|frontier model)\b", re.I),
    re.compile(r"\b(partnership|launch|expands?|rollout)\b", re.I),
]

_MAGNITUDE_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\$|us\$|a\$)\s?\d", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?(bn|billion|million|mw|gw)\b", re.I),
]

_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(evil ai|blackmail|fictional|tropes?|meme|viral|stock is crashing)\b", re.I),
    re.compile(r"\b(token|solana|crypto|airdrop)\b", re.I),
    re.compile(r"\b(how to|explainer|opinion|what is|guide)\b", re.I),
]


def get_event_materiality(text: str) -> float:
    for pattern in _HIGH_EVENT_PATTERNS:
        if pattern.search(text):
            return 1.0
    for pattern in _MEDIUM_EVENT_PATTERNS:
        if pattern.search(text):
            return 0.45
    return 0.0


def get_magnitude_score(text: str) -> float:
    return 1.0 if any(pattern.search(text) for pattern in _MAGNITUDE_PATTERNS) else 0.0


def get_noise_penalty(text: str) -> float:
    penalty = 0.0
    for pattern in _NOISE_PATTERNS:
        if pattern.search(text):
            penalty += 0.22
    return min(penalty, 0.45)


# ──────────────────────────────────────────────
# Composite score
# ──────────────────────────────────────────────

def score_news_item(
    title: str,
    summary: str,
    source: str,
    published: datetime | None,
    *,
    event_weight: float = 0.40,
    trust_weight: float = 0.20,
    ticker_weight: float = 0.25,
    magnitude_weight: float = 0.10,
    recency_weight: float = 0.05,
) -> float:
    """Compute materiality score for a single news item (0.0–1.0)."""
    text = f"{title} {summary}"
    recency = get_recency_score(published)
    trust = get_source_trust(source)
    ticker = get_ticker_relevance(text)
    event = get_event_materiality(text)
    magnitude = get_magnitude_score(text)
    penalty = get_noise_penalty(text)
    raw = (
        event_weight * event
        + trust_weight * trust
        + ticker_weight * ticker
        + magnitude_weight * magnitude
        + recency_weight * recency
        - penalty
    )
    return round(max(0.0, min(raw, 1.0)), 3)


# ──────────────────────────────────────────────
# Materiality tiers
# ──────────────────────────────────────────────

TIER_HIGH_THRESHOLD = 0.85
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


def get_display_tier(item: dict, bucket: str) -> str:
    """Classify an item for the visible feed after source-quality gates.

    Raw scoring deliberately stays broad so we can audit the feed. The display
    tier is stricter: non-ANZ Medium items need both a trusted source and a
    thesis-relevant event; ANZ DC keeps a lower materiality bar but still blocks
    weak sources.
    """
    score = item.get("materiality_score", 0)
    tier = get_materiality_tier(score)
    if tier != "MEDIUM":
        return tier

    source_trust = get_source_trust(item.get("source", ""))
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    if bucket == "ANZ DC":
        has_material_marker = (
            get_event_materiality(text) > 0
            or get_magnitude_score(text) > 0
            or score >= 0.48
        )
        return tier if source_trust >= 0.70 and has_material_marker else "LOW"

    event = get_event_materiality(text)
    if source_trust < 0.70 or event < 1.0 or score < 0.78:
        return "LOW"
    return tier
