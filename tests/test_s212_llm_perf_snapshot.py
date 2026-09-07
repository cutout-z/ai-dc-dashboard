"""S2-12 (C14) verification: benchmark snapshots serve actual readers.

Review reproductions (astra-review-2026-09-04 S2-12):
- seven active LLM views called live `fetch_zeroeval_models()`, returning EMPTY
  on failure instead of using committed outputs; an offline fixture showed zero
  models despite an existing committed snapshot;
- the reader separately needs TrueSkill indexes, while publishers stored reduced
  model fields (top-30 composite) and a different format — blind fallback to
  llm_leaderboard.json could not repair the schema/ranking mismatch;
- `fetch_llm_benchmarks.py` labelled a benchmark mean as "Arena Elo" (fabricated
  ranking identity) and wrote SQLite tables nothing active read.

After the fix (verify criteria):
- refresh produces ONE source-faithful full-field model snapshot
  (data/reference/llm_leaderboard.json) + separately identified TrueSkill index
  data (data/reference/llm_indexes.json), both schema-validated BEFORE write;
- readers default to the validated committed snapshot with a visible as-of;
  network/credentials unavailable -> retained pages still show committed
  evidence with its date (AppTest covered by the offline render check below);
- missing indexes show unavailable — never fabricated ranks, never an empty
  otherwise-valid leaderboard;
- a schema-change fixture fails validation before publication;
- the publisher never stores a rank/composite/Elo field in the model snapshot.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys_path = str(REPO)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from app.lib import llm_snapshot  # noqa: E402


# ────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ────────────────────────────────────────────────────────────────────────────
def _model_row(i: int) -> dict:
    """A minimal but fully contract-shaped model row (all reader keys present)."""
    row: dict = {}
    for key in llm_snapshot.REQUIRED_MODEL_KEYS:
        if key in ("name", "model_id", "canonical_model_id", "organization",
                   "organization_country", "organization_id"):
            row[key] = f"model-{key}-{i}"
        elif key == "name":
            row[key] = f"Test Model {i}"
        elif key in ("license",):
            row[key] = "proprietary"
        elif key in ("release_date", "announcement_date", "knowledge_cutoff"):
            row[key] = "2026-01-15"
        elif key in ("is_moe", "multimodal"):
            row[key] = False
        elif key.endswith("_score"):
            row[key] = 0.7
        elif key in ("context", "training_tokens", "params", "throughput", "latency"):
            row[key] = 128000
        else:
            row[key] = 1.5
    row["name"] = f"Test Model {i}"
    row["model_id"] = f"test-model-{i}"
    return row


def _model_rows(n: int = 6) -> list[dict]:
    return [_model_row(i) for i in range(n)]


def _index_info(cat: str, ids: list[str], conservative: list[float]) -> dict:
    return {
        "category_id": cat,
        "method": "trueskill",
        "methodology": "Bayesian skill rating",
        "games": 8,
        "models": [
            {"model_id": mid, "model_name": mid, "organization_id": "org",
             "organization_name": "Org", "mu": c + 3.0, "sigma": 1.0,
             "conservative": c, "rank": r + 1, "games_played": 5,
             "games_available": 8, "coverage_ratio": 0.62, "global_prior": 0.0}
            for r, (mid, c) in enumerate(zip(ids, conservative))
        ],
    }


# ────────────────────────────────────────────────────────────────────────────
# 1. Payload validation — the schema-change gate
# ────────────────────────────────────────────────────────────────────────────
def test_valid_models_payload_passes():
    payload = llm_snapshot.build_models_payload(_model_rows())
    assert llm_snapshot.validate_models_payload(payload) == []
    # json round-trip (what the file actually stores) still validates
    again = json.loads(json.dumps(payload))
    assert llm_snapshot.validate_models_payload(again) == []
    assert again["_meta"]["model_count"] == 6


def test_schema_change_dropped_reader_key_fails_before_publish():
    rows = _model_rows(3)
    del rows[0]["params"]          # prices_and_value reads params
    payload = llm_snapshot.build_models_payload(rows)
    errors = llm_snapshot.validate_models_payload(payload)
    assert errors and any("params" in e for e in errors), errors


def test_schema_change_renamed_score_fails_before_publish():
    rows = _model_rows(3)
    rows[0]["gpqa_score_renamed"] = rows[0].pop("gpqa_score")
    errors = llm_snapshot.validate_models_payload(llm_snapshot.build_models_payload(rows))
    assert errors and any("gpqa_score" in e for e in errors), errors


def test_forbidden_derived_rank_key_rejected():
    rows = _model_rows(3)
    rows[1]["rank"] = 2            # publisher must never store a rank
    errors = llm_snapshot.validate_models_payload(llm_snapshot.build_models_payload(rows))
    assert errors and any("forbidden derived key" in e and "rank" in e for e in errors), errors


def test_empty_models_rejected():
    errors = llm_snapshot.validate_models_payload(llm_snapshot.build_models_payload([]))
    assert errors and any("empty" in e for e in errors), errors


def test_non_numeric_score_rejected():
    rows = _model_rows(2)
    rows[0]["gpqa_score"] = "high"
    errors = llm_snapshot.validate_models_payload(llm_snapshot.build_models_payload(rows))
    assert errors and any("gpqa_score" in e and "numeric" in e for e in errors), errors


def test_duplicate_model_id_rejected():
    rows = _model_rows(2)
    rows[1]["model_id"] = rows[0]["model_id"]
    errors = llm_snapshot.validate_models_payload(llm_snapshot.build_models_payload(rows))
    assert errors and any("duplicated" in e for e in errors), errors


def test_meta_model_count_mismatch_rejected():
    payload = llm_snapshot.build_models_payload(_model_rows(4))
    payload["_meta"]["model_count"] = 99
    errors = llm_snapshot.validate_models_payload(payload)
    assert errors and any("model_count" in e for e in errors), errors


def test_indexes_payload_valid():
    payload = llm_snapshot.build_indexes_payload(
        {"reasoning": _index_info("reasoning", ["a", "b"], [40.0, 38.0]),
         "math": _index_info("math", ["a"], [39.5])}
    )
    assert llm_snapshot.validate_indexes_payload(payload) == []
    assert payload["_meta"]["index_count"] == 2
    assert payload["_meta"]["model_entry_count"] == 3
    # per-category method preserved verbatim
    assert payload["indexes"]["reasoning"]["method"] == "trueskill"


def test_indexes_projection_drops_heavy_unused_fields():
    info = _index_info("reasoning", ["a"], [40.0])
    info["models"][0]["ci_lower"] = 38.0
    info["models"][0]["ci_upper"] = 42.0
    info["models"][0]["benchmark_results"] = [{"bench": "gpqa", "value": 0.9}]
    payload = llm_snapshot.build_indexes_payload({"reasoning": info})
    row = payload["indexes"]["reasoning"]["models"][0]
    assert set(row.keys()) == set(llm_snapshot.INDEX_ROW_KEYS)
    assert llm_snapshot.validate_indexes_payload(payload) == []


def test_indexes_duplicate_model_id_rejected():
    info = _index_info("reasoning", ["a", "a"], [40.0, 38.0])
    errors = llm_snapshot.validate_indexes_payload(
        llm_snapshot.build_indexes_payload({"reasoning": info}))
    assert errors and any("duplicated" in e for e in errors), errors


def test_indexes_missing_category_meta_rejected():
    payload = llm_snapshot.build_indexes_payload({"reasoning": _index_info("reasoning", ["a"], [40.0])})
    del payload["indexes"]["reasoning"]["method"]
    errors = llm_snapshot.validate_indexes_payload(payload)
    assert errors and any("method" in e for e in errors), errors


# ────────────────────────────────────────────────────────────────────────────
# 2. Loaders — fail loudly, never a silent empty frame
# ────────────────────────────────────────────────────────────────────────────
def test_loader_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        llm_snapshot.load_models_payload(tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError):
        llm_snapshot.load_indexes_payload(tmp_path / "nope.json")


def test_loader_invalid_payload_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"models": [], "_meta": {"updated": "2026-09-07"}}))
    with pytest.raises(llm_snapshot.ContractError):
        llm_snapshot.load_models_payload(p)


def test_loader_valid_roundtrip(tmp_path):
    p = tmp_path / "llm_leaderboard.json"
    p.write_text(json.dumps(llm_snapshot.build_models_payload(_model_rows(5))))
    payload = llm_snapshot.load_models_payload(p)
    assert len(payload["models"]) == 5
    ip = tmp_path / "llm_indexes.json"
    ip.write_text(json.dumps(llm_snapshot.build_indexes_payload(
        {"reasoning": _index_info("reasoning", ["a"], [40.0])})))
    assert llm_snapshot.load_indexes_payload(ip)["_meta"]["index_count"] == 1


# ────────────────────────────────────────────────────────────────────────────
# 3. Ordering — missing indexes never empty / fake a leaderboard
# ────────────────────────────────────────────────────────────────────────────
def _models_frame() -> pd.DataFrame:
    rows = [
        {"model_id": "m1", "name": "M1", "organization": "A", "release_date": "2026-01-01",
         "gpqa_score": 0.90, "swe_bench_verified_score": 0.80, "hle_score": 0.70,
         "aime_2025_score": 0.60},
        {"model_id": "m2", "name": "M2", "organization": "B", "release_date": "2026-02-01",
         "gpqa_score": 0.80, "swe_bench_verified_score": 0.70, "hle_score": 0.60,
         "aime_2025_score": 0.50},
        {"model_id": "m3", "name": "M3", "organization": "A", "release_date": "2026-03-01",
         "gpqa_score": None, "swe_bench_verified_score": None, "hle_score": None,
         "aime_2025_score": None},
    ]
    return pd.DataFrame(rows)


def _index_frame(model_conservative: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame([
        {"model_id": mid, "conservative": c} for mid, c in model_conservative.items()
    ])


def test_reasoning_index_present_sorts_by_it_and_drops_unrated():
    df = _models_frame()
    frames = {"reasoning": _index_frame({"m2": 41.0, "m1": 40.0})}
    ordered, key, missing = llm_snapshot.leaderboard_order(
        df, frames, ["reasoning", "math"], primary="reasoning")
    assert key == "reasoning_index"
    assert list(ordered["model_id"]) == ["m2", "m1"]   # desc by conservative
    assert "m3" not in ordered["model_id"].tolist()    # no published rating -> excluded
    assert missing == ["math"]


def test_missing_indexes_fall_back_to_benchmark_mean_not_empty():
    df = _models_frame()
    ordered, key, missing = llm_snapshot.leaderboard_order(df, {}, ["reasoning", "math"])
    assert key == "benchmark_mean"
    assert missing == ["reasoning", "math"]
    assert len(ordered) == 3                       # all models retained
    assert "benchmark_mean" in ordered.columns
    assert ordered.loc[0, "model_id"] == "m1"      # highest mean (0.75*100)
    assert pd.isna(ordered.loc[2, "benchmark_mean"])  # no-score model last, not dropped


def test_non_overlapping_index_is_treated_unavailable_not_fabricated():
    df = _models_frame()
    frames = {"reasoning": _index_frame({"ghost": 99.0})}   # no model_id overlap
    ordered, key, missing = llm_snapshot.leaderboard_order(df, frames, ["reasoning"])
    assert key == "benchmark_mean"                 # index unusable -> honest fallback
    assert len(ordered) == 3                       # never an empty leaderboard


def test_partial_indexes_only_present_cats_merge():
    df = _models_frame()
    frames = {"math": _index_frame({"m1": 42.0})}
    merged, present, missing = llm_snapshot.merge_index_columns(
        df, frames, ["reasoning", "math"])
    assert present == ["math"]
    assert missing == ["reasoning"]
    assert merged["idx_math"].notna().any()
    assert merged["idx_reasoning"].isna().all()    # missing cat column all-null, callers hide it


# ────────────────────────────────────────────────────────────────────────────
# 4. Committed artifacts — the repo carries valid source-faithful evidence
# ────────────────────────────────────────────────────────────────────────────
def test_committed_models_snapshot_valid_and_full_field():
    payload = llm_snapshot.load_models_payload()      # raises if invalid
    assert payload["_meta"]["schema_version"] == llm_snapshot.MODELS_SCHEMA_VERSION
    assert payload["_meta"]["model_count"] == len(payload["models"])
    assert payload["_meta"]["model_count"] > 100      # full universe, not a top-30 slice
    for row in payload["models"]:
        assert set(llm_snapshot.REQUIRED_MODEL_KEYS) <= set(row.keys())
        assert not (set(row) & llm_snapshot.FORBIDDEN_MODEL_KEYS)  # no offline ranks
    assert any("training_tokens" in r for r in payload["models"])  # verbatim full field


def test_committed_indexes_snapshot_valid():
    payload = llm_snapshot.load_indexes_payload()
    assert payload["_meta"]["schema_version"] == llm_snapshot.INDEXES_SCHEMA_VERSION
    assert payload["_meta"]["index_count"] == len(payload["indexes"])
    for cat in ("reasoning", "math", "coding", "agents", "search", "knowledge"):
        assert cat in payload["indexes"], f"{cat} index missing from committed artifact"
    assert all(
        info.get("method") == "trueskill"
        for info in payload["indexes"].values()
        if isinstance(info, dict)
    )


def test_committed_artifacts_share_asof_date():
    models = llm_snapshot.load_models_payload()
    indexes = llm_snapshot.load_indexes_payload()
    assert models["_meta"]["updated"] == indexes["_meta"]["updated"]


# ────────────────────────────────────────────────────────────────────────────
# 5. Same-snapshot outputs agree with live transformation semantics
# ────────────────────────────────────────────────────────────────────────────
def test_preprocess_on_snapshot_matches_direct_frame_semantics():
    st_mod = pytest.importorskip("streamlit")   # llm_perf imports streamlit
    from app.lib.llm_perf import preprocess_ze  # noqa: PLC0415

    payload = llm_snapshot.load_models_payload()
    # live path: pd.DataFrame(resp.json()); snapshot path: stored verbatim rows
    direct = pd.DataFrame(payload["models"])
    stored = pd.DataFrame(llm_snapshot.models_to_frame(payload["models"]))
    assert direct.equals(stored)
    df_a, specs_a = preprocess_ze(direct)
    df_b, specs_b = preprocess_ze(stored)
    assert not df_a.empty and not specs_a.empty
    pd.testing.assert_frame_equal(df_a, df_b)
    pd.testing.assert_frame_equal(specs_a, specs_b)
    # derived columns the pages rely on exist and are sane
    for col in ("release_date", "quarter", "provider", "is_open", "country", "blended_price"):
        assert col in df_a.columns


def test_no_fabricated_rank_material_in_views_or_pipeline():
    llm_perf = (REPO / "app" / "lib" / "llm_perf.py").read_text()
    assert "load_arena_elo" not in llm_perf
    assert "sqlite3" not in llm_perf
    assert "llm_arena_elo" not in llm_perf
    assert not (REPO / "scripts" / "fetch_llm_benchmarks.py").exists()
    wrapper = (REPO / "deploy" / "run-vps-etl.sh").read_text()
    assert "fetch_llm_benchmarks" not in wrapper
    assert "refresh_llm_leaderboard.py" in wrapper
    # active pages default to committed evidence with a visible as-of
    leaderboard = (REPO / "app" / "views" / "fundamentals" / "llm_performance" / "leaderboard.py").read_text()
    assert "llm_data_status()" in leaderboard
    assert "order_leaderboard" in leaderboard
    assert "updated hourly" not in leaderboard
    for page in ("open_models", "benchmark_performance", "prices_and_value",
                 "speed_and_context", "labs_and_countries", "efficiency_and_scale"):
        text = (REPO / "app" / "views" / "fundamentals" / "llm_performance" / f"{page}.py").read_text()
        assert "llm_data_status()" in text, f"{page} lacks as-of caption"
        assert "Live data unavailable" not in text, f"{page} still claims live-only data"
    # source-health inventory tracks the new index artifact and no longer lists
    # the removed fabricated-Elo SQLite tables
    report = (REPO / "scripts" / "source_health_report.py").read_text()
    assert '"name": "llm_indexes.json"' in report
    view = (REPO / "app" / "views" / "system" / "source_health.py").read_text()
    assert "llm_arena_elo" not in view and "llm_model_specs" not in view
    assert "llm_indexes.json" in view


def test_refresh_script_is_single_producer_with_gate(tmp_path, monkeypatch):
    """refresh_llm_leaderboard refuses to write on contract failure (exit 2)."""
    import sys as _sys

    script = REPO / "scripts" / "refresh_llm_leaderboard.py"
    assert script.exists()

    # Deterministic gate check without network: monkeypatch module internals.
    sys_path_inserted = str(REPO)
    if sys_path_inserted not in _sys.path:
        _sys.path.insert(0, sys_path_inserted)
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("refresh_llm_leaderboard", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # top-level defines requests/main/paths
    monkeypatch.setattr(mod, "MODELS_OUT", tmp_path / "llm_leaderboard.json")
    monkeypatch.setattr(mod, "INDEXES_OUT", tmp_path / "llm_indexes.json")

    valid_indexes = {"reasoning": _index_info("reasoning", ["a"], [40.0])}

    class _Resp:
        def __init__(self, obj):
            self._obj = obj

        def raise_for_status(self):
            pass

        def json(self):
            return self._obj

    def _fake_get(url, **kwargs):
        if "models/full" in url:
            return _Resp(_model_rows(3))
        return _Resp(valid_indexes)

    # valid response -> writes both files, exit 0
    monkeypatch.setattr(mod.requests, "get", _fake_get)
    monkeypatch.setattr(mod, "_atomic_write",
                        lambda p, text: p.write_text(text))
    rc = mod.main()
    assert rc == 0
    assert (tmp_path / "llm_leaderboard.json").exists()
    assert (tmp_path / "llm_indexes.json").exists()

    # schema-change models response (dropped reader key) -> exit 2, nothing written
    before_models = (tmp_path / "llm_leaderboard.json").read_bytes()
    before_indexes = (tmp_path / "llm_indexes.json").read_bytes()

    def _bad_models_get(url, **kwargs):
        if "models/full" in url:
            rows = _model_rows(3)
            del rows[0]["context"]
            return _Resp(rows)
        return _Resp(valid_indexes)

    monkeypatch.setattr(mod.requests, "get", _bad_models_get)
    rc = mod.main()
    assert rc == 2
    assert (tmp_path / "llm_leaderboard.json").read_bytes() == before_models
    assert (tmp_path / "llm_indexes.json").read_bytes() == before_indexes
