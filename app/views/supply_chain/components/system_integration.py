"""
Lane 5: System Integration — DGX to data centre. TCO, reliability, cooling.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px

st.title("System Integration")

tab_tco, tab_rel, tab_cool, tab_deep = st.tabs(["TCO Framework", "Reliability", "Power & Cooling", "Deep Dive"])

with tab_tco:
    st.header("Cluster TCO — 1 GW Facility Example")
    tco_data = pd.DataFrame([
        ("GPU Servers", 3200, 37.6), ("Networking", 1200, 14.1),
        ("Storage & Servers", 400, 4.7), ("Power & Cooling Infra", 600, 7.1),
        ("Building & Land", 2100, 24.7), ("Power (Electricity)", 700, 8.2),
        ("Operations & Staff", 300, 3.5),
    ], columns=["Category", "Annual Cost ($M/yr)", "% of TCO"])
    fig_tco = px.pie(tco_data, values="Annual Cost ($M/yr)", names="Category",
        title="1 GW AI Cluster — Annual TCO ($8.5B/yr)",
        color_discrete_sequence=["#3b82f6", "#8b5cf6", "#22c55e", "#f59e0b", "#6b7280", "#ef4444", "#06b6d4"])
    fig_tco.update_layout(height=420, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig_tco, use_container_width=True)
    st.dataframe(tco_data, use_container_width=True, hide_index=True)

    st.subheader("Depreciation Mismatch Risk")
    depr_data = pd.DataFrame([
        ("GPU (H100/B200)", "3-6 years accounting", "18-36 months economic", "CRITICAL"),
        ("Networking", "5-7 years", "5+ years", "Moderate"),
        ("Power/Cooling Infra", "10-15 years", "10-15 years", "Low"),
        ("Building Shell", "25-40 years", "25-40+ years", "Very Low"),
    ], columns=["Asset", "Accounting Life", "Economic Life", "Risk"])
    st.dataframe(depr_data, use_container_width=True, hide_index=True)
    st.caption("Hyperscalers extended GPU depreciation from 3-4yr to 5-6yr. This reduced collective depreciation by ~$18B in 2024. Economic life is 18-36 months for frontier training.")

with tab_rel:
    st.header("GPU Reliability & Failure Modes")
    rel_data = pd.DataFrame([
        ("GPU failures (diverse)", "30.1% of disruptions", "Meta 16K-GPU A100 cluster"),
        ("ECC double-bit errors", "3.1% of disruptions", "Silent data corruption risk"),
        ("GPU MTBF", "~160 hours (DBE ECC)", "Titan supercomputer (18,688 GPUs)"),
        ("GPU AFR (Annual Failure)", "~9%", "Meta cluster pre-training data"),
        ("Silent Data Corruption", "~1 per 1,000 GPUs/month", "Google/Meta disclosed"),
        ("Infant mortality", "Elevated (first 1,000 hrs)", "Burn-in before revenue service"),
    ], columns=["Failure Mode", "Rate", "Source"])
    st.dataframe(rel_data, use_container_width=True, hide_index=True)

    st.subheader("Data Centre Tier Classification")
    tier_data = pd.DataFrame([
        ("Tier I", "99.671%", "28.8 hrs/yr", "Single path, no redundancy"),
        ("Tier II", "99.741%", "22.0 hrs/yr", "Single path, redundant components"),
        ("Tier III", "99.982%", "1.6 hrs/yr", "Multiple paths, concurrently maintainable"),
        ("Tier IV", "99.995%", "0.4 hrs/yr", "Fully fault-tolerant, 2N redundancy"),
    ], columns=["Tier", "Uptime", "Downtime", "Redundancy"])
    st.dataframe(tier_data, use_container_width=True, hide_index=True)

with tab_cool:
    st.header("Cooling Technology Comparison")
    cool_data = pd.DataFrame([
        ("Air Cooling", "<30 kW/rack", "Fans + CRAC/CRAH", "PUE 1.3-1.6", "Legacy DCs", "Low complexity, density-limited"),
        ("Direct-to-Chip (D2C)", ">120 kW/rack", "Cold plates + CDU", "PUE 1.1-1.2", "NVL72, H200 clusters", "GPU must be liquid-cooled ready"),
        ("Rear-Door HX", "30-50 kW/rack", "Passive liquid coil", "PUE 1.2-1.4", "Retrofit option", "Limited max density"),
        ("Immersion (1-Phase)", ">100 kW/rack", "GPU submerged in fluid", "PUE 1.03-1.05", "Experimental HPC", "Warranty concerns"),
    ], columns=["Technology", "Max Density", "How", "PUE", "Best For", "Tradeoffs"])
    st.dataframe(cool_data, use_container_width=True, hide_index=True)
    st.caption("Blackwell (B200) effectively requires liquid cooling for dense deployments. Converting air-cooled DC to liquid costs $5-15M per MW.")

with tab_deep:
    st.header("Deep Dive")

    with st.expander("DGX Server Architecture"):
        st.markdown("""
