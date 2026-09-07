"""Vintage labels for AU DC views.

Reads the ``<output>.parquet.vintage.json`` sidecars that
``etl/au_dc/source_vintage.py`` writes next to every dated AU DC output, and
turns them into chart captions so a rebuilt file is never presented as
current source coverage (S2-08):

- the grid-capacity charts state which registration snapshot date / archive
  month the operating roster is captured as of;
- the actual-demand chart states the series is historical actuals, how far it
  extends, and which AEMO archive month supplied the newest row.

Every helper degrades gracefully: when a sidecar is absent (older datasets,
or files produced before vintage recording), captions fall back to what can
be derived from the data itself and the page never raises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

#: Mirrors etl/au_dc/source_vintage.py (kept intentionally tiny and duplicated
#: so app views never import ETL modules).
VINTAGE_SUFFIX = ".vintage.json"


def vintage_path_for(output_path: Path) -> Path:
    """Sibling sidecar path for a parquet output."""
    return Path(output_path).with_name(Path(output_path).name + VINTAGE_SUFFIX)


def read_vintage(data_path: Path) -> Dict[str, Any]:
    """Read an output's vintage sidecar; {} when absent or unreadable."""
    sidecar = vintage_path_for(data_path)
    try:
        if not sidecar.exists():
            return {}
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def registration_caption(vintage: Dict[str, Any], base_note: str) -> str:
    """Caption for grid-capacity charts: prefix with the registration snapshot.

    ``base_note`` is the existing AEMO/NEM caveat text. Returns it unchanged
    when no snapshot vintage is recorded.
    """
    snapshot = vintage.get("registration_snapshot")
    archive = vintage.get("archive_month")
    if snapshot:
        prefix = (
            f"Registration roster as of {snapshot} "
            f"(AEMO MMS monthly archive {archive or 'unknown'}). "
        )
        return prefix + base_note
    return base_note


def demand_caption(
    vintage: Dict[str, Any],
    data_through: Optional[str],
) -> str:
    """Caption for the actual-NEM-demand chart.

    Always states the series holds historical actuals (never projections) and,
    when known, how far it extends and which archive month supplied the newest
    row. Falls back to the bare source note when even the data end is unknown.
    """
    base = (
        "Source: AEMO DISPATCHREGIONSUM via NEMOSIS — 5-minute dispatch data "
        "aggregated to monthly averages. Values are historical actuals; the "
        "series never projects future demand."
    )
    if not data_through:
        return base
    archive = vintage.get("archive_month")
    if archive:
        return f"{base} Series extends through {data_through} (AEMO MMS monthly archive {archive})."
    return f"{base} Series extends through {data_through}."
