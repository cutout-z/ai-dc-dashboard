"""
Lane 7: Technology Roadmaps — 5-year outlook, inflections, risk calendar.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd

st.title("Technology Roadmaps")

st.caption(
    "Sources & as-of (2026-09): NVIDIA/AMD/Google product disclosures and roadmap announcements "
    "(GTC/CES 2026), TSMC technology pages. Shipped rows are vendor-documented; announced/est. rows are "
    "vendor roadmap claims, not verified shipments. Likelihoods below are qualitative editorial "
    "judgements — not calibrated probabilities. No forward-looking statement here asserts automatic "
    "collateral obsolescence: the credit effect always depends on workload mix, utilisation and prices."
)

tab_road, tab_infl, tab_cal, tab_deep = st.tabs(["Vendor Roadmaps", "Technology Inflections", "Risk Calendar", "Deep Dive"])

with tab_road:
    st.header("NVIDIA Data Centre GPU Roadmap")
    roadmap_data = pd.DataFrame([
        ("H100", "Hopper", "2022", "TSMC 4N", "HBM3", "NVLink 4", "700", "80B", "DGX H100, HGX H100"),
        ("H200", "Hopper+", "2023", "TSMC 4N", "HBM3e", "NVLink 4", "700", "80B", "HBM upgrade. +45% BW."),
        ("B200", "Blackwell", "2024", "TSMC 4NP", "HBM3e", "NVLink 5", "1000", "208B", "First dual-die. NVL72."),
        ("B300", "Blackwell Ultra", "2025", "TSMC 4NP", "HBM3e", "NVLink 5", "1200", "208B", "FP4 inference focus."),
        ("Rubin", "Rubin", "2026 (announced)", "TSMC 3N (N3-class)", "HBM4", "NVLink 6", "1500 (est.)", "300B+ (est.)", "Vera CPU. NVL144. CPO."),
        ("Rubin Ultra", "Rubin Ultra", "2027 (announced)", "TSMC 3N (N3-class)", "HBM4e", "NVLink 6", "~2000 (est.)", "~400B (est.)", "Kyber rack (NVL576)."),
        ("Feynman", "Feynman", "2028 (announced)", "TSMC N2 (est.)", "HBM5 (est.)", "NVLink 7 (est.)", "TBD", "TBD", "Next-gen architecture."),
    ], columns=["GPU", "Architecture", "Year", "Process", "Memory", "Interconnect", "TDP (W)", "Transistors", "Features"])
    st.dataframe(roadmap_data, use_container_width=True, hide_index=True)
    st.caption("Process nodes are NVIDIA's own labels: 4N/4NP are NVIDIA-custom 4nm-class variants of the TSMC N5 family — NOT 3nm (see Process Node Roadmap below). Rubin/Rubin Ultra/Feynman are announced roadmaps, not shipped product.")

    st.subheader("Competitive Roadmap")
    comp_road = pd.DataFrame([
        ("NVIDIA", "B200/B300", "Blackwell", "2024-25", "TSMC 4NP", "HBM3e"),
        ("NVIDIA", "Rubin", "Rubin", "2026 (announced)", "TSMC N3-class", "HBM4"),
        ("AMD", "MI300X", "CDNA3", "2023-24", "TSMC 5/6nm", "HBM3"),
        ("AMD", "MI350", "CDNA4", "2025 (announced)", "TSMC N3P", "HBM3e"),
        ("AMD", "MI400", "CDNA4+ (est.)", "2026 (announced)", "TSMC N2? (est.)", "HBM4"),
        ("Google", "TPU v6 (Ironwood)", "—", "2025 (announced)", "TSMC N3-class", "HBM3e"),
        ("Google", "TPU v7", "—", "2027 (est.)", "TSMC N2? (est.)", "HBM4"),
        ("AWS", "Trainium2/3", "—", "2024/2026", "TSMC 5nm/3N", "HBM3e/HBM4"),
    ], columns=["Vendor", "Chip", "Architecture", "Year", "Process", "Memory"])
    st.dataframe(comp_road, use_container_width=True, hide_index=True)
    st.caption("Competitor rows are vendor-announced roadmaps (AMD, Google, AWS) as of 2026-09; '?' = unconfirmed process reporting.")

    st.subheader("Process Node Roadmap")
    node_data = pd.DataFrame([
        ("TSMC N5 family (incl. NVIDIA 4N/4NP)", "2020-2025", "FinFET (5nm-class)", "~170M Tr/mm2 (est.)", "H100/H200 (4N), B200/B300 (4NP), MI300X"),
        ("TSMC N3 family (N3/N3E/N3P)", "2022-2026", "FinFET enhanced (3nm)", "~200-260M Tr/mm2 (est.)", "Rubin (announced), MI350 (N3P)"),
        ("TSMC N2", "2025-26", "GAA (nanosheet)", "~280M Tr/mm2 (est.)", "Feynman (announced)"),
        ("TSMC A16", "2026", "GAA + Backside Power", "~320M Tr/mm2 (est.)", "Next-gen after N2"),
        ("Samsung SF3", "2023", "GAA (MBCFET)", "~170M Tr/mm2 (est.)", "Limited AI adoption"),
        ("Samsung SF2", "2025", "GAA (2nd gen)", "~220M Tr/mm2 (est.)", "Targeting AI customers"),
        ("Intel 18A", "2025", "GAA (RibbonFET) + PowerVia", "~250M Tr/mm2 (est.)", "Intel Foundry customers"),
        ("Intel 14A", "2027", "GAA (2nd gen)", "~300M Tr/mm2 (est.)", "High-NA EUV"),
    ], columns=["Node", "Production", "Type", "Density (est.)", "AI Chip Users"])
    st.dataframe(node_data, use_container_width=True, hide_index=True)
    st.caption(
        "Reconciled with the vendor tables above (as-of 2026-09). NVIDIA's H100/H200 sit on 4N and B200/B300 on "
        "4NP — both 4nm-class custom variants of the TSMC N5 family — so they appear in the N5-family row, NOT under "
        "N3. Rubin is NVIDIA's first announced N3-class part. MI300X is N5/N6 (not N3); MI350 is N3P. Densities are "
        "widely-cited public estimates, not foundry-confirmed figures."
    )

with tab_infl:
    st.header("Technology Inflections — 2025-2030")
    st.caption("Likelihood words are qualitative editorial judgements for each stated timing window (as of 2026-09) — not calibrated probabilities. Credit Impact = editorial severity assessment.")
    infl_data = pd.DataFrame([
        ("GAA replaces FinFET", "2025-26", "High", "MODERATE",
         "All leading-edge chips shift to GAA by 2027. Evolutionary, not revolutionary."),
        ("Backside Power (A16)", "2026-27", "High", "MODERATE",
         "Separates power and signal routing. 10-15% perf improvement. New designs required."),
        ("CPO replaces copper", "2026-28", "High", "MODERATE",
         "Optics in switches first (2026), GPU-native CPO (2028+). Copper-based assets face transition."),
        ("ASICs reach GPU training parity", "2027-29", "Moderate", "MAJOR",
         "Google TPU v7, AWS Trainium3 targeting training. GPU-heavy collateral faces competitive displacement."),
        ("Power wall forces redesign", "2027-30", "High", "MAJOR",
         "GPU TDP 1500W+. Racks 300-600kW. Existing DCs cannot accommodate. Retrofit costs $5-15M/MW."),
    ], columns=["Inflection", "Timing", "Likelihood (editorial)", "Credit Impact", "What Changes"])
    st.dataframe(infl_data, use_container_width=True, hide_index=True,
        column_config={"What Changes": st.column_config.TextColumn(width=400)})

with tab_cal:
    st.header("Technology Risk Calendar")
    st.caption("Events/impacts are editorial judgements as of 2026-09. Implication notes describe *potential* credit pressure — a new generation does not by itself strand existing collateral; the effect depends on workload mix, utilisation and prices.")
    cal_data = pd.DataFrame([
        ("2025", "Blackwell ramp. HBM3e tight. CoWoS constrained.", "MAJOR", "Transition risk for Hopper collateral."),
        ("2026", "Rubin announced. HBM4 first shipments.", "MAJOR", "Rubin claims ~4x Blackwell inference (NVIDIA); Blackwell faces potential pressure for frontier-training-only fleets — workload/utilisation/price dependent."),
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
| Hopper+ (H200) | 2023 | HBM3e upgrade, +45% bandwidth | ~1.5x inference (NVIDIA) |
| Blackwell (B200) | 2024 | Dual-die, FP4, NVLink 5, NVL72 | ~2.5x training, ~4x inference (NVIDIA) |
| Blackwell Ultra (B300) | 2025 | Higher clocks, FP4 focus | ~1.5x over B200 (NVIDIA) |
| Rubin | 2026 (announced) | TSMC N3-class, HBM4, NVLink 6, Vera CPU, CPO | ~10x inference token-cost reduction vs H100 (NVIDIA claim) |
| Rubin Ultra | 2027 (announced) | HBM4e, NVL576 (Kyber rack) | Further scale-out |
| Feynman | 2028 (announced) | TSMC N2 (est.), HBM5, NVLink 7 | TBD |

Performance multiples are NVIDIA-announced marketing figures, not independently verified.

**Credit insight (editorial, as-of 2026-09):** Each generation delivers large claimed improvements, which compresses the *frontier-viability window* of each GPU generation. Blackwell collateral faces economic pressure once Rubin ships — but the magnitude depends on workload mix (frontier training vs inference vs serving), utilisation, and power/rental prices. A new generation does not automatically strand the prior one for lower-tier workloads.
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

**Today (2026):** ASICs dominate inference, GPUs dominate training. TPU v6 (Ironwood), Trainium2/3, and Maia-class parts are strong on inference TCO but have not displaced H100/B200 on frontier training throughput or software flexibility (as of 2026-09).

**The inflection (2027-29, editorial scenario):** Google TPU v7 and AWS Trainium3 target training parity. Key enablers: (a) larger die sizes on N2, (b) HBM4 bandwidth, and (c) maturing software stacks (JAX, Neuron SDK). If ASICs reach near-GPU training performance at a meaningfully lower cost, the economic case for GPU-only fleets shifts — these are scenario assumptions, not forecasts.

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
**Technology obsolescence risk (editorial, as-of 2026-09):** Annual GPU cadence means each generation has roughly an 18-36 month window at the *frontier* of training. Rubin-class parts (2026-27) will put economic pressure on Blackwell collateral used for frontier-training workloads — but whether existing collateral is stranded depends on workload mix, utilisation, and power/rental prices. Inference, fine-tuning, and lower-tier training demand generally keeps prior generations revenue-generating well past a new launch.

**Transition timing risk:** The 2026-28 window contains multiple simultaneous transitions: GAA (N2), backside power (A16), HBM4, CPO networking, and potential ASIC training parity. Borrowers with loan maturities in this window face compound transition risk.

**Competitive displacement risk:** ASICs are the most significant potential threat to NVIDIA's GPU position. TPU v7 and Trainium3 (2027-29, announced) target training parity. A portfolio heavy in NVIDIA GPU collateral should monitor ASIC adoption rates as a leading indicator.

**The Three Clocks misalignment:** Silicon improves every 12-18 months. Data centres take 3-7 years to build. Power infrastructure takes 10-30+ years. A 7-year loan must survive technologies that do not exist yet and power infrastructure that may not arrive in time. This structural misalignment is a credit consideration every AI/DC analysis should weigh — it raises the importance of conservative residual-value and refresh assumptions rather than implying any single asset class is worthless.
        """)
