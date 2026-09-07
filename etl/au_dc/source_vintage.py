"""Source-vintage sidecars for AU DC parquet outputs.

The S2-08 finding: rebuilding processed files does not advance source
coverage (the AU ETL could rewrite ``generation_info.parquet`` every run from
a registration archive frozen at 2026-01, and freshness checks that read file
mtime would green-light it). Every AU DC output produced from a dated AEMO
source therefore gets a small ``<output>.parquet.vintage.json`` sidecar that
records *what source vintage actually produced the file*:

- registration outputs (``generation_info.parquet``, ``grid_capacity.parquet``):
  the archive month + the as-of snapshot date for the registration roster, and
  (separately) the identity of the manually downloaded AEMO Generation
  Information workbook that supplied pipeline rows;
- the demand output (``nem_demand_actual.parquet``): which archive months the
  series actually extends through and how the file was produced
  (incremental vs full backfill).

Sidecar contents are content-derived only — no run timestamps — so an
unchanged dataset produces an unchanged sidecar ("no new release ⇒ no false
freshness advance" is true at the file level too). The app reads the sidecars
to label the charts with their true vintage; when a sidecar is absent the app
falls back to deriving what it can from the data itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

#: Sidecar naming: ``nem_demand_actual.parquet`` -> ``nem_demand_actual.parquet.vintage.json``
VINTAGE_SUFFIX = ".vintage.json"


def vintage_path_for(output_path: Path) -> Path:
    """Sibling sidecar path for a parquet output."""
    return output_path.with_name(output_path.name + VINTAGE_SUFFIX)


def write_parquet_with_vintage(
    df: pd.DataFrame,
    out_path: Path,
    vintage: Dict[str, Any],
) -> Path:
    """Write ``df`` to ``out_path`` plus its vintage sidecar (atomic-ish).

    The sidecar is only rewritten when its content actually changes, so a run
    that reproduces the same dataset leaves the sidecar byte-identical.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    sidecar = vintage_path_for(out_path)
    payload = json.dumps(vintage, sort_keys=True, indent=2, default=str) + "\n"
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8") != payload:
        sidecar.write_text(payload, encoding="utf-8")
    return sidecar


def read_vintage(output_path: Path) -> Dict[str, Any]:
    """Read an output's vintage sidecar; {} when absent or unreadable.

    Never raises — views must render fine on datasets without sidecars.
    """
    sidecar = vintage_path_for(Path(output_path))
    try:
        if not sidecar.exists():
            return {}
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def vintage_dict(
    output_name: str,
    *,
    source_tables: list,
    source: str = "AEMO NEMWEB MMSDM monthly archives via NEMOSIS",
    extra: Optional[Dict[str, Any]] = None,
    row_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a canonical vintage sidecar dict (schema_version 1)."""
    payload: Dict[str, Any] = {
        "schema_version": 1,
        "output": output_name,
        "source_tables": source_tables,
        "source": source,
    }
    if extra:
        payload.update(extra)
    if row_count is not None:
        payload["row_count"] = int(row_count)
    return payload
