"""Frontier Lab Revenue & Valuations — funding rounds, ARR, and implied revenue multiples."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "reference"

LAB_COLORS = {"OpenAI": "#10b981", "Anthropic": "#d97706", "xAI": "#6366f1"}

st.title("Frontier Lab Revenue & Valuations")
st.caption(
    "Frontier labs are consuming the majority of AI CAPEX but are private. "
    "Funding round valuations and reported ARR are the only public signals. "
    "Implied EV/Revenue multiples of 15–30× represent the 'AI premium' the market is pricing in — "
    "the key question is whether revenue acceleration justifies the multiple expansion."
)

val_path = _DATA_DIR / "frontier_lab_valuations.csv"
if not val_path.exists():
    st.info("frontier_lab_valuations.csv not found — run /ai-research to populate.")
else:
    df_val = pd.read_csv(val_path)
    df_val["date"] = pd.to_datetime(df_val["date"])

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Valuation Trajectory")
        df_v = df_val[df_val["metric"] == "valuation"].sort_values("date")
        if not df_v.empty:
            fig_v = go.Figure()
            for company, color in LAB_COLORS.items():
                df_c = df_v[df_v["company"] == company]
                if df_c.empty:
                    continue
                fig_v.add_trace(go.Scatter(
                    x=df_c["date"], y=df_c["value"],
                    mode="lines+markers+text",
                    name=company,
                    line=dict(color=color, width=2),
                    marker=dict(size=8),
                    text=[f"${v:.0f}B" for v in df_c["value"]],
                    textposition="top center",
                    textfont=dict(size=9),
                    hovertemplate="<b>%{fullData.name}</b><br>%{x|%b %Y}: $%{y:.0f}B<br>%{customdata}<extra></extra>",
                    customdata=df_c["source"],
                ))
            fig_v.update_layout(
                height=450,
                yaxis_title="Valuation ($B)",
                yaxis_type="log",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_v, use_container_width=True)

    with col2:
        st.subheader("Revenue Run Rate (ARR)")
        df_r = df_val[df_val["metric"] == "arr"].sort_values("date")
        if not df_r.empty:
            fig_r = go.Figure()
            for company, color in LAB_COLORS.items():
                df_c = df_r[df_r["company"] == company]
                if df_c.empty:
                    continue
                fig_r.add_trace(go.Scatter(
                    x=df_c["date"], y=df_c["value"],
                    mode="lines+markers+text",
                    name=company,
                    line=dict(color=color, width=2),
                    marker=dict(size=8),
                    text=[f"${v:.1f}B" for v in df_c["value"]],
                    textposition="top center",
                    textfont=dict(size=9),
                ))
            fig_r.update_layout(
                height=450,
                yaxis_title="ARR ($B)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_r, use_container_width=True)

    st.subheader("Implied Revenue Multiple")
    multiples = []
    for company in LAB_COLORS:
        latest_val = df_val[(df_val["company"] == company) & (df_val["metric"] == "valuation")].sort_values("date").tail(1)
        latest_arr = df_val[(df_val["company"] == company) & (df_val["metric"] == "arr")].sort_values("date").tail(1)
        if not latest_val.empty and not latest_arr.empty:
            val = latest_val.iloc[0]["value"]
            arr = latest_arr.iloc[0]["value"]
            mult = val / arr if arr > 0 else None
            multiples.append({
                "Company": company,
                "Latest Valuation": f"${val:.0f}B",
                "Latest ARR": f"${arr:.1f}B",
                "EV/Revenue": f"{mult:.0f}x" if mult else "-",
                "Val Date": latest_val.iloc[0]["date"].strftime("%b %Y"),
                "ARR Date": latest_arr.iloc[0]["date"].strftime("%b %Y"),
            })
    if multiples:
        st.dataframe(pd.DataFrame(multiples), use_container_width=True, hide_index=True)

    with st.expander("Full Announcement Timeline"):
        df_display = df_val.sort_values("date", ascending=False)
        df_display["value_fmt"] = df_display.apply(
            lambda r: f"${r['value']:.1f}B" if r["unit"] == "USD_B" else f"${r['value']:.1f}B",
            axis=1,
        )
        st.dataframe(
            df_display[["date", "company", "metric", "value_fmt", "source", "notes"]].rename(
                columns={"value_fmt": "Value"}
            ),
            use_container_width=True, hide_index=True,
        )
