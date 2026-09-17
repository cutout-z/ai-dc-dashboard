"""Interesting Articles — investment-radar articles for the DC Dashboard.

Astra 2026-09-04 remediation (F01/S2-01): cards read ONLY the allowlisted
public projection `data/investment_radar_public.json` produced by the Brain
dashboard's `export-public-articles.py`. The full private Brain snapshot
(`status.json`) is never loaded here except in local mode (see below).

Card source order:
  1. repo `data/investment_radar_public.json` — works on Streamlit Cloud
  2. `~/ai-wif-brain-dashboard/data/investment_radar_public.json` — local mode

Full-note bodies (added 2026-09-17) — note text never lives in this public
repo. Availability by environment, in order:
  1. local vault — the iCloud ZC_Mac_Vault on the Mac (LOCAL_MODE); freshest
  2. local mirror file — `~/ai-wif-brain-dashboard/data/notes/public_notes.json`
  3. private repo — raw.githubusercontent.com/cutout-z/ai-wif-brain-dashboard
     (`main:data/notes/public_notes.json`, published by the Brain dashboard's
     nightly job), fetched with a read-only GITHUB_TOKEN app secret.
Frontmatter is stripped for display; author / source / date render as a
caption above the note body.
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

# ── colour palette (dark-theme, consistent with Brain dashboard) ──────────
POLARITY_COLORS: dict[str, str] = {
    "bull / upside": "#22c55e",
    "bear / risk":   "#ef4444",
    "mixed":         "#f59e0b",
    "context":       "#6b7280",
}

THEME_COLORS: dict[str, str] = {
    "AI/DC":                   "#3b82f6",
    "Supply chain":            "#a855f7",
    "Macro":                   "#f59e0b",
    "Commodities / energy":    "#14b8a6",
    "Market structure":        "#ec4899",
    "Company / security":      "#f97316",
    "Geopolitics":             "#ef4444",
}

CONFIDENCE_BADGE: dict[str, str] = {
    "high":   "#22c55e",
    "medium": "#f59e0b",
    "low":    "#ef4444",
}


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


def _render_card_html(item: dict) -> str:
    """Render a single article card as dark-theme HTML."""
    text = _html_escape(item.get("text", ""))
    snippet = _html_escape(item.get("snippet", ""))
    themes = item.get("themes", [])
    polarity = item.get("polarity", "context")
    entities = item.get("entities", [])
    confidence = item.get("confidence", "medium")
    date = item.get("date", "")
    destination = item.get("destination", "")

    pol_color = POLARITY_COLORS.get(polarity, "#6b7280")
    pol_label = polarity.upper() if polarity != "context" else "CONTEXT"
    conf_color = CONFIDENCE_BADGE.get(confidence, "#6b7280")
    conf_label = f"CONFIDENCE {confidence.upper()}"

    theme_tags = "".join(
        f'<span style="display:inline-block;margin:0 4px 4px 0;padding:2px 8px;'
        f'border-radius:12px;font-size:10px;font-weight:600;text-transform:uppercase;'
        f'border:1px solid {THEME_COLORS.get(t, "#6b7280")}40;'
        f'color:{THEME_COLORS.get(t, "#6b7280")};'
        f'background:{THEME_COLORS.get(t, "#6b7280")}15;">{_html_escape(t)}</span>'
        for t in themes
    )

    entities_str = ", ".join(entities) if entities else ""
    entities_html = (
        f'<div style="margin-top:6px;font-size:11px;color:#6b7280;">'
        f'Entities: {_html_escape(entities_str)}</div>'
        if entities_str
        else ""
    )

    footer_parts = [date]
    if destination:
        dest = destination.replace(" + ", " · ")
        footer_parts.append(dest)
    footer = " · ".join(footer_parts)

    return f"""
    <div style="background:#111827;border:1px solid #1e293b;border-radius:8px;
                padding:16px;margin-bottom:0;">
      <div style="display:flex;align-items:flex-start;gap:10px;">
        <span style="flex-shrink:0;display:inline-block;padding:2px 10px;
                     border-radius:4px;font-size:10px;font-weight:700;
                     text-transform:uppercase;
                     background:rgba(6,182,212,0.15);
                     color:#22d3ee;border:1px solid #0891b2;">
          DASHBOARD
        </span>
        <div>
          <div style="font-size:14px;font-weight:600;color:#e2e8f0;
                      line-height:1.4;margin-bottom:4px;">
            {text}
          </div>
          <div style="font-size:12px;color:#9ca3af;font-style:italic;
                      margin-bottom:8px;">
            {snippet}
          </div>
        </div>
      </div>

      <div style="margin-bottom:6px;">{theme_tags}</div>

      <div style="margin-bottom:6px;">
        <span style="display:inline-block;margin-right:6px;padding:2px 8px;
                     border-radius:12px;font-size:10px;font-weight:600;
                     border:1px solid {pol_color}40;
                     color:{pol_color};background:{pol_color}15;">
          {pol_label}
        </span>
        <span style="display:inline-block;padding:2px 8px;border-radius:12px;
                     font-size:10px;font-weight:600;
                     border:1px solid {conf_color}40;
                     color:{conf_color};background:{conf_color}15;">
          {conf_label}
        </span>
      </div>

      {entities_html}

      <div style="margin-top:8px;font-size:11px;color:#4b5563;">
        {footer}
      </div>
    </div>
    """


# ── page ───────────────────────────────────────────────────────────────────

st.title("Interesting Articles")

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
else:
    # ── notes availability caption ──
    if LOCAL_MODE:
        note_hint = (
            " Click **📄 View full note** on any card to read the underlying vault note."
        )
    elif notes_available:
        note_hint = (
            " Click **📄 View full note** on any card to read the note "
            "(served from the private notes mirror)."
        )
    elif _github_token():
        note_hint = " Note mirror unavailable right now — cards only."
    else:
        note_hint = " Vault notes are available locally only."
    st.caption(
        "Extracted threads and articles surfaced by the Brain dashboard's "
        "investment radar for AI & DC Dashboard relevance." + note_hint
    )

    # ── summary metrics ──
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Articles", len(items))
    col2.metric(
        "Bull / Upside",
        sum(1 for it in items if "bull" in str(it.get("polarity", "")).lower()),
    )
    col3.metric(
        "Bear / Risk",
        sum(1 for it in items if "bear" in str(it.get("polarity", "")).lower()),
    )
    col4.metric(
        "Mixed",
        sum(1 for it in items if it.get("polarity") == "mixed"),
    )
    col5.metric(
        "Context",
        sum(1 for it in items if it.get("polarity") == "context"),
    )

    # ── filters ──
    filt_col1, filt_col2 = st.columns([2, 1])
    with filt_col1:
        all_themes = sorted(
            {t for it in items for t in it.get("themes", [])}
        )
        selected_themes = st.multiselect(
            "Filter by theme", all_themes, default=[], placeholder="All themes"
        )
    with filt_col2:
        all_pols = sorted(
            {it.get("polarity", "context") for it in items}
        )
        selected_pols = st.multiselect(
            "Filter by polarity", all_pols, default=[], placeholder="All polarities"
        )

    filtered = items
    if selected_themes:
        filtered = [
            it for it in filtered
            if set(selected_themes).intersection(it.get("themes", []))
        ]
    if selected_pols:
        filtered = [
            it for it in filtered
            if it.get("polarity") in selected_pols
        ]

    st.caption(f"Showing {len(filtered)} of {len(items)} articles")

    # ── render cards ──
    with st.container(height=700, border=False):
        for i, item in enumerate(filtered):
            card_key = f"card_{i}"

            # Card HTML
            st.markdown(_render_card_html(item), unsafe_allow_html=True)

            # View full note button — shown whenever a note source exists
            if notes_available:
                view_col, _ = st.columns([1, 4])
                with view_col:
                    if st.button("📄 View full note", key=f"btn_{card_key}"):
                        st.session_state.setdefault("expanded_notes", set())
                        if card_key in st.session_state["expanded_notes"]:
                            st.session_state["expanded_notes"].discard(card_key)
                        else:
                            st.session_state["expanded_notes"].add(card_key)

                # Show note content if expanded
                if st.session_state.get("expanded_notes", set()) and card_key in st.session_state["expanded_notes"]:
                    with st.container(border=True):
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
            # No note source (cloud without token): cards only.

            # Divider between cards
            st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)
