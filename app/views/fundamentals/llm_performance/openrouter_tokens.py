"""OpenRouter Token Traffic — platform-wide aggregate token usage by model.

Replicates the shape of the a16z / OpenRouter rankings chart ("agents are using
far more tokens than people") with the public, verifiable data OpenRouter
actually exposes: per-day total tokens for the top 50 models + long tail.

Data source: OpenRouter Datasets API — openrouter.ai/docs/api/api-reference/datasets
Refreshed by: scripts/refresh_openrouter_usage.py (daily)
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.lib.llm_perf import PROVIDER_COLOURS, chart_layout
from app.lib.openrouter_usage import (
    CSV_PATH, META_PATH,
    daily_totals, fmt_tokens, load_rankings_daily, load_usage_meta,
    org_to_provider, provider_colour, provider_series,
)

CHART_LAYOUT = chart_layout()

SOURCE_LINE = (
    "Source: [OpenRouter Datasets API](https://openrouter.ai/docs/api/api-reference/datasets) "
    "(rankings-daily) · [Live rankings](https://openrouter.ai/rankings)"
)


def _csv_mtime() -> float:
    try:
        return CSV_PATH.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(ttl=60, show_spinner=False)
def _load_data(_mtime: float) -> tuple[pd.DataFrame, dict]:
    return load_rankings_daily(), load_usage_meta()


st.title("OpenRouter Token Traffic")
st.caption("Platform-wide daily token throughput across OpenRouter — the empirical pulse of AI model usage.")
st.markdown(SOURCE_LINE, unsafe_allow_html=True)

df, meta = _load_data(_csv_mtime())
if df.empty:
    st.info(
        "No OpenRouter dataset yet. Run the daily refresh to fetch it:\n\n"
        "```bash\n"
        "python scripts/refresh_openrouter_usage.py\n"
        "```\n\n"
        "Requires an OpenRouter API key (any key authenticates the datasets endpoint) — "
        "set `OPENROUTER_API_KEY` or store it in macOS Keychain as service `openrouter-api`."
    )
    st.stop()

total = daily_totals(df)
latest_day = total["date"].max()
as_of = meta.get("data_end") or latest_day.date().isoformat()

# ---- Stat cards -----------------------------------------------------------
sev = total.set_index("date")["total_tokens"].rolling(7).mean()
latest_7 = sev.iloc[-1]
full_7 = sev.dropna()
if len(full_7) >= 2:
    start_7 = full_7.iloc[0]
    growth = latest_7 / start_7 if start_7 > 0 else float("nan")
else:
    start_7, growth = float("nan"), float("nan")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest 7-day avg (tokens/day)", fmt_tokens(latest_7))
c2.metric(f"Latest full day ({as_of})", fmt_tokens(float(total.loc[total['date'] == latest_day, 'total_tokens'].sum())))
c3.metric("Cumulative since dataset start", fmt_tokens(float(total["total_tokens"].sum())))
c4.metric(
    "Growth vs dataset start",
    f"{growth:.1f}×" if pd.notna(growth) else "—",
    delta_color="off",
)

st.markdown(
    "<small style='color:#888'>**What it shows.** Aggregate tokens processed per day through the "
    "OpenRouter API (prompt + completion, native tokenizers), summed across the top 50 models and "
    "the long-tail `other` bucket. **Why it matters.** Token throughput is the closest public proxy "
    "for real LLM adoption and workload growth — free of benchmark self-reporting. "
    "**Caveats.** OpenRouter traffic only, not whole-market; volumes include free-tier models, so "
    "token share ≠ spend share; the top-50 membership can change day to day.</small>",
    unsafe_allow_html=True,
)

# ---- Main trend chart (a16z-style 7-day average) ---------------------------
sm = st.checkbox("Show 7-day rolling average", value=True)
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=total["date"], y=total["total_tokens"],
    mode="lines", name="Daily total",
    line=dict(color=PROVIDER_COLOURS["DeepSeek"], width=1.2),
    hovertemplate="%{x|%b %d, %Y}: %{y:,.0f} tokens<extra></extra>",
))
if sm:
    fig.add_trace(go.Scatter(
        x=sev.index, y=sev.values,
        mode="lines", name="7-day average",
        line=dict(color="#3b82f6", width=3),
        hovertemplate="7-day avg %{x|%b %d, %Y}: %{y:,.0f} tokens<extra></extra>",
    ))
    if pd.notna(growth):
        fig.add_annotation(
            x=sev.index[-1], y=latest_7,
            text=f"{growth:.1f}× vs start of dataset",
            showarrow=False, xshift=12, yshift=10,
            font=dict(size=11, color="#3b82f6"),
        )
fig.update_layout(
    title="Daily tokens processed through OpenRouter",
    xaxis_title="", yaxis_title="Tokens / day",
    height=420, **CHART_LAYOUT,
)
fig.update_yaxes(tickformat=".2s")
st.plotly_chart(fig, use_container_width=True)

# ---- Provider share ---------------------------------------------------------
st.subheader("Share by provider")
ps = provider_series(df, top_n=7)
providers = [p for p in ps["provider"].unique() if p != "Other (long tail)"]
providers = sorted(
    providers,
    key=lambda p: ps.loc[ps["provider"] == p, "total_tokens"].sum(),
    reverse=True,
) + ["Other (long tail)"]

fig2 = go.Figure()
for p in providers:
    sub = ps[ps["provider"] == p]
    fig2.add_trace(go.Scatter(
        x=sub["date"], y=sub["total_tokens"],
        name=p, mode="lines", stackgroup="one",
        line=dict(width=0.5, color=provider_colour(p)),
        hovertemplate="%{x|%b %d, %Y}<br>%{y:,.0f} tokens<extra>" + p + "</extra>",
    ))
fig2.update_layout(
    title="Daily tokens by provider (stacked, top 7 + long tail)",
    xaxis_title="", yaxis_title="Tokens / day",
    height=420, **CHART_LAYOUT,
)
fig2.update_yaxes(tickformat=".2s")
st.plotly_chart(fig2, use_container_width=True)

# ---- Top models table -------------------------------------------------------
st.subheader("Top models by day")
days = sorted(df["date"].dt.date.unique(), reverse=True)
pick = st.selectbox("Day (UTC)", days, index=0, format_func=lambda d: d.isoformat())
day_df = df[df["date"].dt.date == pick].copy()
day_df = day_df.sort_values("total_tokens", ascending=False).head(25).reset_index(drop=True)
day_total = day_df["total_tokens"].sum()
day_df.insert(0, "rank", range(1, len(day_df) + 1))
day_df["share"] = day_df["total_tokens"] / day_total * 100
day_df["model"] = day_df["model"].apply(lambda m: "long-tail `other`" if m == "other" else m)
day_df["provider"] = day_df["org"].map(org_to_provider)
table = day_df[["rank", "model", "provider", "total_tokens", "share"]]
st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "rank": "Rank",
        "model": "Model (OpenRouter slug)",
        "provider": "Provider",
        "total_tokens": st.column_config.NumberColumn("Tokens (day)", format="%d"),
        "share": st.column_config.NumberColumn("Share of day", format="%.2f%%"),
    },
)
st.caption(
    f"Top 25 of the day's dataset rows; the dataset's own `other` row aggregates every model "
    f"outside the top 50. Dataset window: {meta.get('data_start', '—')} → {meta.get('data_end', '—')}"
    f" · pulled {meta.get('updated', '—')} · {meta.get('days', '—')} days · {meta.get('rows', '—')} rows."
)
