"""Australian Data Centre Analysis — Section landing page."""

import streamlit as st
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "au_dc" / "processed"

projects_exists = (DATA_DIR / "projects.parquet").exists()
dc_demand_exists = (DATA_DIR / "dc_demand.parquet").exists()
grid_exists = (DATA_DIR / "grid_capacity.parquet").exists()

st.title("Australian Data Centre Analysis")
st.markdown("*Market intelligence built from public data sources*")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Data Layers", f"{'✓' if projects_exists else '✗'} Projects")
with col2:
    st.metric("Data Layers", f"{'✓' if dc_demand_exists else '✗'} DC Demand")
with col3:
    st.metric("Data Layers", f"{'✓' if grid_exists else '✗'} Grid Capacity")

st.markdown("---")
st.markdown("""
### Navigation
Use the sidebar to navigate between sections:
- **Market Overview** — Headline KPIs, capacity trends, market breakdown
- **Regional Analysis** — Power & supply trends, DC demand vs grid capacity
- **Company Analysis** — Operator profiles, market share
- **Project Analysis** — Full project database with filtering

### Data Sources
All data is sourced from publicly available information:
- AEMO Generation Information, ESOO, ISP/IASR
- Oxford Economics / AEMO Data Centre Energy Demand report
- CEFC/Baringa "Getting the Balance Right" report
- ASX/NZX filings (NEXTDC, Infratil, Goodman, Macquarie Technology)
- NSW Planning Portal (State Significant Development applications)
- Company press releases and websites
""")
