"""
Lane 6: Supply Chain Mapping — concentration, lead times, geopolitics.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px

st.title("Supply Chain Mapping")

tab_conc, tab_lead, tab_geo, tab_deep = st.tabs(["Concentration", "Lead Times", "Geopolitical", "Deep Dive"])

with tab_conc:
    st.header("Supply Chain Concentration — Risk-Scored")
    conc_data = pd.DataFrame([
        ("EUV Lithography", "ASML", 100, "Sole source", 4.75),
        ("Advanced Fab (<7nm)", "TSMC", 90, "Sole source", 4.75),
        ("CoWoS Packaging", "TSMC", 95, "Sole source", 4.50),
        ("ABF Film", "Ajinomoto", 95, "Sole source", 3.75),
        ("HBM3e Memory", "SK Hynix", 90, "Single source", 3.75),
        ("InfiniBand", "NVIDIA Mellanox", 90, "Single source", 3.50),
        ("ABF Substrate", "Ibiden", 75, "Single source", 3.25),
        ("GPU Training", "NVIDIA", 95, "Single source", 3.50),
        ("Transformers", "Multiple", 60, "Oligopoly", 2.25),
        ("Generators", "Caterpillar/Cummins", 80, "Duopoly", 1.75),
    ], columns=["Component", "Dominant Supplier", "Share %", "Type", "Score"])

    fig_conc = px.bar(conc_data.sort_values("Score"), x="Score", y="Component", orientation="h",
        color="Score", color_continuous_scale=["#22c55e", "#f59e0b", "#ef4444"], range_color=[1, 5], text="Score")
    fig_conc.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    fig_conc.update_layout(height=450, xaxis=dict(range=[0, 5.5]), showlegend=False, margin=dict(l=20, r=40, t=10, b=0))
    st.plotly_chart(fig_conc, use_container_width=True)
    st.caption("Score = f(Supplier Concentration, Lead Time Risk, Geopolitical Risk, Economic Impact). >=3.5 = Extreme/High.")

    st.dataframe(conc_data.sort_values("Score", ascending=False), use_container_width=True, hide_index=True)

with tab_lead:
    st.header("Component Lead Times — Construction Loan Impact")
    lead_data = pd.DataFrame([
        ("Transformers", "140-160+ weeks", "Must order before loan close"),
        ("Generators", "52-104 weeks", "Long lead. Diesel vs gas turbine options."),
        ("EUV Lithography Tools", "~78 weeks", "ASML backlog. Only affects new fabs."),
        ("CoWoS Packaging Capacity", "52-78 weeks", "New capacity takes 18+ months."),
        ("ABF Substrates", "26-52 weeks", "Expanding but demand growing faster."),
        ("HBM Memory", "16-26 weeks", "Currently sold out. New capacity 12-18 months."),
        ("GPU (NVIDIA)", "12-20 weeks", "Volume allocation is the real constraint."),
        ("Optical Transceivers", "8-16 weeks", "Commodity supply."),
        ("Networking Switches", "8-16 weeks", "Lead time not binding constraint."),
    ], columns=["Component", "Lead Time", "Assessment"])
    st.dataframe(lead_data, use_container_width=True, hide_index=True)
    st.warning("Transformers are the longest-lead item at 140-160+ weeks (3+ years). Verify transformer orders placed AND confirmed delivery dates before funding construction draws.")

with tab_geo:
    st.header("Geopolitical Risk Matrix")
    geo_data = pd.DataFrame([
        ("Taiwan Strait", "High", "Very High", "TSMC (fab+packaging), ASE, >90% advanced chips"),
        ("China Export Controls", "Moderate", "High", "NVIDIA H100/B200, ASML tools to China"),
        ("South Korea Instability", "Low-Mod", "High", "SK Hynix (HBM3e >90%), Samsung (HBM)"),
        ("Japan Supply Disruption", "Low", "Moderate", "Ibiden (substrates), Ajinomoto (ABF film)"),
        ("Netherlands Export Policy", "Moderate", "Moderate", "ASML EUV tools. NL government controls."),
    ], columns=["Risk", "Probability", "Impact", "What is at Risk"])
    st.dataframe(geo_data, use_container_width=True, hide_index=True)

    st.subheader("Stress Test Scenarios")
    stress_data = pd.DataFrame([
        ("Taiwan blockade (>1 month)", "Low (5-10%)", "Catastrophic", "Global chip supply halts. >90% advanced chips in Taiwan."),
        ("SK Hynix production halt", "Low-Mod (10-15%)", "Severe", "HBM3e supply stops. >90% from SK Hynix."),
        ("CoWoS capacity stall", "Moderate (20-30%)", "Significant", "Packaging bottleneck tightens. TSMC single point."),
        ("Transformer lead time extension", "High (40-50%)", "Moderate", "DC construction delayed 3+ years."),
        ("China export control escalation", "Mod-High (30-40%)", "Moderate", "NVIDIA revenue impacted. Huawei Ascend domestic alt."),
    ], columns=["Scenario", "Probability", "Credit Impact", "Description"])
    st.dataframe(stress_data, use_container_width=True, hide_index=True)

with tab_deep:
    st.header("Deep Dive")

    with st.expander("Sole Source vs Single Source"):
        st.markdown("""
