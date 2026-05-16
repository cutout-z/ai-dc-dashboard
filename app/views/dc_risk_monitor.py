"""Hidden DC operator risk monitor review page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

from app.lib.dc_risk_signals import (
    STATUS_COLORS,
    STATUS_LABELS,
    RiskSignal,
    buildout_financing_signal,
    capex_commitment_signal,
    capital_markets_signal,
    contracted_demand_signal,
    market_breadth_signal,
    model_economics_signal,
    overall_status,
    power_deliverability_signal,
    power_procurement_coverage_signal,
    project_execution_signal,
    unscored_context,
)
from app.lib.equities import fetch_equities_data


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NEWS_CATALOG_PATH = PROJECT_ROOT / "data" / "reference" / "news_catalog.csv"

EXPORT_MODE = st.query_params.get("export") == "1"
if EXPORT_MODE:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        #MainMenu {
            display: none !important;
        }
        .block-container {
            max-width: 1180px !important;
            padding-top: 2rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        [data-testid="stAppViewContainer"] {
            margin-left: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

st.title("Australian DC Risk Monitor")
st.caption(
    "Hidden review page. Focus: downside risk to Australian data-centre operators and projects, "
    "with global hyperscaler and AI signals treated as upstream transmission indicators."
)


def _load_market_signal() -> RiskSignal:
    try:
        with st.spinner("Loading market breadth..."):
            return market_breadth_signal(fetch_equities_data())
    except Exception:
        return market_breadth_signal(None)


@st.cache_data(ttl=300, show_spinner=False)
def _load_high_news(path: str, limit: int = 12) -> pd.DataFrame:
    catalog_path = Path(path)
    if not catalog_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(catalog_path)
    if df.empty:
        return df

    for col in ("published", "first_seen_at", "last_seen_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    df["max_materiality_score"] = pd.to_numeric(
        df.get("max_materiality_score"), errors="coerce"
    ).fillna(0.0)
    high = df[df.get("last_tier", "") == "HIGH"].copy()
    if high.empty:
        return high
    return high.sort_values(
        ["published", "max_materiality_score"], ascending=[False, False]
    ).head(limit)


signals = [
    contracted_demand_signal(),
    capex_commitment_signal(),
    power_deliverability_signal(),
    power_procurement_coverage_signal(),
    project_execution_signal(),
    capital_markets_signal(),
    buildout_financing_signal(),
    _load_market_signal(),
    model_economics_signal(),
]
overall = overall_status(signals)

SIGNAL_LENS = {
    "Contracted demand quality": {
        "lens": "AU direct",
        "why": "Uses AU/ANZ operator contracted-capacity and order-book disclosures.",
    },
    "Project execution and permitting": {
        "lens": "AU direct",
        "why": "Uses the Australian project database: site status, MW, power evidence, and remediation fields.",
    },
    "Hyperscaler commitment": {
        "lens": "Global tenant proxy",
        "why": "Australian growth is largely hyperscaler-led, so global capex cuts/pushouts can transmit into local leasing and delivery confidence.",
    },
    "Portfolio power coverage": {
        "lens": "Global tenant proxy",
        "why": "Tracks global hyperscaler power procurement because the same tenants anchor Australian demand; campus-level AU power matching is still a gap.",
    },
    "Power deliverability": {
        "lens": "Global infrastructure proxy",
        "why": "Current queue data is US-heavy, but the risk mechanism is directly relevant to Australian grid-constrained projects.",
    },
    "Capital markets": {
        "lens": "Global funding proxy",
        "why": "Debt appetite and private-credit conditions influence Australian operators, offshore tenants, and development partners.",
    },
    "Buildout financing exposure": {
        "lens": "Global funding proxy",
        "why": "Tracks debt-funded AI/DC buildout pressure around tenants and infrastructure platforms that can affect Australian demand quality.",
    },
    "Market breadth": {
        "lens": "Global risk-appetite proxy",
        "why": "Equity breadth is not Australian project evidence, but helps identify whether DC/AI risk appetite is narrowing.",
    },
    "Model economics": {
        "lens": "Global AI-demand proxy",
        "why": "Model economics affect the willingness of AI tenants to keep absorbing high-cost capacity globally, including Australia.",
    },
}


def _status_pill(status: str) -> str:
    color = STATUS_COLORS.get(status, "#6b7280")
    label = STATUS_LABELS.get(status, status.title())
    return (
        f"<span style='display:inline-block;padding:2px 9px;border-radius:999px;"
        f"background:{color};color:white;font-size:0.78rem;font-weight:700;'>{label}</span>"
    )


def _lens_pill(sig: RiskSignal) -> str:
    lens = SIGNAL_LENS.get(sig.name, {}).get("lens", "Signal")
    color = "#0f766e" if lens == "AU direct" else "#475569"
    return (
        f"<span style='display:inline-block;padding:2px 9px;border-radius:999px;"
        f"background:{color};color:white;font-size:0.72rem;font-weight:700;'>{lens}</span>"
    )


def _render_signal_card(sig: RiskSignal) -> None:
    color = STATUS_COLORS.get(sig.status, "#6b7280")
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-left:6px solid {color};border-radius:6px;
                    padding:14px 16px;margin-bottom:12px;background:rgba(255,255,255,0.02);">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
            <div>
              <div style="font-size:1.05rem;font-weight:750;margin-bottom:4px;">{sig.name}</div>
              <div style="font-size:1.55rem;font-weight:800;color:{color};">{sig.value}</div>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
              {_lens_pill(sig)}
              {_status_pill(sig.status)}
            </div>
          </div>
          <div style="font-size:0.88rem;margin-top:8px;color:#9ca3af;">{sig.detail}</div>
          <div style="font-size:0.78rem;margin-top:8px;color:#64748b;">{SIGNAL_LENS.get(sig.name, {}).get("why", "")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Why it matters**")
        st.caption(sig.why_it_matters)
    with c2:
        st.markdown("**Watch for**")
        st.caption(sig.watch_for)

    if sig.evidence:
        st.markdown("**Current evidence**")
        for item in sig.evidence[:5]:
            st.caption(f"- {item}")

    if sig.table is not None and not sig.table.empty:
        with st.expander("Underlying rows"):
            st.dataframe(sig.table, use_container_width=True, hide_index=True)


top_col, detail_col = st.columns([1.1, 2])
with top_col:
    overall_color = STATUS_COLORS.get(overall["status"], "#6b7280")
    st.markdown(
        f"""
        <div style="border-radius:8px;padding:18px;background:{overall_color};color:white;">
          <div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;">Current state</div>
          <div style="font-size:1.55rem;font-weight:800;line-height:1.15;margin-top:6px;">{overall["label"]}</div>
          <div style="font-size:0.9rem;margin-top:8px;">{overall["detail"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with detail_col:
    st.markdown(
        """
        This version deliberately avoids a single AI-bubble verdict. The monitor is anchored on Australian DC
        operator risk, then layers global signals only where they plausibly transmit into local downside through
        hyperscaler leasing, project execution, power availability, financing conditions, or AI tenant economics.
        """
    )
    st.caption(
        "Signals with weak attribution to DC operators are kept as context only: AI revenue disclosure, circular financing, and GPU spot prices."
    )

st.subheader("Australian Market Lens")
st.markdown(
    """
The dashboard's risk question is not "is US AI in a bubble?" It is: **could the Australian data-centre buildout be overextended, delayed, or repriced?**

Because Australian demand is primarily hyperscaler-led, global AI and US financial signals still matter, but only as transmission channels:
global capex plans affect tenant demand, global credit markets affect funding, global model economics affect AI workload growth, and global power procurement shows how seriously tenants are solving the energy bottleneck.
"""
)
st.dataframe(
    pd.DataFrame(
        [
            {
                "Layer": "Australian direct evidence",
                "What it covers": "Local projects, AU/ANZ contracted MW, operator order books, project status, power evidence.",
                "How to read it": "Highest weight. These are closest to Australian DC operator economics.",
            },
            {
                "Layer": "Tenant transmission",
                "What it covers": "Hyperscaler capex, global power procurement, AI workload economics.",
                "How to read it": "Relevant because hyperscalers anchor Australian demand, but not standalone proof of AU stress.",
            },
            {
                "Layer": "Funding transmission",
                "What it covers": "Debt/private-credit events, buildout financing, market breadth.",
                "How to read it": "Useful for refinancing and risk-appetite pressure, but needs local bond/spread data to become decisive.",
            },
        ]
    ),
    use_container_width=True,
    hide_index=True,
)


st.subheader("Risk Matrix")

matrix = pd.DataFrame(
    {
        "Signal": [s.name for s in signals],
        "Lens": [SIGNAL_LENS.get(s.name, {}).get("lens", "") for s in signals],
        "Score": [s.score for s in signals],
        "Status": [STATUS_LABELS.get(s.status, s.status) for s in signals],
        "Value": [s.value for s in signals],
    }
)
fig = go.Figure()
fig.add_trace(
    go.Bar(
        x=matrix["Score"],
        y=matrix["Signal"],
        orientation="h",
        marker_color=[
            STATUS_COLORS.get(s.status, "#6b7280")
            for s in signals
        ],
        text=matrix["Status"] + " - " + matrix["Value"],
        textposition="auto",
        hovertemplate="%{y}<br>%{text}<extra></extra>",
    )
)
fig.update_layout(
    height=310,
    xaxis=dict(
        title="Risk level",
        tickmode="array",
        tickvals=[0, 1, 2],
        ticktext=["Supported / no score", "Watch", "Warning"],
        range=[0, 2.4],
    ),
    yaxis=dict(autorange="reversed"),
    margin=dict(l=0, r=0, t=10, b=0),
    showlegend=False,
)
st.plotly_chart(fig, use_container_width=True)


st.subheader("High-Rated News")
st.caption(
    "Duplicated from the News catalog. These are not scored directly, but they provide the event layer behind the risk monitor."
)
high_news = _load_high_news(str(NEWS_CATALOG_PATH))
if high_news.empty:
    st.info("No HIGH-rated news rows found in the catalog.")
else:
    news_display = pd.DataFrame(
        {
            "Published": high_news["published"].dt.strftime("%Y-%m-%d"),
            "Bucket": high_news.get("last_bucket", "").fillna(""),
            "Score": high_news["max_materiality_score"],
            "Title": high_news.get("title", "").fillna(""),
            "Source": high_news.get("source", "").fillna(""),
            "Link": high_news.get("url", "").fillna(""),
        }
    )
    st.dataframe(
        news_display,
        use_container_width=True,
        hide_index=True,
        height=min(500, 38 * (len(news_display) + 1) + 3),
        column_config={
            "Published": st.column_config.TextColumn("Published", width="small"),
            "Bucket": st.column_config.TextColumn("Bucket", width="medium"),
            "Score": st.column_config.NumberColumn("Score", format="%.3f", width="small"),
            "Title": st.column_config.TextColumn("Title", width="large"),
            "Source": st.column_config.TextColumn("Source", width="medium"),
            "Link": st.column_config.LinkColumn("Link", display_text="Open", width="small"),
        },
    )


st.subheader("Scored Signals")

for section, section_signals in [
    ("Australian Direct Signals", [s for s in signals if SIGNAL_LENS.get(s.name, {}).get("lens") == "AU direct"]),
    ("Global Transmission Signals", [s for s in signals if SIGNAL_LENS.get(s.name, {}).get("lens") != "AU direct"]),
]:
    st.markdown(f"### {section}")
    for signal in section_signals:
        with st.container(border=True):
            _render_signal_card(signal)


st.subheader("Context Only")
st.caption("Useful signals, but not strong enough to drive the DC operator risk score without better evidence.")
context_df = pd.DataFrame(unscored_context())
st.dataframe(context_df, use_container_width=True, hide_index=True)


st.subheader("Data Buildout Status")
st.caption("What has been implemented from the recommended data list, and what still needs a better source.")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Area": "Lease backlog / preleasing",
                "Now implemented": "AU/ANZ operator contracted MW and forward order book disclosures.",
                "Remaining gap": "Tenant concentration, WALE, churn, and signed-but-not-commenced conversion.",
            },
            {
                "Area": "Power procurement",
                "Now implemented": "Portfolio-level firm/PPA versus soft pipeline from tracked sourcing disclosures.",
                "Remaining gap": "Australian campus-level firm MW versus announced IT load and power delivery dates.",
            },
            {
                "Area": "Project execution",
                "Now implemented": "AU project status, proposed-MW share, power evidence gaps, and remediation fields.",
                "Remaining gap": "Automated permitting/interconnection status by named campus.",
            },
            {
                "Area": "Market breadth",
                "Now implemented": "Existing live basket returns by Mag 7, AI Infra, and DC Operators.",
                "Remaining gap": "Equal-weight vs cap-weight indices and a longer stored history.",
            },
            {
                "Area": "Capital markets",
                "Now implemented": "Material credit/debt event proxy from the news catalog plus tracked debt/hybrid financing exposure.",
                "Remaining gap": "Australian operator bond yields/spreads, rating outlooks, maturities, and covenant data.",
            },
            {
                "Area": "AU-specific tenant transmission",
                "Now implemented": "Global hyperscaler commitment and model-economics signals are marked as transmission proxies.",
                "Remaining gap": "Named AU tenant mix, campus-level preleasing, signed-but-not-commenced capacity, and customer concentration.",
            },
        ]
    ),
    use_container_width=True,
    hide_index=True,
)
