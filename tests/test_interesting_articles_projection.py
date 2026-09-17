"""A4 functional check: interesting_articles.py reads only the projection.

Runs the real page under Streamlit AppTest twice:
  cloud-mode  — repo data/investment_radar_public.json is the projection,
                _HOME_STATUS removed: old full-snapshot loader would show 0.
  local-mode  — _HOME_PUBLIC present (fixture with private-marker + item).

Also checks the private-snapshot resolver directly. Never touches the real
private snapshot; all state via monkeypatched module constants.

Card display contract (2026-09-17): headline + date only — no routing badge,
theme/polarity/confidence pills, entities line or designation, and no summary
metric row / filter controls on the page.

Run:  /opt/anaconda3/bin/python3.12 tests/test_interesting_articles_projection.py
"""
from __future__ import annotations

import importlib.util
import json
import os
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
        repo_expected = len(
            json.loads((REPO / "data" / "investment_radar_public.json").read_text())["articles"]
        )
        cards = [m.value for m in at.markdown if "background:#111827" in m.value]
        check("renders one card per projected article (consumer == export count)",
              len(cards) == repo_expected, f"{len(cards)} vs {repo_expected}")
        check("no summary metrics row on the page", not at.metric,
              f"{len(at.metric)} metric(s) rendered" if at.metric else "")
        check("no filter controls on the page", not at.multiselect)
        check("no buttons on the page", not at.button)

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

        # ---------- notes mirror: local file source + note formatting ----------
        home3 = make_home(tmp / "mirror", with_projection=True)
        notes_dir = home3 / "ai-wif-brain-dashboard" / "data" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        fixture_body = (
            "---\nauthor: \"@someone\"\nlinks: [\"[[private]]\"]\n"
            "source: \"https://x.com/a\"\ncreated: 2026-09-01T00:00:00Z\n---\n\n# Note\n\nBody here"
        )
        (notes_dir / "public_notes.json").write_text(json.dumps({
            "schema_version": 1, "generated_at": "t0",
            "notes": [{"date": "2026-09-06", "text": "Local article",
                       "source_path": "Q&A/some-note.md", "digest": "abc",
                       "body": fixture_body}],
        }))
        os.environ.pop("GITHUB_TOKEN", None)  # keep tests offline
        mod3, _st3 = load_page(home3)
        m3 = mod3._load_notes_map.__wrapped__()
        check("mirror map loads from local file",
              ("2026-09-06", "Local article") in m3, f"{list(m3)[:2]}")
        check("mirror body carries note text",
              "Body here" in m3.get(("2026-09-06", "Local article"), ""))
        meta, body = mod3._split_note(fixture_body)
        check("frontmatter stripped from displayed body",
              "---" not in body and "links:" not in body, body[:48])
        check("meta caption carries author + source + date",
              "@someone" in meta and "x.com/a" in meta and "2026-09-01" in meta, meta)
        check("body keeps note content", body.strip().startswith("# Note"), body[:48])

        # ---------- card payload: headline + date only ----------
        html_card = mod2._render_card_html({
            "date": "2026-09-14",
            "text": "Headline here",
            "snippet": "snippety",
            "destination": "Personal investing",
            "polarity": "context",
            "confidence": "medium",
            "themes": ["AI/DC", "Macro"],
            "entities": ["OpenAI", "Anthropic"],
        })
        check("card keeps headline", "Headline here" in html_card)
        check("card keeps date", "2026-09-14" in html_card)
        for gone in ("RESEARCH", "DASHBOARD", "MINER", "WATCH", "AI/DC", "Macro",
                     "CONTEXT", "CONFIDENCE", "Entities", "OpenAI",
                     "Personal investing", "snippety"):
            check(f"card drops {gone!r}", gone not in html_card)

        print(f"\n{PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
