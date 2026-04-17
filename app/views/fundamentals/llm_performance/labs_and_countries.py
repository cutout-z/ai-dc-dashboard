"""Labs and Countries — who is leading, shipping the most, and how power is shifting."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import (
    ATTR, PROVIDER_COLOURS, ORG_TO_PROVIDER,
    fetch_zeroeval_models, preprocess_ze, chart_layout,
)

ze_df = fetch_zeroeval_models()
df, _ = preprocess_ze(ze_df)
CHART_LAYOUT = chart_layout()

st.title("Labs and Countries")
st.caption("Who is leading, who is shipping the most, and how the balance of power is shifting.")

if ze_df.empty or df.empty:
    st.info("Live data unavailable — ZeroEval API offline.")
else:
    ctry_counts = df["country"].value_counts().reset_index()
    ctry_counts.columns = ["country", "count"]
    fig_ctry = go.Figure(go.Bar(
        x=ctry_counts["count"], y=ctry_counts["country"], orientation="h",
        marker_color="#3b82f6",
        hovertemplate="%{y}: %{x} models<extra></extra>",
    ))
    fig_ctry.update_layout(
        title="Cumulative Releases by Country",
        xaxis_title="Models",
        yaxis=dict(autorange="reversed"),
        height=300,
        showlegend=False,
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_ctry, use_container_width=True)

    hm = df.groupby(["year", "month"]).size().reset_index(name="count")
    hm_piv = hm.pivot(index="year", columns="month", values="count").fillna(0)
    month_abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    hm_piv.columns = [month_abbr[c - 1] for c in hm_piv.columns]
    fig_hm = go.Figure(go.Heatmap(
        z=hm_piv.values, x=hm_piv.columns.tolist(), y=hm_piv.index.tolist(),
        colorscale="Blues", text=hm_piv.values.astype(int), texttemplate="%{text}",
        hovertemplate="Year: %{y} · %{x}: %{z} releases<extra></extra>",
    ))
    fig_hm.update_layout(title="Release Heatmap", height=300, showlegend=False, **CHART_LAYOUT)
    st.plotly_chart(fig_hm, use_container_width=True)

    top5c = df["country"].value_counts().head(5).index.tolist()
    df["country_grp"] = df["country"].apply(lambda c: c if c in top5c else "Other")
    qc = df.groupby(["quarter", "country_grp"]).size().reset_index(name="count")
    qc["pct"] = qc.groupby("quarter")["count"].transform(lambda x: x / x.sum() * 100)
    ctry_clrs = {
        "US": "#3b82f6", "CN": "#ef4444", "FR": "#10b981",
        "GB": "#f59e0b", "IL": "#8b5cf6", "KR": "#ec4899",
        "IN": "#06b6d4", "CA": "#a78bfa", "Other": "#6b7280",
    }
    ctry_labels = {
        "US": "United States", "CN": "China", "FR": "France",
        "GB": "United Kingdom", "IL": "Israel", "KR": "South Korea",
        "IN": "India", "CA": "Canada", "Other": "Other",
    }
    fig_ctry_area = go.Figure()
    for ctry in top5c + ["Other"]:
        colour = ctry_clrs.get(ctry, "#6b7280")
        label = ctry_labels.get(ctry, ctry)
        sub = qc[qc["country_grp"] == ctry]
        if sub.empty:
            continue
        fig_ctry_area.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["pct"], name=label, stackgroup="one",
            line=dict(color=colour, width=0),
            fillcolor=colour,
            hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_ctry_area.update_layout(
        title="Model Releases by Country (% share)",
        yaxis_title="Share (%)",
        height=320,
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_ctry_area, use_container_width=True)

    top8labs = df["organization"].value_counts().head(8).index.tolist()
    total = len(df)
    fig_labs = go.Figure()
    for org in top8labs:
        sub = df[df["organization"] == org].groupby("quarter").size().reset_index(name="n")
        sub = sub.sort_values("quarter")
        sub["cum_pct"] = sub["n"].cumsum() / total * 100
        colour = PROVIDER_COLOURS.get(ORG_TO_PROVIDER.get(org, ""), "#6b7280")
        fig_labs.add_trace(go.Scatter(
            x=sub["quarter"], y=sub["cum_pct"], name=org,
            mode="lines", line=dict(color=colour, width=1.5),
            hovertemplate=f"{org}: %{{y:.1f}}%<extra></extra>",
        ))
    fig_labs.update_layout(
        title="Cumulative Releases by Lab (% of total)",
        yaxis_title="Cumulative Share (%)",
        height=320,
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_labs, use_container_width=True)
    st.caption(ATTR)
