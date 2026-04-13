"""DC Power Demand Forecasts."""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reference"

st.title("Power")
st.caption(
    "Power constraint — not silicon — is now the binding constraint on hyperscale AI clusters. "
    "All major forecasters project near-doubling of data centre power demand by 2030. "
    "The key risk: if power build-out falls behind, CAPEX commitments become stranded."
)

st.header("DC Power Demand Forecasts")

power_path = DATA_DIR / "dc_power_forecasts.csv"
if power_path.exists():
    df_power = pd.read_csv(power_path)

    col1, col2 = st.columns(2)
    with col1:
        df_global = df_power[df_power["region"] == "Global"]
        if not df_global.empty:
            fig_global = px.line(df_global, x="year", y="demand_twh", color="source", line_dash="scenario",
                                  markers=True, title="Global DC Power Demand (TWh)",
                                  labels={"demand_twh": "TWh", "year": "Year"})
            fig_global.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_global, use_container_width=True)

    with col2:
        df_us = df_power[df_power["region"].isin(["United States", "PJM Interconnect", "Texas"])]
        if not df_us.empty:
            fig_us = px.line(df_us, x="year", y="demand_twh", color="region", line_dash="source",
                              markers=True, title="US / Regional DC Power Demand (TWh)",
                              labels={"demand_twh": "TWh", "year": "Year"})
            fig_us.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig_us, use_container_width=True)

    with st.expander("Full Forecast Data"):
        st.dataframe(df_power[["source", "region", "year", "demand_twh", "scenario", "notes"]],
                      use_container_width=True, hide_index=True)
else:
    st.warning("DC power forecasts CSV missing (data/reference/dc_power_forecasts.csv).")
