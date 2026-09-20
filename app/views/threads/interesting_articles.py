"""Interesting Articles — investment-radar articles for the DC Dashboard.

Astra 2026-09-04 remediation (F01/S2-01): cards read ONLY the allowlisted
public projection `data/investment_radar_public.json` produced by the Brain
dashboard's `export-public-articles.py`. The full private Brain snapshot
(`status.json`) is never loaded here except in local mode (see below).

Card source order:
  1. repo `data/investment_radar_public.json` — works on Streamlit Cloud
  2. `~/ai-wif-brain-dashboard/data/investment_radar_public.json` — local mode

Card selection (2026-09-17): dashboard-classified (mechanism-gated) articles
PLUS every DC-relevant radar article (AI/DC · Supply chain themes).

Card display (2026-09-17): headline + date only. Per Zalen's request the
routing badge (DASHBOARD / RESEARCH / MINER / WATCH), theme, polarity and
confidence pills, the extracted-entities line, the routing designation in
the footer, the summary metric row, both filter dropdowns and the
"Showing N of M" counter were all removed.

Full-note bodies (added 2026-09-17, restored 2026-09-20 after the minimal-card
sweep 029711f also swept the entry point) — note text never lives in this public
repo. Availability by environment, in order:
  1. local vault — the iCloud ZC_Mac_Vault on the Mac (LOCAL_MODE); freshest
  2. local mirror file — `~/ai-wif-brain-dashboard/data/notes/public_notes.json`
  3. private repo — raw.githubusercontent.com/cutout-z/ai-wif-brain-dashboard
     (`main:data/notes/public_notes.json`, published by the Brain dashboard's
     nightly job), fetched with a read-only GITHUB_TOKEN app secret.
Frontmatter is stripped for display; author / source / date render as a
caption above the note body. The per-card "View full note" button (restored
2026-09-20) is the entry point; with no note source available the page is
cards-only, captioned.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests
import streamlit as st

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPO_PUBLIC = _REPO_ROOT / "data" / "investment_radar_public.json"
_HOME_PUBLIC = Path.home() / "ai-wif-brain-dashboard" / "data" / "investment_radar_public.json"

# Local mode: the private vault snapshot exists on this machine, so full-note
# reading from the vault is possible. On Streamlit Cloud it is not.
_PRIVATE_LOCAL_STATUS = Path.home() / "ai-wif-brain-dashboard" / "data" / "status.json"
LOCAL_MODE = _PRIVATE_LOCAL_STATUS.exists()

STATUS_PATH = _HOME_PUBLIC if not REPO_PUBLIC.exists() else REPO_PUBLIC

VAULT_ROOT = (
    Path.home()
    / "Library/Mobile Documents/iCloud~md~obsidian/Documents/ZC_Mac_Vault"
)

# Notes mirror (private repo) — the cloud-safe source for full note bodies.
NOTES_MIRROR_URL = (
    "https://raw.githubusercontent.com/cutout-z/ai-wif-brain-dashboard/"
    "main/data/notes/public_notes.json"
)
_LOCAL_NOTES = Path.home() / "ai-wif-brain-dashboard" / "data" / "notes" / "public_notes.json"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


# ── helpers ────────────────────────────────────────────────────────────────

def _get_status_mtime() -> float:
    """Get projection mtime for cache busting."""
    try:
        return STATUS_PATH.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(ttl=60, show_spinner=False)
def _load_dashboard_items(status_mtime: float = 0.0) -> list[dict]:
    """Load the allowlisted public articles (schema_version 1 projection)."""
    if not STATUS_PATH.exists():
        return []

    try:
        export = json.loads(STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(export, dict) or export.get("schema_version") != 1:
        return []
    articles = export.get("articles", [])
    if not isinstance(articles, list):
        return []
    return [a for a in articles if isinstance(a, dict)]


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@st.cache_data(ttl=600, show_spinner="Loading note…")
def _load_note_content(source_path: str) -> str | None:
    """Read the full vault note for a given source_path. Returns None if missing."""
    note_path = VAULT_ROOT / source_path
    if not note_path.exists():
        return None
    try:
        return note_path.read_text(encoding="utf-8")
    except OSError:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _resolve_local_source_path(date: str, text: str) -> str:
    """Locally only: recover a vault ref from the private snapshot by identity.

    The public projection deliberately carries no source_path. On this Mac the
    private snapshot exists, so match (date, text) to restore note access.
    Never published — this runs exclusively in local mode.
    """
    try:
        status = json.loads(_PRIVATE_LOCAL_STATUS.read_text())
    except (json.JSONDecodeError, OSError):
        return ""
    radar = status.get("investment_radar", {})
    for item in radar.get("leads", []) + radar.get("watch", []):
        if isinstance(item, dict) and item.get("date") == date and item.get("text") == text:
            return str(item.get("source_path", ""))
    return ""


# ── notes mirror ────────────────────────────────────────────────────────────

def _github_token() -> str | None:
    """Read-only token for fetching the private notes mirror.

    Order: GITHUB_TOKEN env var, then Streamlit secrets. Only touches
    st.secrets when a secrets.toml exists on disk (same guard as
    app/lib/llm_perf.py) so local runs never show the no-secrets banner.
    """
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    _secrets_candidates = [
        Path.home() / ".streamlit" / "secrets.toml",
        _REPO_ROOT / ".streamlit" / "secrets.toml",
    ]
    if any(p.is_file() for p in _secrets_candidates):
        try:
            tok = st.secrets.get("GITHUB_TOKEN") or st.secrets.get("github_token")
            if tok:
                return str(tok)
        except Exception:
            pass
    return None


@st.cache_data(ttl=600, show_spinner=False)
def _load_notes_map() -> dict[tuple[str, str], str]:
    """(date, text) -> note body, from the local mirror file or the private repo.

    Local file wins when present (fresh export on this Mac); otherwise the
    private repo is fetched with GITHUB_TOKEN. Unavailable/failed fetch
    returns {} and the page degrades gracefully.
    """
    payload = None
    if _LOCAL_NOTES.is_file():
        try:
            payload = json.loads(_LOCAL_NOTES.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = None
    if payload is None:
        token = _github_token()
        if token:
            try:
                resp = requests.get(
                    NOTES_MIRROR_URL,
                    headers={
                        "Authorization": f"token {token}",
                        "Accept": "application/vnd.github.raw",
                    },
                    timeout=15,
                )
                if resp.ok:
                    payload = resp.json()
            except (requests.RequestException, json.JSONDecodeError, ValueError):
                payload = None
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return {}
    notes = payload.get("notes", [])
    if not isinstance(notes, list):
        return {}
    out: dict[tuple[str, str], str] = {}
    for note in notes:
        if not isinstance(note, dict):
            continue
        body = note.get("body")
        if isinstance(body, str) and body:
            out[(str(note.get("date", "")), str(note.get("text", "")))] = body
    return out


def _split_note(body: str) -> tuple[str, str]:
    """Return (meta_caption, markdown_body) with frontmatter removed.

    author / source / created become a tidy caption; everything else after
    the frontmatter renders as the note body.
    """
    meta_parts: list[str] = []
    m = _FRONTMATTER_RE.match(body)
    if m:
        fm = m.group(1)
        author = re.search(r'^author:\s*"?(.*?)"?\s*$', fm, re.MULTILINE)
        source = re.search(r'^source:\s*"?(.*?)"?\s*$', fm, re.MULTILINE)
        created = re.search(r'^created:\s*"?(.*?)"?\s*$', fm, re.MULTILINE)
        if author and author.group(1):
            meta_parts.append(author.group(1))
        if source and source.group(1):
            url = source.group(1)
            meta_parts.append(f"[source]({url})" if url.startswith("http") else url)
        if created and created.group(1):
            meta_parts.append(created.group(1)[:10])
        body = body[m.end():]
    return " · ".join(meta_parts), body.lstrip("\n")


def _note_body_for(item: dict, notes_map: dict[tuple[str, str], str]) -> str | None:
    """Best available full-note body for an article item, or None."""
    key = (str(item.get("date", "")), str(item.get("text", "")))
    if LOCAL_MODE:
        source_path = _resolve_local_source_path(*key)
        if source_path:
            content = _load_note_content(source_path)
            if content:
                return content
    return notes_map.get(key)


# ── cards ──────────────────────────────────────────────────────────────────

def _render_card_html(item: dict) -> str:  # retained for reference; unused since the 2026-09-20 grid rework
    """Render a single article card: headline + date only."""
    text = _html_escape(str(item.get("text", "")))
    date = _html_escape(str(item.get("date", "")))

    return f"""
    <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;
                padding:16px;margin-bottom:0;">
      <div style="font-size:14px;font-weight:600;color:#e2e8f0;
                  line-height:1.4;margin-bottom:6px;">
        {text}
      </div>
      <div style="font-size:11px;color:#4b5563;">
        {date}
      </div>
    </div>
    """


# ── page (callable so the News page can embed this section) ────────────────

def render_interesting_articles() -> None:
    """Render the Interesting Articles section (cards grid + note dialogs).

    UX (2026-09-20 rework):
    - cards lay out in a 2-column grid with no fixed-height scroll box, so
      many more articles are visible on load;
    - the "Read note" button lives INSIDE each card (no hanging button row);
    - clicking opens a full modal dialog (st.dialog) showing the complete
      note — meta caption above, whole markdown body scrollable — instead of
      an inline expansion that required scrolling to reach.
    """
    with st.spinner("Loading articles..."):
        items = _load_dashboard_items(status_mtime=_get_status_mtime())

    notes_map = _load_notes_map()
    notes_available = LOCAL_MODE or bool(notes_map)

    if not items:
        st.info(
            "No dashboard-classified articles found. "
            "The public article projection (`investment_radar_public.json`) may not "
            "be available yet, or the investment radar hasn't surfaced any "
            "DC-relevant items."
        )
        st.caption(f"Looking at: `{STATUS_PATH}`")
        return

    if LOCAL_MODE:
        note_hint = " Click **Read note** on any card to open the underlying vault note."
    elif notes_available:
        note_hint = " Click **Read note** on any card (served from the private notes mirror)."
    elif _github_token():
        note_hint = " Note mirror unavailable right now — cards only."
    else:
        note_hint = " Vault notes are available locally only."
    st.caption(
        "Extracted threads and articles surfaced by the Brain dashboard's "
        "investment radar for AI & DC Dashboard relevance." + note_hint
    )

    @st.dialog("Full note", width="large")
    def _show_note(item: dict) -> None:
        """Modal dialog with the full note body (readable, no page scroll)."""
        note_content = _note_body_for(item, notes_map)
        if note_content:
            meta, body = _split_note(note_content)
            if meta:
                st.caption(meta)
            st.markdown(body)
        else:
            st.warning(
                "Note not found for this article."
                + (" (vault note missing)" if LOCAL_MODE
                   else " (not in notes mirror)")
            )

    # ── card grid: 2 columns, button embedded in the card ──
    cols = st.columns(2)
    for i, item in enumerate(items):
        card_key = f"card_{i}"
        headline = str(item.get("text", ""))
        date = str(item.get("date", ""))
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(
                    f"<div style='font-size:14px;font-weight:600;line-height:1.4;"
                    f"margin-bottom:4px;'>{_html_escape(headline)}</div>",
                    unsafe_allow_html=True,
                )
                btn_col, date_col = st.columns([1, 3])
                with btn_col:
                    if notes_available and st.button(
                        "Read note", key=f"btn_{card_key}", use_container_width=True
                    ):
                        _show_note(item)
                with date_col:
                    st.markdown(
                        f"<div style='font-size:11px;opacity:0.6;"
                        f"padding-top:7px;text-align:right;'>{_html_escape(date)}</div>",
                        unsafe_allow_html=True,
                    )
