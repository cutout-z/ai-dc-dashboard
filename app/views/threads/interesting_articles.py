"""Interesting Articles — investment radar items surfaced for the DC Dashboard.

Reads the Brain dashboard's status.json and filters investment_radar leads
for items specifically classified as DASHBOARD (action='dashboard') by the
investment radar logic.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

STATUS_PATH = Path.home() / "ai-wif-brain-dashboard" / "data" / "status.json"
VAULT_ROOT = (
    Path.home()
    / "Library/Mobile Documents/iCloud~md~obsidian/Documents/ZC_Mac_Vault"
)

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

@st.cache_data(ttl=300, show_spinner=False)
def _load_dashboard_items() -> list[dict]:
    if not STATUS_PATH.exists():
        return []

    try:
        status = json.loads(STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    radar = status.get("investment_radar", {})
    all_items: list[dict] = radar.get("leads", []) + radar.get("watch", [])

    dashboard_items = [
        item for item in all_items
        if item.get("action") == "dashboard"
    ]

    dashboard_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return dashboard_items


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
st.caption(
    "Extracted threads and articles surfaced by the Brain dashboard's "
    "investment radar for AI & DC Dashboard relevance. "
    "Click **📄 View full note** on any card to read the underlying vault note."
)

with st.spinner("Loading articles..."):
    items = _load_dashboard_items()

if not items:
    st.info(
        "No dashboard-classified articles found. "
        "The Brain dashboard's `status.json` may not be available or the "
        "investment radar hasn't surfaced any DC-relevant items yet."
    )
    st.caption(f"Looking at: `{STATUS_PATH}`")
else:
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
            source_path = item.get("source_path", "")
            card_key = f"card_{i}_{source_path}"

            # Card HTML
            st.markdown(_render_card_html(item), unsafe_allow_html=True)

            # View full note button
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
                    if source_path:
                        note_content = _load_note_content(source_path)
                        if note_content:
                            st.markdown(note_content)
                        else:
                            st.warning(f"Note not found: `{source_path}`")
                    else:
                        st.caption("No source path available for this article.")

            # Divider between cards
            st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)
