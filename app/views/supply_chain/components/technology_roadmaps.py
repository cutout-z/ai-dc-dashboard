"""
Lane 7: Technology Roadmaps — 5-year outlook, inflections, risk calendar.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd

st.title("Technology Roadmaps")

tab_road, tab_infl, tab_cal, tab_deep = st.tabs(["Vendor Roadmaps", "Technology Inflections", "Risk Calendar", "Deep Dive"])

with tab_road:
    st.header("NVIDIA Data Centre GPU Roadmap")
    roadmap_data = pd.DataFrame([
        ("H100", "Hopper", "2022", "TSMC 4N", "HBM3", "NVLink 4", "700", "80B", "DGX H100, HGX H100"),
        ("H200", "Hopper+", "2023", "TSMC 4N", "HBM3e", "NVLink 4", "700", "80B", "HBM upgrade. +45% BW."),
        ("B200", "Blackwell", "2024", "TSMC 4NP", "HBM3e", "NVLink 5", "1000", "208B", "First dual-die. NVL72."),
        ("B300", "Blackwell Ultra", "2025", "TSMC 4NP", "HBM3e", "NVLink 5", "1200", "208B", "FP4 inference focus."),
        ("Rubin", "Rubin", "2026", "TSMC 3N", "HBM4", "NVLink 6", "1500 (est.)", "300B+ (est.)", "Vera CPU. NVL144. CPO."),
        ("Rubin Ultra", "Rubin Ultra", "2027", "TSMC 3N", "HBM4e", "NVLink 6", "~2000 (est.)", "~400B (est.)", "Kyber rack (NVL576)."),
        ("Feynman", "Feynman", "2028", "TSMC N2", "HBM5 (est.)", "NVLink 7 (est.)", "TBD", "TBD", "Next-gen architecture."),
    ], columns=["GPU", "Architecture", "Year", "Process", "Memory", "Interconnect", "TDP (W)", "Transistors", "Features"])
    st.dataframe(roadmap_data, use_container_width=True, hide_index=True)

    st.subheader("Competitive Roadmap")
    comp_road = pd.DataFrame([
        ("NVIDIA", "B200/B300", "Blackwell", "2024-25", "TSMC 4NP", "HBM3e"),
        ("NVIDIA", "Rubin", "Rubin", "2026", "TSMC 3N", "HBM4"),
        ("AMD", "MI300X", "CDNA3", "2023-24", "TSMC 5/6nm", "HBM3"),
        ("AMD", "MI350", "CDNA3+", "2025", "TSMC 3N", "HBM3e"),
        ("AMD", "MI400", "CDNA4", "2026", "TSMC N2?", "HBM4"),
        ("Google", "TPU v6 (Ironwood)", "—", "2025", "TSMC 3N", "HBM3e"),
        ("Google", "TPU v7", "—", "2027", "TSMC N2?", "HBM4"),
        ("AWS", "Trainium2/3", "—", "2024/2026", "TSMC 5nm/3N", "HBM3e/HBM4"),
    ], columns=["Vendor", "Chip", "Architecture", "Year", "Process", "Memory"])
    st.dataframe(comp_road, use_container_width=True, hide_index=True)

    st.subheader("Process Node Roadmap")
    node_data = pd.DataFrame([
        ("TSMC N3/N3E", "2023", "FinFET", "~215M Tr/mm2", "H100, B200, MI300X"),
        ("TSMC N3P", "2024", "FinFET enhanced", "~230M", "B300, Rubin"),
        ("TSMC N2", "2025-26", "GAA (nanosheet)", "~280M", "Rubin Ultra, Feynman"),
        ("TSMC A16", "2026", "GAA + Backside Power", "~320M", "Next-gen after N2"),
        ("Samsung SF3", "2023", "GAA (MBCFET)", "~170M", "Limited AI adoption"),
        ("Samsung SF2", "2025", "GAA (2nd gen)", "~220M", "Targeting AI customers"),
        ("Intel 18A", "2025", "GAA (RibbonFET) + PowerVia", "~250M", "Intel Foundry comeback"),
        ("Intel 14A", "2027", "GAA (2nd gen)", "~300M", "High-NA EUV"),
    ], columns=["Node", "Production", "Type", "Density", "AI Chip Users"])
    st.dataframe(node_data, use_container_width=True, hide_index=True)

with tab_infl:
    st.header("Technology Inflections — 2025-2030")
    infl_data = pd.DataFrame([
        ("GAA replaces FinFET", "2025-26", "High (90%+)", "MODERATE",
         "All leading-edge chips shift to GAA by 2027. Evolutionary, not revolutionary."),
        ("Backside Power (A16)", "2026-27", "High (80%+)", "MODERATE",
         "Separates power and signal routing. 10-15% perf improvement. New designs required."),
        ("CPO replaces copper", "2026-28", "High (80%+)", "MODERATE",
         "Optics in switches first (2026), GPU-native CPO (2028+). Copper-based assets face transition."),
        ("ASICs reach GPU training parity", "2027-29", "Moderate (40-60%)", "MAJOR",
         "Google TPU v7, AWS Trainium3 targeting training. GPU-heavy collateral faces competitive displacement."),
        ("Power wall forces redesign", "2027-30", "High (80%+)", "MAJOR",
         "GPU TDP 1500W+. Racks 300-600kW. Existing DCs cannot accommodate. Retrofit costs $5-15M/MW."),
    ], columns=["Inflection", "Timing", "Probability", "Credit Impact", "What Changes"])
    st.dataframe(infl_data, use_container_width=True, hide_index=True,
        column_config={"What Changes": st.column_config.TextColumn(width=400)})

with tab_cal:
    st.header("Technology Risk Calendar")
    cal_data = pd.DataFrame([
        ("2025", "Blackwell ramp. HBM3e tight. CoWoS constrained.", "MAJOR", "Transition risk for Hopper collateral."),
        ("2026", "Rubin announced. HBM4 first shipments.", "MAJOR", "Rubin 4x inference vs Blackwell. Blackwell obsolescence starts."),
        ("2026", "CPO networking volume ramp. TSMC N2 volume.", "MODERATE", "InfiniBand copper begins transition. Intel Foundry competition."),
        ("2027", "Rubin Ultra. ASICs near training parity. UEC mature.", "MODERATE", "NVIDIA competitive pressure. Networking monopoly challenged."),
        ("2028", "Feynman architecture. Optics at chip level.", "MODERATE", "Optical interconnects start replacing copper GPU-to-GPU."),
        ("2029-30", "Power wall: 2kW+ GPUs. Air cooling non-viable.", "MAJOR", "Existing air-cooled DCs uncompetitive. Liquid-cooled premium."),
        ("2030", "ASIC vs GPU competitive balance determined.", "MODERATE", "Market structure for AI compute settles."),
    ], columns=["Year", "Event", "Credit Impact", "Implications"])
    st.dataframe(cal_data, use_container_width=True, hide_index=True,
        column_config={"Implications": st.column_config.TextColumn(width=450)})

    st.subheader("The Three Clocks")
    st.markdown("""
