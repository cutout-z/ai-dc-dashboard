"""Shared run-result contract for ETL/producer scripts (Astra S2-04).

Every producer reports an explicit outcome so downstream health surfaces can
distinguish success, partial success, deliberate skips and hard failure:

    ok        — all attempted sources succeeded with observations
    degraded  — some attempted sources failed; usable observations published
    error     — no usable observations / required inputs missing; any
                previously-published output is preserved untouched
    skipped   — nothing attempted by design (e.g. dry run)

Counts follow fetch/lookup attempts, not items: ``attempted`` is how many
external sources were tried, ``succeeded`` how many returned observations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def final_status(succeeded: int, attempted: int) -> str:
    """ok / degraded / error from attempt counts (attempted == 0 -> error)."""
    if attempted <= 0 or succeeded <= 0:
        return "error"
    if succeeded < attempted:
        return "degraded"
    return "ok"


def read_log_record(log_path: Path, script: str) -> dict:
    """Read one script's previous structured record (empty dict if absent)."""
    try:
        import json

        log = json.loads(log_path.read_text())
        record = log.get(script)
        return record if isinstance(record, dict) else {}
    except Exception:
        return {}


def write_log_record(
    log_path: Path,
    script: str,
    *,
    status: str,
    attempted: int | None = None,
    succeeded: int | None = None,
    observations: int | None = None,
    notes: str = "",
    count: int | None = None,
) -> None:
    """Upsert one script's record preserving last_attempt/last_success history.

    - ``last_attempt`` is always advanced (a failed attempt is still an attempt).
    - ``last_success`` only advances on ok/degraded runs and is otherwise
      preserved from the previous record, so staleness stays visible.
    - Legacy ``last_run``/``count``/``notes`` keys are kept in sync so older
      readers (VPS-era) still render.
    """
    import json

    now = now_iso()
    previous = read_log_record(log_path, script)
    record: dict = {
        "last_attempt": now,
        "last_run": now,  # legacy key, same instant
        "status": status,
    }
    if attempted is not None:
        record["attempted"] = attempted
    if succeeded is not None:
        record["succeeded"] = succeeded
    if observations is not None:
        record["observations"] = observations
    if count is not None:
        record["count"] = count
    record["notes"] = notes
    if status in {"ok", "degraded"}:
        record["last_success"] = now
    elif previous.get("last_success"):
        record["last_success"] = previous["last_success"]

    try:
        log = json.loads(log_path.read_text()) if log_path.exists() else {}
        if not isinstance(log, dict):
            log = {}
    except Exception:
        log = {}
    log[script] = record
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