**DGX** is NVIDIA's integrated AI server: 8 GPUs + NVSwitch + CPUs + networking + storage in one box.

| Generation | GPU | Year | Price | Key Advance |
|---|---|---|---|---|
| DGX-1 | P100 (8x) | 2016 | ~$129K | First AI appliance |
| DGX A100 | A100 (8x) | 2020 | ~$199K | MIG, TF32, sparsity |
| DGX H100 | H100 (8x) | 2022 | ~$300K | FP8, Transformer Engine |
| DGX B200 | B200 (8x) | 2024 | ~$500K | Dual-die, FP4, NVL72-ready |

**HGX** is the OEM baseboard version — same GPU+NVSwitch layout but for Dell, Supermicro, HPE to build servers around. Most cloud deployments use HGX, not DGX.

**AMD equivalent:** MI300X uses OAM (OCP Accelerator Module) form factor — less integrated than DGX but more flexible for OEMs.
        """)

    with st.expander("GB200 NVL72 Rack"):
        st.markdown("""
The NVL72 is the current flagship AI rack: 36 Grace CPUs + 72 Blackwell GPUs in a single liquid-cooled rack.

- **130 TB/s NVLink domain** — all 72 GPUs share a coherent memory domain
- **120-132 kW per rack** — 10-20x a typical enterprise rack
- **~1,500 kg** — requires reinforced floor loading
- **Liquid cooling mandatory** — no air-cooled NVL72 option
- **25x more energy efficient than H100** for LLM inference

**Credit implication:** A data centre built for air-cooled 20 kW racks cannot host NVL72. This is the physical manifestation of GPU power density growth outpacing facility design cycles.
        """)

    with st.expander("Silent Data Corruption (SDC)"):
        st.markdown("""
SDC is hardware that produces wrong results without any error flag. It is the most insidious failure mode because it is invisible.

**Scale of the problem:**
- Google: ~1 SDC per 1,000 machines per month
- Meta: SDC caused 3.1% of training disruptions in A100 clusters
- Titan supercomputer: 30.1% of pre-training disruptions were GPU failures

**Why it matters for credit:** A GPU cluster with undetected SDC produces wrong AI models. Worse: it may produce models that appear correct but have subtle errors. This is a reputational and operational risk for AI service providers. SDC rates increase with GPU age — older collateral has higher SDC risk.
        """)

    with st.expander("Credit Implications"):
        st.markdown("""
**Collateral value mismatch:** GPU economic life (18-36 months) is a fraction of building life (25-40 years). A 7-year loan on a data centre must survive 4-5 GPU generations. The building retains value; the GPUs inside do not.

**Concentration risk:** NVIDIA controls the DGX/HGX platform standard. No credible alternative for integrated AI server systems exists at scale. AMD OAM is an emerging alternative but lacks the software integration of DGX.

**Cost exposure:** Power is the dominant OpEx (50-70% of facility operating cost). A $0.01/kWh change in electricity price swings OpEx by ~$2M/year per 25MW facility. Transformer lead times (140-160+ weeks) are a hard gate on construction timelines.

**Transition risk:** Air cooling -> liquid cooling is a non-linear transition. Air-cooled data centres face retrofit costs of $5-15M per MW to accommodate next-gen GPUs. New-build liquid-cooled are cheaper than retrofit. Loan terms must account for this upgrade cycle.
        """)