**Sole source:** Only one supplier CAN supply the component. No alternative exists at any scale. Examples: ASML (EUV lithography), Ajinomoto (ABF film).

**Single source:** Only one supplier IS supplying, but alternatives could theoretically emerge. Examples: SK Hynix (HBM3e — Samsung could compete), NVIDIA (GPUs — AMD could compete).

**Credit distinction:** Sole source risk cannot be mitigated through diversification. Single source risk can be, given time and investment. A borrower whose supply chain has sole source dependencies has unhedgeable concentration risk.

**Risk hierarchy:**
1. Sole source with no roadmap for alternatives: **Maximum risk** (ASML EUV, Ajinomoto ABF film)
2. Sole source with credible alternative timeline: **High risk** (TSMC CoWoS -> UCIe standardisation 2027+)
3. Single source with high barriers: **Elevated risk** (SK Hynix HBM3e -> Samsung/Micron ramp)
4. Single source with active competition: **Moderate risk** (NVIDIA GPU -> AMD/ASIC competition)
5. Oligopoly/competitive supply: **Low risk** (transformers, generators, networking switches)
        """)

    with st.expander("Manufacturing Economics — Yield & Binning"):
        st.markdown("""
**Die yield:** Not every die on a wafer works. Yield rates by process node:
- N5 (mature): ~90% good dies per wafer
- N3 (early ramp): ~60-80%
- N2 (projected early ramp): ~50-70%

**Binning:** Working dies are tested and sorted into performance bins. A single wafer yields multiple SKUs:
- H100 (fully functional, highest bin)
- H100-NVL (slightly lower bin, optimised for NVL)
- H800 (reduced interconnect, for China export compliance)
- Harvested dies (some cores disabled, sold as lower SKU)

**Tape-out to volume:** 12-18 months from final design to volume production. This lag means credit officers evaluating a construction loan for next-gen GPU clusters must understand that the GPUs being manufactured today were designed 18 months ago.

**Wafer allocation:** NVIDIA, AMD, Apple, Intel, Qualcomm all compete for the same TSMC wafers. TSMC's pricing power is substantial — wafer prices have risen from ~$3K (28nm) to ~$20K+ (N3) to projected ~$45K (A16).
        """)

    with st.expander("Credit Implications"):
        st.markdown("""
**Concentration risk scoring:** 6 components score 3.5+ (Extreme/High risk) — EUV, Advanced Fab, CoWoS, ABF Film, HBM3e, InfiniBand. A supply disruption at any of these halts AI hardware shipments.

**Lead time risk:** Transformers at 140-160+ weeks must be ordered before loan close. This is a hard gate — no amount of money accelerates delivery. Verification of transformer orders should be a condition precedent to construction drawdowns.

**Geopolitical risk:** Taiwan concentration (>90% advanced chips) is the single largest non-diversifiable risk in AI hardware lending. China export controls, South Korea stability, and Netherlands export policy are additional layers.

**Stress testing:** Portfolios should be stress-tested against the scenarios above. Taiwan blockade is low-probability but catastrophic-impact. Transformer lead time extension is higher-probability but moderate-impact.
        """)
