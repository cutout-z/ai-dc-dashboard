"""Shared LLM-benchmark snapshot contract (Astra S2-12 / C14).

One producer — ``scripts/refresh_llm_leaderboard.py`` — writes two committed,
schema-validated artifacts under ``data/reference/``:

  llm_leaderboard.json  — source-faithful FULL-FIELD model snapshot. Every model
                          row returned by api.zeroeval.com/leaderboard/models/full
                          (``justCanonicals=true``) is stored verbatim under
                          ``models``, with ``_meta`` recording source/fetch time.
                          No rank, composite or "Elo"-style field is ever added by
                          the publisher: any score/ranking shown by readers is
                          derived at read time from the published fields, or read
                          from the separate index artifact.
  llm_indexes.json      — ZeroEval TrueSkill index data, separately identified
                          from the model snapshot. Per-category verbatim rows
                          (model_id, mu, sigma, conservative, rank, ...) under
                          ``indexes``, with category meta (method/methodology).

Readers (``app/lib/llm_perf.py``) default to these committed snapshots and only
ever show a rank from published index values — never an offline fabrication.
Validation in this module is the shared gate: it fails a schema-change fixture
BEFORE publication and makes loaders fail loudly (never a silent empty frame)
when a committed artifact is missing or malformed.

The module is intentionally free of Streamlit imports so both the producer
scripts and the app views share it.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _REPO_ROOT / "data" / "reference"

MODELS_FILE_NAME = "llm_leaderboard.json"
INDEXES_FILE_NAME = "llm_indexes.json"

MODELS_SOURCE_URL = "https://api.zeroeval.com/leaderboard/models/full"
INDEXES_SOURCE_URL = "https://api.zeroeval.com/leaderboard/indexes/all"

MODELS_SCHEMA_VERSION = 2
INDEXES_SCHEMA_VERSION = 1

# Reader contract: every key the active LLM views / preprocessors read from the
# model snapshot. The endpoint may add fields freely (snapshot stores them
# verbatim), but if a future API change ever drops one of these, the refresh
# fails BEFORE publication so a reader never silently loses a column.
REQUIRED_MODEL_KEYS: list[str] = [
    "aime_2025_score", "announcement_date", "apex_agents_score", "arc_agi_v2_score",
    "browsecomp_score", "canonical_model_id", "charxiv_r_score", "context",
    "frontiermath_score", "gpqa_score", "hle_score", "input_price", "is_moe",
    "knowledge_cutoff", "latency", "license", "mcp_atlas_score", "mmmlu_score",
    "mmmu_pro_score", "mmmu_score", "model_id", "mrcr_v2_score", "multimodal",
    "name", "organization", "organization_country", "organization_id",
    "osworld_score", "output_price", "params", "release_date", "scicode_score",
    "screenspot_pro_score", "simpleqa_score", "swe_bench_pro_score",
    "swe_bench_verified_score", "tau_bench_retail_score", "terminal_bench_score",
    "throughput", "toolathlon_score", "training_tokens",
]

# Derived rank-like keys must never appear in the stored model snapshot rows:
# offline-published ranks are exactly what S2-12 forbids. If the upstream API
# ever adds a rank of its own the refresh fails loudly and the contract gets an
# explicit decision rather than a silent new field.
FORBIDDEN_MODEL_KEYS: set[str] = {
    "rank", "elo", "arena_elo", "composite", "composite_score",
}

REQUIRED_MODEL_META_KEYS: set[str] = {
    "schema_version", "source", "fetched_at", "updated", "model_count",
}
REQUIRED_INDEX_META_KEYS: set[str] = {
    "schema_version", "source", "fetched_at", "updated", "index_count",
}

# Headline benchmarks used for an explicitly-labelled offline sort fallback
# (never presented as a TrueSkill / Elo rank).
BENCH_MEAN_COLS: list[str] = [
    "gpqa_score", "swe_bench_verified_score", "hle_score", "aime_2025_score",
]

# Per-model fields retained in the index artifact. Values are verbatim ZeroEval
# TrueSkill outputs; heavy per-model detail arrays used by no reader
# (benchmark_results, ci_*) are intentionally not retained — the projection is
# documented in the artifact's _meta.note.
INDEX_ROW_KEYS: list[str] = [
    "model_id", "model_name", "organization_id", "organization_name",
    "mu", "sigma", "conservative", "rank",
    "games_played", "games_available", "coverage_ratio", "global_prior",
]
INDEX_CAT_META_KEYS: list[str] = ["category_id", "method", "methodology", "games"]


class ContractError(ValueError):
    """A snapshot payload violates the shared contract.

    The message enumerates every violation found, so a schema drift is
    actionable rather than a bare assertion.
    """


# ────────────────────────────────────────────────────────────────────────────
# Path helpers
# ────────────────────────────────────────────────────────────────────────────
def models_path(data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / MODELS_FILE_NAME


def indexes_path(data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / INDEXES_FILE_NAME


# ────────────────────────────────────────────────────────────────────────────
# Validation (shared producer gate + reader loader gate)
# ────────────────────────────────────────────────────────────────────────────
def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _errors_for_meta(meta: Any, required: set[str], which: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(meta, dict):
        return [f"{which}._meta must be a dict, got {type(meta).__name__}"]
    for key in required:
        if key not in meta:
            errors.append(f"{which}._meta missing required key {key!r}")
    if "updated" in meta:
        try:
            datetime.fromisoformat(str(meta["updated"]))
        except ValueError:
            errors.append(f"{which}._meta.updated {meta['updated']!r} is not ISO-date parseable")
    if "fetched_at" in meta:
        if not isinstance(meta["fetched_at"], str) or "T" not in meta["fetched_at"]:
            errors.append(f"{which}._meta.fetched_at must be an ISO-8601 datetime string")
    return errors


def validate_models_payload(obj: Any) -> list[str]:
    """Return a list of contract violations for a models snapshot payload.

    Empty list == valid. Never raises.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return [f"models payload must be a dict, got {type(obj).__name__}"]
    errors += _errors_for_meta(obj.get("_meta"), REQUIRED_MODEL_META_KEYS, "models")
    if "_meta" in obj and isinstance(obj["_meta"], dict):
        if obj["_meta"].get("schema_version") != MODELS_SCHEMA_VERSION:
            errors.append(
                f"models._meta.schema_version must be {MODELS_SCHEMA_VERSION}, "
                f"got {obj['_meta'].get('schema_version')!r}"
            )
        if "source" in obj["_meta"] and not str(obj["_meta"]["source"]).startswith("http"):
            errors.append(f"models._meta.source {obj['_meta']['source']!r} is not a URL")

    models = obj.get("models")
    if not isinstance(models, list):
        return errors + [f"models.models must be a list, got {type(models).__name__}"]
    if not models:
        errors.append("models.models is empty — a model snapshot with zero rows is invalid")
    seen_ids: set[str] = set()
    for i, row in enumerate(models):
        prefix = f"models.models[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be a dict, got {type(row).__name__}")
            continue
        for key in REQUIRED_MODEL_KEYS:
            if key not in row:
                errors.append(f"{prefix} missing required key {key!r}")
        for key in FORBIDDEN_MODEL_KEYS:
            if key in row:
                errors.append(f"{prefix} carries forbidden derived key {key!r} — "
                              "the publisher never stores ranks/composites")
        for key in ("name", "model_id", "organization"):
            val = row.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
        mid = row.get("model_id")
        if isinstance(mid, str) and mid in seen_ids:
            errors.append(f"{prefix}.model_id {mid!r} duplicated")
        if isinstance(mid, str):
            seen_ids.add(mid)
        for key in row:
            val = row[key]
            if val is None or isinstance(val, str) or isinstance(val, bool):
                continue
            if not _is_num(val):
                errors.append(f"{prefix}.{key} has non-scalar value {type(val).__name__}")
        for key in row:
            if key.endswith("_score") and row[key] is not None and not _is_num(row[key]):
                errors.append(f"{prefix}.{key} must be numeric or null, got {type(row[key]).__name__}")
    meta = obj.get("_meta")
    if isinstance(meta, dict) and isinstance(models, list):
        mc = meta.get("model_count")
        if mc is not None and mc != len(models):
            errors.append(f"models._meta.model_count {mc} != models.models length {len(models)}")
    return errors


