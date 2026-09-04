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

from app.lib.llm_perf import chart_layout
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

# ---- Main chart: Top Models — weekly stacked bars (OpenRouter rankings) ----
NAMED_SERIES = 9
NAME_FIXES = {"Gpt": "GPT", "Openai": "OpenAI", "Deepseek": "DeepSeek",
              "Xai": "xAI", "Glm": "GLM", "Ai": "AI", "Llm": "LLM"}


def _short_name(slug: str) -> str:
    """'deepseek/deepseek-r1-0528' -> 'DeepSeek R1 0528'; 'other' -> 'Others'."""
    if slug == "other":
        return "Others"
    words = slug.split("/", 1)[-1].replace("-", " ").replace("_", " ").split()
    return " ".join(NAME_FIXES.get(w.capitalize(), w.capitalize()) for w in words)


wk = df.copy()
wk["week"] = wk["date"] - pd.to_timedelta(wk["date"].dt.dayofweek, unit="D")  # Mon-based
top_models = wk.groupby("model")["total_tokens"].sum().sort_values(ascending=False)
named = [m for m in top_models.index if m != "other"][:NAMED_SERIES]
wk["series"] = wk["model"].where(wk["model"].isin(named), "other")
piv = (
    wk.pivot_table(index="week", columns="series", values="total_tokens", aggfunc="sum")
    .fillna(0).sort_index()
)
latest_week = piv.index.max()
named_by_latest = piv.loc[latest_week, named].sort_values(ascending=False).index.tolist()
series_order = ["other"] + named_by_latest

# Vivid categorical palette in the spirit of openrouter.ai/rankings; long tail pink at base.
MODEL_PALETTE = ["#f97316", "#4ade80", "#facc15", "#3b82f6", "#8b5cf6",
                 "#38bdf8", "#f472b6", "#14b8a6", "#e879f9"]
series_colour = {"other": "#ec4899"}
series_colour.update({m: c for m, c in zip(named_by_latest, MODEL_PALETTE)})

data_end = df["date"].max()
partial_last = data_end < latest_week + pd.Timedelta(days=6)
bar_width_ms = int(4.6 * 86400 * 1000)


def _bar_trace(s: str, use_pattern: bool) -> go.Bar:
    disp = _short_name(s)
    marker = dict(color=series_colour[s], line=dict(width=0))
    if use_pattern and partial_last:
        marker["pattern"] = dict(shape=["/" if w == latest_week else "" for w in piv.index])
    return go.Bar(
        x=piv.index, y=piv[s], name=disp, width=bar_width_ms, marker=marker,
        customdata=[fmt_tokens(float(v)) for v in piv[s]],
        hovertemplate="%{x|%b %d, %Y}<br>%{customdata} tokens<extra>" + disp + "</extra>",
    )


fig = go.Figure()
try:
    for s in series_order:
        fig.add_trace(_bar_trace(s, use_pattern=True))
except ValueError:  # per-point pattern not supported on this plotly build -> dim the partial week
    fig = go.Figure()
    for s in series_order:
        fig.add_trace(_bar_trace(s, use_pattern=False))
    if partial_last:
        for tr in fig.data:
            tr.marker.opacity = [0.45 if w == latest_week else 1.0 for w in piv.index]

fig.update_layout(
    barmode="stack", showlegend=False, hovermode="x unified",
    title="Top Models — weekly token usage across OpenRouter",
    xaxis_title="", yaxis_title="",
    height=440, **CHART_LAYOUT,
)
tick_i = list(range(0, len(piv), 5))
fig.update_xaxes(
    tickvals=[piv.index[i] for i in tick_i],
    ticktext=[
        piv.index[i].strftime("%b %d, %Y") if i == 0 else piv.index[i].strftime("%b %d")
        for i in tick_i
    ],
    showgrid=False, showline=False,
)
fig.update_yaxes(showgrid=False, zeroline=False, tickformat="~s")  # 30T / 60T / 90T style
if st.radio("Scale", ["Linear", "Log"], horizontal=True, label_visibility="collapsed") == "Log":
    fig.update_yaxes(type="log")


def _week_breakdown(col, week: pd.Timestamp) -> None:
    """Pinned latest-week breakdown panel (the source's tooltip/legend card)."""
    rows = "".join(
        "<div style='display:flex;align-items:center;gap:7px;padding:2.5px 0'>"
        f"<span style='width:9px;height:9px;border-radius:50%;background:{series_colour[s]};flex:none'></span>"
        f"<span style='flex:1;color:#d4d4d4;font-size:12.5px;white-space:nowrap;overflow:hidden;"
        f"text-overflow:ellipsis'>{_short_name(s)}</span>"
        f"<span style='color:#fafafa;font-size:12.5px;font-variant-numeric:tabular-nums'>{fmt_tokens(float(piv.loc[week, s]))}</span>"
        "</div>"
        for s in series_order
    )
    html = (
        "<div style='border:1px solid #2f2f2f;border-radius:10px;background:#1a1a1a;padding:12px 14px'>"
        f"<div style='display:inline-block;border:1px solid #3a3a3a;border-radius:6px;padding:2px 10px;"
        f"font-size:12px;color:#fafafa;margin-bottom:10px'>Week of {week.strftime('%B %d, %Y')}</div>"
        + rows
        + "<hr style='border:none;border-top:1px solid #2f2f2f;margin:8px 0 6px'>"
        "<div style='display:flex;justify-content:space-between;font-size:13px'>"
        "<span style='color:#fafafa;font-weight:600'>Total</span>"
        f"<span style='color:#fafafa;font-weight:600'>{fmt_tokens(float(piv.loc[week].sum()))}</span></div>"
        "</div>"
    )
    col.markdown(html, unsafe_allow_html=True)


st.caption(
    "Weekly tokens stacked by model — top 9 by cumulative volume plus the aggregated long tail. "
    "Weeks start Monday"
    + (
        f"; the final bar covers a partial week (data through {data_end.date().isoformat()})."
        if partial_last else "."
    )
)
chart_col, panel_col = st.columns([3.4, 1], gap="small")
chart_col.plotly_chart(fig, use_container_width=True)
_week_breakdown(panel_col, latest_week)

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
