"""
Lane 3: Advanced Packaging — CoWoS, EMIB, hybrid bonding.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.title("Advanced Packaging")

tab_tech, tab_supply, tab_deep = st.tabs(["Technology Comparison", "Supply Chain", "Deep Dive"])

with tab_tech:
    st.header("Packaging Technologies — Side by Side")
    pkg_data = pd.DataFrame([
        ("CoWoS-S", "TSMC", "Silicon interposer (~2X reticle)", "3.3X reticle", "~$10K/wafer", "NVIDIA, AMD, Broadcom"),
        ("CoWoS-L", "TSMC", "Local silicon bridges (~4X reticle)", "5.5X reticle (roadmap 14X)", "~$12-15K/wafer", "Blackwell B200"),
        ("CoWoS-R", "TSMC", "Organic interposer (RDL)", "No reticle limit", "~$6-8K/wafer", "Lower-cost apps"),
        ("EMIB", "Intel", "Embedded bridges in substrate", "~8X reticle", "Varies", "Ponte Vecchio, Gaudi 3"),
        ("I-Cube", "Samsung", "Silicon interposer (2.5D)", "~2X reticle", "~$8-10K/wafer", "Limited HBM integration"),
        ("FOCoS", "ASE/SPIL", "Fan-out chip-on-substrate", "~2-3X reticle", "~$5-7K/wafer", "OSAT alternative"),
    ], columns=["Technology", "Vendor", "Architecture", "Max Package", "Cost", "Key Users"])
    st.dataframe(pkg_data, use_container_width=True, hide_index=True)

    st.subheader("TSMC CoWoS Capacity Ramp")
    cowos_cap = pd.DataFrame([
        ("2023", 13, "Pre-AI boom baseline"), ("2024", 35, "H100/H200 demand"),
        ("2025", 80, "Blackwell ramp begins"), ("2026E", 167, "Aggressive expansion"),
    ], columns=["Year", "Capacity (k wpm)", "Notes"])

    fig_cap = go.Figure()
    fig_cap.add_trace(go.Bar(x=cowos_cap["Year"], y=cowos_cap["Capacity (k wpm)"],
        text=cowos_cap["Capacity (k wpm)"], texttemplate="%{text}k", textposition="outside",
        marker_color="#3b82f6"))
    fig_cap.update_layout(height=380, yaxis_title="CoWoS Capacity (thousand wafers/month)",
        xaxis_type="category", margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig_cap, use_container_width=True)
    st.caption("TSMC CoWoS capacity growing ~13x from 2023 to 2026E. NVIDIA consumes ~63% of capacity.")

with tab_supply:
    st.header("Packaging Supply Chain")
    supply_data = pd.DataFrame([
        ("TSMC CoWoS", "TSMC", "~95%", "Taiwan", "Sole source", "13 -> 167k wpm expansion"),
        ("Intel EMIB", "Intel", "<5%", "US, Ireland", "Intel-only", "Foundry Services opening"),
        ("Samsung I/H/X-Cube", "Samsung", "<5%", "South Korea", "Distant third", "NVIDIA qual pending"),
        ("ABF Substrate", "Ibiden", "~75% (Blackwell)", "Japan", "Near sole source", "Ajinomoto ABF film monopoly"),
        ("ABF Substrate", "Unimicron", "~15-20%", "Taiwan", "Growing", "Capacity expanding"),
        ("ABF Film", "Ajinomoto", ">95%", "Japan", "Sole source", "Only two plants globally"),
    ], columns=["Component", "Supplier", "Share", "Location", "Status", "Notes"])
    st.dataframe(supply_data, use_container_width=True, hide_index=True)

with tab_deep:
    st.header("Deep Dive")

    with st.expander("Why Packaging Matters — The Reticle Wall"):
        st.markdown("""
The reticle limit (~858 mm2) is the maximum single-die size that lithography tools can expose. B200 was the first GPU to exceed this, using two dies connected by NV-HBI (10 TB/s).

**Monolithic vs chiplet:**
- Monolithic: one die. Limited to ~858 mm2. A100, H100 are monolithic.
- Chiplet: multiple smaller dies assembled on one package. B200 (2 dies), MI300X (8 compute + 8 HBM).

**Why chiplets are inevitable:** Process node shrinks deliver less area reduction per generation than they used to. Transistor counts keep growing (80B -> 208B -> 300B+). Without chiplets, dies would exceed reticle limits and be unmanufacturable.

**Cost of monolithic vs chiplet:** Chiplet designs have higher packaging cost (CoWoS adds $10-15K per wafer) but higher yield (smaller dies = fewer defects per die). The crossover point where chiplets become cheaper depends on defect density — at N3 and below, chiplets are likely cheaper for any die >400 mm2.
        """)

    with st.expander("CoWoS-S vs CoWoS-L vs CoWoS-R"):
        st.markdown("""
**CoWoS-S (Silicon interposer):** Full silicon interposer connecting GPU dies to HBM stacks. Maximum package size ~3.3X reticle (~2,800 mm2). Mature technology, highest performance. Used in A100, H100.

**CoWoS-L (Local Silicon Interconnect):** Uses small silicon bridges instead of a full interposer. Enables larger packages (~5.5X reticle today, roadmap to 14X). Lower cost than full interposer but design is more complex. Used in B200.

**CoWoS-R (Organic interposer):** Uses organic RDL (redistribution layer) instead of silicon. No reticle size limit. Lower performance but much cheaper. Used for lower-cost applications (networking, consumer).

**Intel EMIB:** Embedded silicon bridges in the organic substrate. No large interposer needed. ~8X reticle today. Used in Ponte Vecchio (47 tiles). Key advantage: can connect dies of different process nodes on the same package.
        """)

    with st.expander("Hybrid Bonding — The Next Frontier"):
        st.markdown("""
Hybrid bonding (Cu-Cu direct bonding) eliminates microbumps entirely. Copper pads on two dies are directly bonded at room temperature through atomic diffusion.

| Metric | Microbump (Current) | Hybrid Bonding (Next) | Advantage |
|---|---|---|---|
| Interconnect Density | ~400-1,000 bumps/mm2 | ~10,000-100,000 bonds/mm2 | 10-100x |
| Bond Pitch | ~35-50 um | <10 um (sub-um achievable) | 5-10x finer |
| Power per Connection | ~0.5-1.0 pJ/bit | ~0.05-0.1 pJ/bit | 10x reduction |
| Stack Height | ~50 um per layer | ~10 um per layer | Thinner stacks |

First high-volume AI application: HBM4 (2026). Already in production: AMD 3D V-Cache. Requires Class 1 cleanroom and <0.5 nm surface roughness — extreme manufacturing precision.
        """)

    with st.expander("Credit Implications"):
        st.markdown("""
**Collateral value risk:** Packaging is tied to chip design — near-zero standalone salvage value. A packaged GPU has value; the packaging process itself does not.

**Concentration risk:** TSMC controls ~95% of CoWoS. Ibiden controls ~75% of high-end substrates for Blackwell. Ajinomoto controls >95% of ABF film. Each is a single point of failure.

**Cost exposure:** Packaging cost as % of BOM is rising from 15-20% to potentially 40-50% as chiplets become standard. CoWoS pricing increases 10-20% per year as demand exceeds supply.

**Transition risk:** Four simultaneous transitions: microbump -> hybrid bonding, Si -> glass interposer, proprietary -> UCIe standard, TSMC monopoly -> multi-source. Each transition creates risk for borrowers locked into current-generation packaging.
        """)