| Clock | Cycle Time | What It Governs |
|---|---|---|
| Silicon Clock | 12-18 months | GPU performance, efficiency, competitiveness |
| Facility Clock | 3-7 years | Data centre construction, power interconnection |
| Energy Clock | 10-30+ years | Power availability, transmission capacity |

**The gap:** Silicon improves 2-4x in the time it takes to permit a data centre. By the time a facility is operational, the GPUs it was designed for are two generations old.
    """)

with tab_deep:
    st.header("Deep Dive")

    with st.expander("NVIDIA Roadmap — What Changes Each Generation"):
        st.markdown("""
NVIDIA has shifted from a biennial to an annual architecture cadence:

| Generation | Year | Key Change | Performance vs Prior Gen |
|---|---|---|---|
| Hopper (H100) | 2022 | FP8, Transformer Engine, NVLink 4 | Baseline |
| Hopper+ (H200) | 2023 | HBM3e upgrade, +45% bandwidth | ~1.5x inference |
| Blackwell (B200) | 2024 | Dual-die, FP4, NVLink 5, NVL72 | ~2.5x training, ~4x inference |
| Blackwell Ultra (B300) | 2025 | Higher clocks, FP4 focus | ~1.5x over B200 |
| Rubin | 2026 | TSMC 3N, HBM4, NVLink 6, Vera CPU, CPO | ~10x reduction in inference token cost vs H100 |
| Rubin Ultra | 2027 | HBM4e, NVL576 (Kyber rack) | Further scale-out |
| Feynman | 2028 | TSMC N2, HBM5, NVLink 7 | TBD |

