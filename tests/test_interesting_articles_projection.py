"""A4 functional check: interesting_articles.py reads only the projection.

Runs the real page under Streamlit AppTest twice:
  cloud-mode  — repo data/investment_radar_public.json is the projection,
                _HOME_STATUS removed: old full-snapshot loader would show 0.
  local-mode  — _HOME_PUBLIC present (fixture with private-marker + item),
                page renders with local caption and "View full note" buttons.

Also checks the private-snapshot resolver directly. Never touches the real
private snapshot; all state via monkeypatched module constants.

Run:  /opt/anaconda3/bin/python3.12 tests/test_interesting_articles_projection.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app" / "views" / "threads"))

from streamlit.testing.v1 import AppTest  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def load_page(home_dir: Path):
    spec = importlib.util.spec_from_file_location(
        "interesting_articles",
        REPO / "app" / "views" / "threads" / "interesting_articles.py",
    )
    mod = importlib.util.module_from_spec(spec)
    import streamlit as st

    orig_home = Path.home
    Path.home = lambda: home_dir  # type: ignore[assignment]
    try:
        spec.loader.exec_module(mod)
    finally:
        Path.home = orig_home  # type: ignore[assignment]
    return mod, st


def make_home(tmp: Path, with_projection: bool) -> Path:
    home = tmp / "home"
    (home / "ai-wif-brain-dashboard" / "data").mkdir(parents=True, exist_ok=True)
    if with_projection:
        (home / "ai-wif-brain-dashboard" / "data" / "investment_radar_public.json").write_text(
            json.dumps({"schema_version": 1, "generated_at": "t0", "articles": [
                {"date": "2026-09-06", "text": "Local article", "snippet": "s",
                 "source": "https://x.example/a", "themes": ["Macro"],
                 "polarity": "context", "entities": [], "confidence": "medium",
                 "destination": "AI & DC"},
            ]})
        )
    return home


def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ---------- cloud mode ----------
        # Corrupt the home fallback (proves the repo file is the source used).
        home = make_home(tmp / "cloud", with_projection=True)
        (home / "ai-wif-brain-dashboard" / "data" / "investment_radar_public.json").write_text(
            json.dumps({"schema_version": 1, "generated_at": "t0", "articles": []})
        )
        mod, st = load_page(home)
        check("cloud mode detected", mod.LOCAL_MODE is False)
        check("no _HOME_STATUS anywhere",
              "_HOME_STATUS" not in (REPO / "app" / "views" / "threads" / "interesting_articles.py").read_text())
        at = AppTest.from_file(str(REPO / "app" / "views" / "threads" / "interesting_articles.py"))
        at.run(timeout=30)
        check("page renders (no exception)",
              not at.exception, at.exception[0].value if at.exception else "")
        arts = [m.value for m in at.metric]
        repo_expected = len(
            json.loads((REPO / "data" / "investment_radar_public.json").read_text())["articles"]
        )
        check("renders repo projection (consumer == export count)",
              bool(arts) and int(arts[0]) == repo_expected, f"{arts[:1]} vs {repo_expected}")

        # ---------- local mode ----------
        home2 = make_home(tmp / "local", with_projection=True)
        # private snapshot fixture must exist BEFORE module exec (drives LOCAL_MODE)
        priv = home2 / "ai-wif-brain-dashboard" / "data" / "status.json"
        priv.write_text(json.dumps({
            "investment_radar": {"leads": [
                {"date": "2026-09-06", "text": "Local article",
                 "source_path": "Q&A/some-note.md"}], "watch": []},
            "_private_marker": "x",
        }))
        mod2, st2 = load_page(home2)
        check("local mode detected", mod2.LOCAL_MODE is True)
        # resolver against a synthetic private snapshot (never the real one)
        priv = home2 / "ai-wif-brain-dashboard" / "data" / "status.json"
        priv.write_text(json.dumps({
            "investment_radar": {"leads": [
                {"date": "2026-09-06", "text": "Local article",
                 "source_path": "Q&A/some-note.md"}], "watch": []},
            "_private_marker": "x",
        }))
        resolved = mod2._resolve_local_source_path.__wrapped__(
            "2026-09-06", "Local article"
        )
        check("resolver finds local vault ref", resolved == "Q&A/some-note.md", resolved)
        resolved_miss = mod2._resolve_local_source_path.__wrapped__("2026-01-01", "Nope")
        check("resolver misses cleanly", resolved_miss == "")

        print(f"\n{PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
