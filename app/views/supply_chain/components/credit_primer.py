"""
Lane 0: Hardware-Credit Nexus — dependency map, acronyms, credit risk matrix.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.title("Hardware Credit Primer")
st.caption(
    "This section of the dashboard maps the AI data centre hardware stack — from silicon to rack — "
    "for credit officers who need to understand what they are lending against. "
    "Each lane (0-7) covers a specific component domain: GPU architecture, memory subsystems, "
    "advanced packaging, interconnects, system integration, supply chains, and technology roadmaps. "
    "Every page includes a \"Deep Dive\" section with the underlying technical detail, "
    "but the summary charts and credit risk matrices are designed to be usable in 15 minutes. "
    "Start with this reading guide to navigate by your credit scenario."
)

tab_guide, tab_map, tab_acro, tab_risk, tab_nvidia = st.tabs([
    "Reading Guide", "Dependency Map", "Acronyms", "Credit Risk Matrix", "NVIDIA Dependency",
])

with tab_guide:
    st.subheader("Reading Guide")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### Path A: Data Centre-Out (Recommended)")
        st.caption("Start with the asset you are lending against. Drill down as needed.")
        st.markdown("""
1. **5. System Integration** — What is inside a rack? Big cost items?
2. **6. Supply Chain Mapping** — Who makes everything? Lead times.
3. **1. AI Accelerator Architecture** — What is inside the GPU?
4. **2. Memory Subsystem** — Why is memory the bottleneck?
5. **3. Advanced Packaging** — How are chips assembled?
6. **4. Interconnect & Networking** — How do GPUs talk?
7. **7. Technology Roadmaps** — What changes next?
        """)
    with col_b:
        st.markdown("### Path B: Component-In")
        st.caption("Start from silicon and build up.")
        st.markdown("Lane 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7")

    st.markdown("---")
    st.subheader("Quick-Start by Credit Scenario")
    qcol1, qcol2 = st.columns(2)
    with qcol1:
        st.markdown("**Evaluating a neocloud loan?**")
        st.caption("NVIDIA Dependency Index, then Lanes 1 (GPU obsolescence) + 5 (TCO).")
        st.markdown("**Evaluating a DC construction loan?**")
        st.caption("Lanes 5 (System) + 6 (Lead times) + 7 (Roadmaps).")
    with qcol2:
        st.markdown("**Evaluating a GPU ABS / hardware lease?**")
        st.caption("Collateral Value in Risk Matrix, then Lanes 1 + 2 (HBM lock-in).")
        st.markdown("**Need a rapid briefing?**")
        st.caption("Dependency Map + Bottleneck Sequence + Risk Matrix above. 15 minutes.")

with tab_map:
    st.subheader("AI Hardware Supply Chain — Component Dependency Map")
    bottleneck_data = pd.DataFrame([
        ("CPU->GPU Transition", "2020-2022", "Resolved", 0),
        ("Memory Wall (HBM)", "2022-2024", "Transitioning", 2),
        ("HBM Supply Shortage", "2024-2026", "Active", 4),
        ("CoWoS Packaging", "2025-H2 2026", "Tight", 3),
        ("Power Wall (grid/cooling)", "2025-2027", "Active", 4),
        ("Interconnect & Photonics", "2026-2028", "Emerging", 2),
        ("Miniaturization (1nm)", "2027-2030", "Future", 1),
        ("Data & Latency Wall", "2030s", "Long-term", 1),
    ], columns=["Bottleneck", "Period", "Status", "severity"])

    color_map = {"Active": "#ef4444", "Tight": "#f59e0b", "Transitioning": "#f59e0b",
                 "Emerging": "#3b82f6", "Future": "#6b7280", "Resolved": "#22c55e", "Long-term": "#6b7280"}

    fig_bl = go.Figure()
    for _, row in bottleneck_data.iterrows():
        fig_bl.add_trace(go.Scatter(x=[row["Period"]], y=[row["Bottleneck"]], mode="markers+text",
            marker=dict(size=max(row["severity"]*8, 8), color=color_map.get(row["Status"], "#6b7280")),
            text=row["Status"], textposition="middle right", textfont=dict(size=11),
            hovertemplate=f"<b>{row['Bottleneck']}</b><br>{row['Period']}<br>Status: {row['Status']}<extra></extra>"))
    fig_bl.update_layout(height=500, xaxis_title="Timeline", yaxis=dict(autorange="reversed"),
        showlegend=False, margin=dict(l=20, r=120, t=10, b=40))
    st.plotly_chart(fig_bl, use_container_width=True)
    st.caption("Based on the AI infrastructure constraints bottleneck sequence. Each bottleneck resolves only for the next to appear.")

    st.subheader("Single Points of Failure")
    spof_data = pd.DataFrame([
        ("Advanced Fab (<7nm)", "TSMC (~90%)", "Samsung (limited), Intel (2027+)", "No AI chips for anyone. Total supply halt.", 5),
        ("EUV Lithography", "ASML (100%)", "None", "No leading-edge chips, period.", 5),
        ("HBM3e Memory", "SK Hynix (>90%)", "Samsung (ramping), Micron (qualified)", "GPU shipments halted. B200 cannot ship without HBM.", 5),
        ("CoWoS Packaging", "TSMC (~95%)", "ASE/SPIL (limited), Samsung I-Cube", "GPUs and HBM manufactured but cannot be assembled.", 4),
        ("ABF Substrate", "Ibiden (~50%)", "Unimicron, Shinko", "Interposer substrate shortage. Packaging slowed.", 3),
        ("InfiniBand / NVLink", "NVIDIA Mellanox (>90%)", "Ethernet via UEC (Broadcom, Marvell)", "GPU clusters cannot scale. Training halted beyond single node.", 3),
        ("CUDA Software", "NVIDIA (proprietary)", "ROCm (AMD), Triton (open)", "All existing workloads locked. Migration takes years.", 3),
    ], columns=["Component", "Sole Source?", "Alternative", "Failure Impact", "Score"])

    st.dataframe(spof_data[["Component", "Sole Source?", "Alternative", "Failure Impact"]],
        use_container_width=True, hide_index=True,
        column_config={"Failure Impact": st.column_config.TextColumn(width=450)})

with tab_acro:
    st.subheader("Acronym Cheat Sheet")
    acronym_data = pd.DataFrame([
        ("GPU", "Graphics Processing Unit", "Massively parallel processor. NVIDIA dominates AI.", "Compute"),
        ("TPU", "Tensor Processing Unit", "Google custom AI accelerator. Systolic arrays.", "Compute"),
        ("ASIC", "Application-Specific IC", "Custom chip. AWS Trainium, Microsoft Maia, Meta MTIA.", "Compute"),
        ("CUDA", "Compute Unified Device Architecture", "NVIDIA proprietary software. ~5M developers locked in.", "Compute"),
        ("SM", "Streaming Multiprocessor", "Fundamental compute unit inside NVIDIA GPU.", "Compute"),
        ("MIG", "Multi-Instance GPU", "Splits one GPU into up to 7 isolated virtual GPUs.", "Compute"),
        ("TFLOPS", "Trillion FLOPS", "Standard compute throughput. B200: ~9 PFLOPS (FP8 sparse).", "Compute"),
        ("TDP", "Thermal Design Power", "Max heat output (watts). B200: 1,000W.", "Compute"),
        ("HBM", "High Bandwidth Memory", "3D-stacked DRAM on GPU interposer. ~8x bandwidth of GDDR.", "Memory"),
        ("HBM3e", "HBM 3rd Gen Extended", "Current standard (2024-26). Used in H200, B200, MI300X.", "Memory"),
        ("HBM4", "HBM 4th Gen", "Next-gen (2026+). 2048-bit. 16-hi. Hybrid bonding.", "Memory"),
        ("GDDR", "Graphics Double Data Rate", "Standard GPU memory on PCB. Cheaper, slower than HBM.", "Memory"),
        ("TSV", "Through-Silicon Via", "Vertical connection through silicon. Enables HBM 3D stacking.", "Memory"),
        ("CXL", "Compute Express Link", "Memory/storage pooling across servers.", "Memory"),
        ("CoWoS", "Chip-on-Wafer-on-Substrate", "TSMC packaging. GPU+HBM on silicon interposer. ~95% share.", "Packaging"),
        ("EMIB", "Embedded Multi-Die Interconnect Bridge", "Intel packaging. Small bridges in substrate.", "Packaging"),
        ("UCIe", "Universal Chiplet Interconnect Express", "Open standard for multi-vendor chiplet assembly.", "Packaging"),
        ("ABF", "Ajinomoto Build-up Film", "Chip substrate insulator. Ajinomoto >95% monopoly.", "Packaging"),
        ("NVLink", "NVIDIA GPU Interconnect", "NVLink 5: 1.8 TB/s per GPU. Proprietary.", "Interconnect"),
        ("InfiniBand", "—", "High-performance networking. NVIDIA (Mellanox) dominates.", "Interconnect"),
        ("RDMA", "Remote Direct Memory Access", "Direct memory access between computers. Critical for GPUs.", "Interconnect"),
        ("UEC", "Ultra Ethernet Consortium", "Industry group developing Ethernet alternative to InfiniBand.", "Interconnect"),
        ("DGX", "Deep Learning GPU System", "NVIDIA integrated AI server. 8x B200 + NVSwitch.", "System"),
        ("NVL72", "NVLink 72-GPU Rack", "36 CPUs + 72 GPUs. Liquid-cooled. 130 TB/s NVLink.", "System"),
        ("PUE", "Power Usage Effectiveness", "Total facility power / IT power. 1.0 = perfect.", "System"),
        ("MTBF", "Mean Time Between Failures", "GPU: ~1-3 years at high utilisation.", "System"),
        ("SDC", "Silent Data Corruption", "Undetected hardware errors producing wrong results.", "System"),
    ], columns=["Acronym", "Full Name", "Definition", "Category"])

    search = st.text_input("Search acronyms", key="acro_search")
    df_f = acronym_data.copy()
    if search:
        mask = df_f["Acronym"].str.contains(search, case=False)
        mask |= df_f["Definition"].str.contains(search, case=False)
        df_f = df_f[mask]
    st.dataframe(df_f, use_container_width=True, hide_index=True, height=500,
        column_config={"Definition": st.column_config.TextColumn(width=450)})

with tab_risk:
    st.subheader("Hardware to Credit Risk Matrix")
    risk_data = pd.DataFrame([
        ("GPU / Accelerator", "HIGH (18-36mo)", "HIGH (annual cadence)", "HIGH (700-1200W per GPU)", "NVIDIA+TSMC dual"),
        ("HBM Memory", "HIGH (gen-locked)", "MODERATE (HBM4 2026)", "LOW (~10% GPU power)", "SK Hynix >90% HBM3e"),
        ("Advanced Packaging", "MODERATE", "LOW (platform, not gen)", "LOW (CapEx not OpEx)", "TSMC ~95% CoWoS"),
        ("Interconnect / NW", "MODERATE (5-7yr)", "LOW (slow standards)", "MODERATE (~8% CapEx)", "NVIDIA Mellanox >90%"),
        ("DC Facility", "LOW (25-40yr)", "LOW (generic asset)", "HIGH (50-70% OpEx)", "Multiple suppliers"),
    ], columns=["Domain", "Collateral Value", "Tech Obsolescence", "Power/Cost Exposure", "Single-Supplier"])

    st.dataframe(risk_data, use_container_width=True, hide_index=True)

    st.subheader("Aggregate Risk by Borrower Type")
    borrower_data = pd.DataFrame([
        ("Hyperscaler (MSFT, GOOG, AMZN, META)", "GPU + networking + facility",
         "CapEx sustainability. $50B+/yr spend. Off-balance-sheet lease exposure ($662B Moody's)."),
        ("Neocloud (CoreWeave, Lambda, Crusoe)", "GPU + HBM + networking",
         "Collateral value risk. GPUs as collateral. Depreciation mismatch vs loan terms."),
        ("DC Developer / Landlord", "Facility shell + power/cooling",
         "Tenant credit risk. If neocloud defaults, can facility be re-leased?"),
        ("Enterprise AI Buyer", "Full stack (DGX/HGX)",
         "Utilisation risk. If AI initiative fails, GPU assets are stranded."),
    ], columns=["Borrower Type", "Primary Exposure", "Key Credit Concern"])
    st.dataframe(borrower_data, use_container_width=True, hide_index=True,
        column_config={"Key Credit Concern": st.column_config.TextColumn(width=450)})

with tab_nvidia:
    st.subheader("NVIDIA Dependency Index")
    nvidia_data = pd.DataFrame([
        ("AI Training GPUs", 95, "AMD ~5%"),
        ("CUDA Software", 95, "Developer lock-in. ~5M devs."),
        ("InfiniBand", 90, "Mellanox acquisition. UEC emerging."),
        ("Data Centre GPUs (overall)", 90, "AMD, ASICs gaining in inference."),
        ("AI Inference GPUs", 85, "ASICs gaining share."),
        ("GPU Lease Pricing", 70, "Competitive market."),
        ("NVLink (chip-chip)", 100, "Proprietary. No alternative."),
        ("NVSwitch", 100, "Proprietary. No alternative."),
    ], columns=["Layer", "NVIDIA Share %", "Notes"])

    fig_nv = go.Figure(go.Bar(x=nvidia_data["NVIDIA Share %"], y=nvidia_data["Layer"], orientation="h",
        text=nvidia_data["NVIDIA Share %"], texttemplate="%{text}%", textposition="outside",
        marker_color=["#22c55e"]*2 + ["#f59e0b"]*2 + ["#3b82f6"]*2 + ["#ef4444"]*2))
    fig_nv.update_layout(height=400, xaxis=dict(range=[0, 110], title="NVIDIA Market Share (%)"),
        yaxis=dict(autorange="reversed"), showlegend=False, margin=dict(l=20, r=60, t=10, b=20))
    st.plotly_chart(fig_nv, use_container_width=True)

    st.subheader("Dependency Reduction Timeline")
    st.markdown("""
| Timeframe | Event | Impact |
|---|---|---|
| 2025-26 | AMD MI350/MI400 ramp | Potential 10-15% training share if ROCm matures |
| 2025-26 | UEC Ethernet for AI | Reduces InfiniBand dependency |
| 2026-27 | AWS Trainium2/3, TPU v6 | Hyperscalers reduce NVIDIA dependency |
| 2026-27 | UCIe chiplet standard | Multi-vendor chiplet assembly |
| 2027-28 | ZLUDA / Triton maturity | Open-source CUDA compatibility |
| 2028+ | Optical interconnects | Could disrupt NVLink advantage |
    """)