**Credit insight:** Each generation delivers 2-4x improvement over the previous. This compresses the useful life of each GPU generation. Blackwell-based collateral will face obsolescence pressure when Rubin ships (2026).
        """)

    with st.expander("Process Node Deep-Dive — GAA and Backside Power"):
        st.markdown("""
**FinFET -> GAA (Gate-All-Around):** FinFET wraps the gate around three sides of the channel. GAA wraps all four sides, providing better electrostatic control. TSMC N2 is the first GAA node for high-volume AI chips. Samsung already uses GAA (SF3), but with lower density and yield.

**Backside power delivery (TSMC A16, Intel PowerVia):** Delivers power from the back of the wafer, separating power and signal routing. Benefits: 10-15% performance improvement, better voltage scaling, frees up front-side routing for signals. Requires new design methodologies — existing designs are not directly portable.

**Implications:** The shift to GAA and backside power means future GPU designs will be fundamentally different from current ones. Chips designed for N3 cannot be trivially ported to N2 or A16.
        """)

    with st.expander("The ASIC Inflection — When Do Custom Chips Beat GPUs?"):
        st.markdown("""
The GPU vs ASIC debate turns on two questions: (1) can ASICs match GPU performance for training, and (2) at what scale does the TCO advantage justify the development cost?

**Today (2025):** ASICs dominate inference, GPUs dominate training. TPU v5p, Trainium2, and Maia 100 all outperform GPUs on inference TCO but cannot match H100/B200 on training throughput or software flexibility.

**The inflection (2027-29):** Google TPU v7 and AWS Trainium3 target training parity. Key enablers: (a) larger die sizes on N2, (b) HBM4 bandwidth, and (c) maturing software stacks (JAX, Neuron SDK). If ASICs achieve 90%+ GPU training performance at 50-70% of the cost, the economic case shifts decisively.

**Credit implication:** A borrower whose collateral is 100% NVIDIA GPUs faces competitive displacement risk if ASICs achieve training parity. The risk is highest for inference-heavy workloads (where ASICs already compete) and lowest for frontier training (where NVIDIA's software moat is strongest). The 2027-29 window is when this risk materialises.
        """)

    with st.expander("Moore's Law — Is It Still Alive?"):
        st.markdown("""
Moore's Law has multiple definitions. The most relevant for AI hardware:

**Transistor count doubling:** Still roughly on track. B200 has 208B transistors vs H100's 80B (2.6x in 2 years). But this is achieved through chiplets and larger die area, not density scaling alone.

**Transistor density scaling:** Slowing. TSMC N5 -> N3 delivers ~1.5x density (vs the historical ~2x). N2 delivers ~1.3x over N3. The era of 2x density per node is over.

**Cost per transistor:** The economic premise of Moore's Law broke around 2014. Cost per transistor has been flat to slightly rising since 28nm. Each new node costs more per transistor, not less. This means future GPU performance gains will come from architecture and packaging innovation, not cheaper transistors.

**Credit implication:** GPU performance gains are increasingly driven by power consumption (higher TDP), die size (chiplets), and packaging complexity — all of which increase cost. The "next GPU will be cheaper per FLOP" assumption may not hold. Borrowers projecting cost-per-FLOP declines should be stress-tested against flat or rising cost curves.
        """)

    with st.expander("Credit Implications"):
        st.markdown("""
**Technology obsolescence risk:** Annual GPU cadence means each generation has ~18-24 months of frontier viability. Rubin (2026) will make Blackwell-based collateral economically stranded for training workloads.

**Transition timing risk:** The 2026-28 window contains multiple simultaneous transitions: GAA (N2), backside power (A16), HBM4, CPO networking, and potential ASIC training parity. Borrowers with loan maturities in this window face compound transition risk.

**Competitive displacement risk:** ASICs are the most significant threat to NVIDIA's GPU monopoly. TPU v7 and Trainium3 (2027-29) target training parity. A portfolio heavy in NVIDIA GPU collateral should monitor ASIC adoption rates as a leading indicator.

**The Three Clocks misalignment:** Silicon improves every 12-18 months. Data centres take 3-7 years to build. Power infrastructure takes 10-30+ years. A 7-year loan must survive technologies that do not exist yet and power infrastructure that may not arrive in time. This is a structural, unresolvable misalignment that every AI/DC credit analysis must account for.
        """)
