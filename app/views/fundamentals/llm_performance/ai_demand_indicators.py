"""AI Demand Indicators — user growth and token consumption as bubble-risk signals."""
from __future__ import annotations

from pathlib import Path

import plotly.express as px
import streamlit as st

_DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "reference"

st.title("AI Demand Indicators")
st.caption(
    "User growth is the clearest leading indicator of whether AI revenue can sustain current CAPEX levels. "
    "Rising users without commensurate monetisation would be a key bubble-risk signal."
)

token_path = _DATA_DIR / "token_consumption.csv"
if token_path.exists():
    import pandas as pd
    df_tokens = pd.read_csv(token_path)
    df_tokens["date"] = pd.to_datetime(df_tokens["date"])

    st.subheader("Frontier Model User Growth")
    st.caption(
        "Mix of weekly active users (OpenAI) and monthly active users (Anthropic, Google, xAI) "
        "— compare directionally, not precisely."
    )
    df_users = df_tokens[df_tokens["metric"].str.contains("active_users")].copy()
    if not df_users.empty:
        df_users["value_m"] = df_users["value"] / 1e6
        fig_users = px.scatter(
            df_users, x="date", y="value_m", color="provider",
            size="value_m", title="Active Users (Millions)",
            labels={"value_m": "Users (M)", "date": ""},
        )
        fig_users.update_traces(marker=dict(sizemin=5))
        fig_users.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_users, use_container_width=True)
    else:
        st.info("No active user data found in token_consumption.csv.")
else:
    st.info("token_consumption.csv not found — run /ai-research to populate.")