def validate_indexes_payload(obj: Any) -> list[str]:
    """Return contract violations for an indexes snapshot payload."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return [f"indexes payload must be a dict, got {type(obj).__name__}"]
    errors += _errors_for_meta(obj.get("_meta"), REQUIRED_INDEX_META_KEYS, "indexes")
    if "_meta" in obj and isinstance(obj["_meta"], dict):
        if obj["_meta"].get("schema_version") != INDEXES_SCHEMA_VERSION:
            errors.append(
                f"indexes._meta.schema_version must be {INDEXES_SCHEMA_VERSION}, "
                f"got {obj['_meta'].get('schema_version')!r}"
            )
    idx = obj.get("indexes")
    if not isinstance(idx, dict):
        return errors + [f"indexes.indexes must be a dict, got {type(idx).__name__}"]
    if not idx:
        errors.append("indexes.indexes is empty")
    for cat, info in idx.items():
        prefix = f"indexes.indexes[{cat!r}]"
        if not isinstance(info, dict):
            errors.append(f"{prefix} must be a dict, got {type(info).__name__}")
            continue
        for key in INDEX_CAT_META_KEYS:
            if key not in info:
                errors.append(f"{prefix} missing {key!r}")
        rows = info.get("models")
        if not isinstance(rows, list):
            errors.append(f"{prefix}.models must be a list, got {type(rows).__name__}")
            continue
        seen: set[str] = set()
        for j, row in enumerate(rows):
            rp = f"{prefix}.models[{j}]"
            if not isinstance(row, dict):
                errors.append(f"{rp} must be a dict")
                continue
            for key in INDEX_ROW_KEYS:
                if key not in row:
                    errors.append(f"{rp} missing {key!r}")
            mid = row.get("model_id")
            if not isinstance(mid, str) or not mid.strip():
                errors.append(f"{rp}.model_id must be a non-empty string")
            elif mid in seen:
                errors.append(f"{rp}.model_id {mid!r} duplicated")
            else:
                seen.add(mid)
            for key in ("mu", "sigma", "conservative", "rank"):
                val = row.get(key)
                if val is not None and not _is_num(val):
                    errors.append(f"{rp}.{key} must be numeric or null, got {type(val).__name__}")
    meta = obj.get("_meta")
    if isinstance(meta, dict) and isinstance(idx, dict):
        mec = meta.get("model_entry_count")
        total = sum(len(info.get("models") or [])
                    for info in idx.values() if isinstance(info, dict) and isinstance(info.get("models"), list))
        if mec is not None and mec != total:
            errors.append(f"indexes._meta.model_entry_count {mec} != actual entry count {total}")
    return errors


def _require_valid(payload: Any, which: str) -> None:
    if which == "models":
        errors = validate_models_payload(payload)
    else:
        errors = validate_indexes_payload(payload)
    if errors:
        raise ContractError(f"{which} snapshot fails contract ({len(errors)} issue(s)):\n  - "
                            + "\n  - ".join(errors[:25]))


# ────────────────────────────────────────────────────────────────────────────
# Payload builders (producer side)
# ────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_models_payload(raw_rows: list[dict], fetched_at: str | None = None) -> dict:
    """Wrap verbatim endpoint rows + _meta into the models snapshot payload."""
    payload = {
        "_meta": {
            "schema_version": MODELS_SCHEMA_VERSION,
            "source": MODELS_SOURCE_URL,
            "endpoint_params": "justCanonicals=true",
            "fetched_at": fetched_at or _now_iso(),
            "updated": date.today().isoformat(),
            "model_count": len(raw_rows),
            "note": (
                "Source-faithful full-field snapshot: every canonical model row returned by "
                "the ZeroEval models/full endpoint, stored verbatim. No rank or composite is "
                "published here — readers derive displayed scores or read published TrueSkill "
                "index values from the sibling llm_indexes.json."
            ),
        },
        "models": raw_rows,
    }
    return payload


def build_indexes_payload(raw: dict, fetched_at: str | None = None) -> dict:
    """Project the /indexes/all response into the committed index artifact.

    Category meta and per-model TrueSkill values are copied verbatim; the heavy
    per-model detail arrays no reader uses (``benchmark_results``, ``ci_*``) are
    dropped, and the projection is documented in _meta.
    """
    indexes: dict[str, dict[str, Any]] = {}
    total_rows = 0
    for cat, info in raw.items():
        if not isinstance(info, dict):
            continue
        rows = info.get("models")
        if not isinstance(rows, list):
            continue
        projected_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            projected_rows.append({key: row.get(key) for key in INDEX_ROW_KEYS})
        cat_meta: dict[str, Any] = {key: info.get(key) for key in INDEX_CAT_META_KEYS}
        indexes[cat] = {**cat_meta, "models": projected_rows}
        total_rows += len(projected_rows)
    payload = {
        "_meta": {
            "schema_version": INDEXES_SCHEMA_VERSION,
            "source": INDEXES_SOURCE_URL,
            "fetched_at": fetched_at or _now_iso(),
            "updated": date.today().isoformat(),
            "index_count": len(indexes),
            "model_entry_count": total_rows,
            "note": (
                "ZeroEval TrueSkill index data (method: trueskill), separately identified from "
                "the model snapshot. Values (mu/sigma/conservative/rank) are copied verbatim from "
                "the API; per-model detail arrays no reader consumes (benchmark_results, ci_*) "
                "are not retained. Ranks shown by readers come from this artifact only."
            ),
        },
        "indexes": indexes,
    }
    return payload


# ────────────────────────────────────────────────────────────────────────────
# Loaders (reader side) — fail loudly, never a silent empty frame
# ────────────────────────────────────────────────────────────────────────────
def load_models_payload(path: Path | None = None) -> dict:
    """Read and validate the committed models snapshot.

    Raises FileNotFoundError when absent and ContractError when malformed.
    """
    p = path or models_path()
    payload = json.loads(p.read_text())
    _require_valid(payload, "models")
    return payload


def load_indexes_payload(path: Path | None = None) -> dict:
    """Read and validate the committed indexes snapshot."""
    p = path or indexes_path()
    payload = json.loads(p.read_text())
    _require_valid(payload, "indexes")
    return payload


# ────────────────────────────────────────────────────────────────────────────
# Reader-oriented frames & ordering helpers (pure pandas; no Streamlit)
# ────────────────────────────────────────────────────────────────────────────
def models_to_frame(models: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(models)


def indexes_to_frames(indexes: dict) -> dict[str, pd.DataFrame]:
    """Map the validated indexes payload to {category: DataFrame}.

    DataFrames carry the retained TrueSkill columns
    (model_id, mu, sigma, conservative, rank, ...).
    """
    result: dict[str, pd.DataFrame] = {}
    for cat, info in indexes.items():
        if isinstance(info, dict) and isinstance(info.get("models"), list):
            rows = [row for row in info["models"] if isinstance(row, dict)]
            if rows:
                result[cat] = pd.DataFrame(rows)
    return result


def merge_index_columns(
    models_df: pd.DataFrame,
    index_frames: dict[str, pd.DataFrame],
    index_cats: list[str],
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Left-merge per-category conservative ratings onto the model frame.

    Returns ``(df, cats_present, cats_missing)`` where present means the
    category exists AND the merge yielded at least one non-null rating.
    """
    df = models_df.copy()
    present: list[str] = []
    missing: list[str] = []
    for cat in index_cats:
        col = f"idx_{cat}"
        merged = False
        if cat in index_frames and not index_frames[cat].empty:
            sub = index_frames[cat][["model_id", "conservative"]].rename(
                columns={"conservative": col}
            )
            df = df.merge(sub, on="model_id", how="left")
            if df[col].notna().any():
                present.append(cat)
                merged = True
        if not merged:
            if col not in df.columns:
                df[col] = None
            missing.append(cat)
    return df, present, missing


