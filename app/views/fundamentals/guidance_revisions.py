"""Historical CAPEX Guidance Revisions — how hyperscaler CAPEX guidance evolved from first issuance to actual."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"

COMPANY_COLORS = {
    "Microsoft": "#00A4EF",
    "Alphabet": "#EA4335",
    "Amazon": "#FF9900",
    "Meta": "#1877F2",
    "Oracle": "#C74634",
    "CoreWeave": "#00BFA5",
    "Apple": "#A3AAAE",
}

# Fiscal years that have closed (actuals reported)
COMPLETED_FY = {"FY2025", "CY2025"}

st.title("Historical CAPEX Guidance Revisions")
st.caption(
    "Shows how each hyperscaler's annual CAPEX guidance evolved from first issuance through "
    "to the full-year actual. Solid lines = in-progress years. Dashed = completed. "
    "★ stars = reported actuals. Error bars show stated guidance ranges (low–high)."
)

# ── Load ─────────────────────────────────────────────────────────────────────
history_path = DATA_DIR / "capex_guidance_history.csv"
df_raw = pd.read_csv(history_path, parse_dates=["announced_date"])

ALL_COMPANIES = [c for c in COMPANY_COLORS if c in df_raw["company"].unique()]
ALL_FY = sorted(df_raw["fiscal_year"].unique(), reverse=True)

# ── Filters ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    selected_companies = st.multiselect(
        "Companies", ALL_COMPANIES, default=ALL_COMPANIES, key="gr_companies"
    )
with col2:
    selected_fy = st.multiselect(
        "Fiscal Years", ALL_FY, default=ALL_FY, key="gr_fy"
    )

if not selected_companies or not selected_fy:
    st.warning("Select at least one company and fiscal year.")
    st.stop()

df = df_raw[
    df_raw["company"].isin(selected_companies) & df_raw["fiscal_year"].isin(selected_fy)
].copy()

if df.empty:
    st.info("No guidance history for the selected filters.")
    st.stop()

# ── Revision path chart ───────────────────────────────────────────────────────
st.subheader("Revision Paths")

template = st.session_state.get("plotly_template", "plotly_dark")
annotation_color = st.session_state.get("annotation_color", "white")

fig = go.Figure()

# One legend entry per company; FY labelled inline at line end
_legend_shown = set()

for company in selected_companies:
    color = COMPANY_COLORS.get(company, "#888")
    for fy in selected_fy:
        mask = (df["company"] == company) & (df["fiscal_year"] == fy)
        df_line = df[mask].sort_values("announced_date").reset_index(drop=True)
        if df_line.empty:
            continue

        is_actual = df_line["notes"].str.contains("Actual full-year", na=False)
        is_completed = fy in COMPLETED_FY

        # Error bar arrays — zero where no range given
        err_plus, err_minus = [], []
        for _, row in df_line.iterrows():
            if pd.notna(row.get("guidance_high")) and pd.notna(row.get("guidance_low")):
                err_plus.append(float(row["guidance_high"]) - float(row["guidance_usd_b"]))
                err_minus.append(float(row["guidance_usd_b"]) - float(row["guidance_low"]))
            else:
                err_plus.append(0)
                err_minus.append(0)

        # FY label at rightmost point only
        text_labels = [""] * len(df_line)
        text_labels[-1] = fy

        first_for_company = company not in _legend_shown
        _legend_shown.add(company)

        fig.add_trace(go.Scatter(
            x=df_line["announced_date"],
            y=df_line["guidance_usd_b"],
            mode="lines+markers+text",
            name=company,
            legendgroup=company,
            showlegend=first_for_company,
            text=text_labels,
            textposition="middle right",
            textfont=dict(color=color, size=10),
            line=dict(
                color=color,
                width=2,
                dash="dash" if is_completed else "solid",
            ),
            marker=dict(
                color=color,
                size=[12 if a else 8 for a in is_actual],
                symbol=["star" if a else "circle" for a in is_actual],
                line=dict(color=annotation_color, width=1),
            ),
            error_y=dict(
                type="data",
                symmetric=False,
                array=err_plus,
                arrayminus=err_minus,
                visible=True,
                color=color,
                thickness=1.5,
                width=4,
            ),
            customdata=df_line[["fiscal_year", "source", "notes"]].values,
            hovertemplate=(
                f"<b>{company} {fy}</b><br>"
                "Date: %{x|%b %d, %Y}<br>"
                "Guidance: $%{y:.1f}B<br>"
                "Source: %{customdata[1]}<br>"
                "Notes: %{customdata[2]}<br>"
                "<extra></extra>"
            ),
        ))

# Marker key entries — star = actual, dashed = completed
fig.add_trace(go.Scatter(
    x=[None], y=[None], mode="markers",
    name="★  Reported actual",
    marker=dict(symbol="star", size=12, color="white", line=dict(color="gray", width=1)),
    showlegend=True,
))
fig.add_trace(go.Scatter(
    x=[None], y=[None], mode="lines",
    name="╌  Completed year",
    line=dict(color="gray", width=2, dash="dash"),
    showlegend=True,
))

fig.update_layout(
    template=template,
    xaxis_title="Announcement Date",
    yaxis_title="CAPEX Guidance ($B)",
    legend=dict(orientation="v", x=1.01, y=1, font=dict(size=11)),
    height=520,
    margin=dict(r=160, t=30),
    hovermode="closest",
)
fig.update_yaxes(rangemode="tozero")

st.plotly_chart(fig, use_container_width=True)

# ── Revision summary bar chart ────────────────────────────────────────────────
st.subheader("Revision Summary")
st.caption(
    "First guidance issued vs final reported actual, with net revision shown. "
    "Bars grouped by company × fiscal year."
)

summary_rows = []
for company in selected_companies:
    for fy in sorted(selected_fy):
        mask = (df["company"] == company) & (df["fiscal_year"] == fy)
        df_fy = df[mask].sort_values("announced_date").reset_index(drop=True)
        if df_fy.empty:
            continue

        is_actual_mask = df_fy["notes"].str.contains("Actual full-year", na=False)
        df_guidance = df_fy[~is_actual_mask]
        df_actual   = df_fy[is_actual_mask]

        if df_guidance.empty:
            continue

        first_val  = float(df_guidance.iloc[0]["guidance_usd_b"])
        latest_val = float(df_guidance.iloc[-1]["guidance_usd_b"])
        actual_val = float(df_actual.iloc[-1]["guidance_usd_b"]) if not df_actual.empty else None
        n_revisions = len(df_guidance) - 1

        summary_rows.append({
            "label":       f"{company}<br>{fy}",
            "company":     company,
            "fy":          fy,
            "first":       first_val,
            "latest":      latest_val,
            "actual":      actual_val,
            "n_revisions": n_revisions,
            "net_change":  (actual_val or latest_val) - first_val,
        })

if summary_rows:
    x_labels = [r["label"] for r in summary_rows]

    fig_sum = go.Figure()

    # First guidance
    fig_sum.add_trace(go.Bar(
        name="First guidance",
        x=x_labels,
        y=[r["first"] for r in summary_rows],
        marker_color="rgba(107, 114, 128, 0.7)",
        hovertemplate="<b>%{x}</b><br>First guidance: $%{y:.1f}B<extra></extra>",
    ))

    # Latest non-actual guidance (only where it differs from first)
    latest_y = [
        r["latest"] if r["latest"] != r["first"] else None
        for r in summary_rows
    ]
    if any(v is not None for v in latest_y):
        fig_sum.add_trace(go.Bar(
            name="Latest guidance",
            x=x_labels,
            y=latest_y,
            marker_color="rgba(59, 130, 246, 0.8)",
            hovertemplate="<b>%{x}</b><br>Latest guidance: $%{y:.1f}B<extra></extra>",
        ))

    # Reported actual
    actual_y = [r["actual"] for r in summary_rows]
    if any(v is not None for v in actual_y):
        fig_sum.add_trace(go.Bar(
            name="★ Reported actual",
            x=x_labels,
            y=actual_y,
            marker_color="rgba(34, 197, 94, 0.85)",
            hovertemplate="<b>%{x}</b><br>Reported actual: $%{y:.1f}B<extra></extra>",
        ))

    # Net revision annotations above each group
    for i, r in enumerate(summary_rows):
        end_val = r["actual"] if r["actual"] is not None else r["latest"]
        delta   = end_val - r["first"]
        if delta == 0:
            continue
        sign  = "+" if delta > 0 else "−"
        color = "#22c55e" if delta > 0 else "#ef4444"
        fig_sum.add_annotation(
            x=r["label"],
            y=end_val,
            text=f"<b>{sign}${abs(delta):.0f}B</b>",
            showarrow=False,
            yshift=10,
            font=dict(size=11, color=color),
        )

    fig_sum.update_layout(
        template=template,
        barmode="group",
        yaxis_title="CAPEX ($B)",
        yaxis=dict(rangemode="tozero"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        height=400,
        margin=dict(t=50, r=20, b=20),
        hovermode="x unified",
    )
    st.plotly_chart(fig_sum, use_container_width=True)

# ── Apple / Microsoft caveat ──────────────────────────────────────────────────
caveats = []
if "Apple" in selected_companies:
    caveats.append("**Apple** does not issue formal annual CAPEX guidance — figures shown are analyst consensus (FactSet).")
if "Microsoft" in selected_companies:
    caveats.append("**Microsoft** gives directional guidance only (no explicit annual figure) — FY2026 $120B is analyst consensus based on H1 run-rate.")
if caveats:
    st.info("  \n".join(caveats))

# ── Revision detail table ─────────────────────────────────────────────────────
st.subheader("Revision Detail")

tbl = df.sort_values(["company", "fiscal_year", "announced_date"]).copy()

# Delta vs prior revision within same (company, fiscal_year)
tbl["delta"] = tbl.groupby(["company", "fiscal_year"])["guidance_usd_b"].diff()

def _fmt_delta(d):
    if pd.isna(d):
        return "—"
    sign = "+" if d > 0 else ("−" if d < 0 else "")
    return f"{sign}${abs(d):.1f}B"

def _fmt_range(row):
    if pd.notna(row.get("guidance_low")) and pd.notna(row.get("guidance_high")):
        return f"${row['guidance_low']:.0f}–{row['guidance_high']:.0f}B"
    return ""

tbl["guidance_fmt"] = tbl["guidance_usd_b"].apply(lambda x: f"${x:.1f}B")
tbl["range_fmt"] = tbl.apply(_fmt_range, axis=1)
tbl["delta_fmt"] = tbl["delta"].apply(_fmt_delta)
tbl["date_fmt"] = tbl["announced_date"].dt.strftime("%b %d, %Y")

display = tbl[[
    "company", "fiscal_year", "date_fmt",
    "guidance_fmt", "range_fmt", "delta_fmt",
    "source", "notes",
]].rename(columns={
    "company": "Company",
    "fiscal_year": "Fiscal Year",
    "date_fmt": "Date",
    "guidance_fmt": "Guidance",
    "range_fmt": "Range",
    "delta_fmt": "vs Prior",
    "source": "Source",
    "notes": "Notes",
})

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Notes": st.column_config.TextColumn(width="large"),
        "Source": st.column_config.TextColumn(width="medium"),
    },
)
