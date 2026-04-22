"""LLM Leaderboard — frontier models ranked by composite benchmark score."""
from __future__ import annotations

import streamlit as st

from app.lib.llm_perf import BENCH_COLS, fetch_zeroeval_models, chart_layout  # noqa: F401

ze_df = fetch_zeroeval_models()
CHART_LAYOUT = chart_layout()

st.title("LLM Leaderboard")
st.caption(
    "Frontier models ranked by composite benchmark score (mean of GPQA, SWE-Bench Verified, HLE, AIME-2025). "
    "Live data from [LLM Stats](https://llm-stats.com) · updated hourly."
)

if ze_df.empty:
    st.info("Live data unavailable — ZeroEval API offline.")
else:
    lb = ze_df.copy()
    lb["composite_score"] = lb[BENCH_COLS].mean(axis=1, skipna=True).mul(100).round(1)
    lb = lb.dropna(subset=["composite_score"])
    lb = lb.sort_values("composite_score", ascending=False).reset_index(drop=True)
    lb["rank"] = range(1, len(lb) + 1)
    lb["type"] = lb["license"].apply(lambda x: "Closed" if x == "proprietary" else "Open")
    lb["context_k"] = (lb["context"].fillna(0) / 1000).round(0)

    display = {
        "#": lb["rank"],
        "Model": lb["name"],
        "Org": lb["organization"],
        "Type": lb["type"],
        "Score": lb["composite_score"],
        "GPQA": (lb["gpqa_score"] * 100).round(1),
        "AIME '25": (lb["aime_2025_score"] * 100).round(1),
        "SWE-Bench": (lb["swe_bench_verified_score"] * 100).round(1),
        "HLE": (lb["hle_score"] * 100).round(1),
        "In $/M": lb["input_price"],
        "Out $/M": lb["output_price"],
        "Ctx (K)": lb["context_k"],
        "Speed": lb["throughput"],
    }
    import pandas as pd
    st.dataframe(
        pd.DataFrame(display),
        use_container_width=True,
        hide_index=True,
        height=500,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Model": st.column_config.TextColumn(width="medium"),
            "Org": st.column_config.TextColumn(width="small"),
            "Type": st.column_config.TextColumn(width="small"),
            "Score": st.column_config.NumberColumn(format="%.1f", width="small"),
            "GPQA": st.column_config.NumberColumn(format="%.1f%%"),
            "AIME '25": st.column_config.NumberColumn(format="%.1f%%"),
            "SWE-Bench": st.column_config.NumberColumn(format="%.1f%%"),
            "HLE": st.column_config.NumberColumn(format="%.1f%%"),
            "In $/M": st.column_config.NumberColumn(format="$%.2f"),
            "Out $/M": st.column_config.NumberColumn(format="$%.2f"),
            "Ctx (K)": st.column_config.NumberColumn(format="%dK"),
            "Speed": st.column_config.NumberColumn(format="%d tok/s"),
        },
    )
    st.caption(
        f"[LLM Stats](https://llm-stats.com) / api.zeroeval.com · {len(lb)} models · "
        "Score = mean(GPQA, SWE-Bench, HLE, AIME-2025) as %. Blanks = no published score. Speed in tokens/sec."
    )
    st.markdown("")
    st.caption(
        "Charts on the other LLM Performance pages use live data from "
        "[LLM Stats](https://llm-stats.com) via api.zeroeval.com."
    )