def leaderboard_order(
    models_df: pd.DataFrame,
    index_frames: dict[str, pd.DataFrame],
    index_cats: list[str] | None = None,
    primary: str = "reasoning",
) -> tuple[pd.DataFrame, str, list[str]]:
    """Order the leaderboard model frame for display.

    Sort key semantics (never a fabricated rank):
      * ``reasoning_index`` — sorted by the published ZeroEval TrueSkill
        reasoning index (primary when that index has data); models without a
        published reasoning rating are excluded, as before.
      * ``benchmark_mean`` — honest fallback when the reasoning index is
        unavailable offline: mean of the four headline published benchmark
        scores, labelled as such by the caller. No model is dropped and no
        TrueSkill/Elo claim is made.

    Returns ``(ordered_df, sort_key, missing_cats)``.
    """
    cats = list(index_cats or [])
    if primary not in cats:
        cats = [primary, *[c for c in cats if c != primary]]
    df, present, missing = merge_index_columns(models_df, index_frames, cats)
    if primary in present and df[f"idx_{primary}"].notna().any():
        ordered = (
            df.dropna(subset=[f"idx_{primary}"])
            .sort_values(f"idx_{primary}", ascending=False)
            .reset_index(drop=True)
        )
        return ordered, "reasoning_index", missing
    df["benchmark_mean"] = df[BENCH_MEAN_COLS].mean(axis=1, skipna=True).mul(100)
    ordered = (
        df.sort_values("benchmark_mean", ascending=False, na_position="last")
        .reset_index(drop=True)
    )
    return ordered, "benchmark_mean", missing
