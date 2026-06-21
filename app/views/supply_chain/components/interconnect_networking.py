"""
Lane 4: Interconnect & Networking — NVLink, InfiniBand, Ethernet.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.title("Interconnect & Networking")

tab_nv, tab_ib, tab_top, tab_deep = st.tabs(["NVLink & NVSwitch", "InfiniBand vs Ethernet", "Scale & Topology", "Deep Dive"])

with tab_nv:
    st.header("NVLink Generational Evolution")
    nvlink_data = pd.DataFrame([
        ("NVLink 1", "Pascal (P100)", "2016", "160", "20", "—", "—"),
        ("NVLink 2", "Volta (V100)", "2017", "300", "37.5", "NVSwitch 1", "16"),
        ("NVLink 3", "Ampere (A100)", "2020", "600", "50", "NVSwitch 2", "16"),
        ("NVLink 4", "Hopper (H100)", "2022", "900", "56.25", "NVSwitch 3", "32"),
        ("NVLink 5", "Blackwell (B200)", "2024", "1,800", "112.5", "NVSwitch 4", "72"),
        ("NVLink 6", "Rubin (2026E)", "2026", "3,600 (est.)", "~200+", "NVSwitch 5", "144+ (est.)"),
    ], columns=["Generation", "Platform", "Year", "BW/GPU (GB/s)", "BW/Link (GB/s)", "Switch", "Max GPUs"])

    fig_nv = go.Figure()
    fig_nv.add_trace(go.Bar(x=nvlink_data["Generation"], y=nvlink_data["BW/GPU (GB/s)"],
        text=nvlink_data["BW/GPU (GB/s)"], texttemplate="%{text:,}", textposition="outside",
        marker_color=["#93c5fd", "#60a5fa", "#3b82f6", "#2563eb", "#1d4ed8", "#1e3a5f"]))
    fig_nv.update_layout(height=380, yaxis_title="Bandwidth per GPU (GB/s)", margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig_nv, use_container_width=True)
    st.caption("NVLink bandwidth per GPU grown ~11x from Pascal to Blackwell. Each generation backward-incompatible.")
    st.dataframe(nvlink_data, use_container_width=True, hide_index=True)

with tab_ib:
    st.header("InfiniBand vs Ethernet")
    ib_data = pd.DataFrame([
        ("InfiniBand NDR400", "400", "NVIDIA Quantum-2", "~$1,500-2,000/port", "~1-2 us", "NVIDIA monopoly", "Lowest latency, RDMA-native"),
        ("InfiniBand XDR800", "800", "NVIDIA Quantum-X800", "~$2,500-3,500/port", "<1 us", "NVIDIA monopoly", "Next-gen. Premium pricing."),
        ("400GbE (RoCEv2)", "400", "Broadcom, Marvell", "~$800-1,200/port", "~3-5 us", "Multi-vendor", "Cheaper, multi-vendor"),
        ("800GbE (UEC)", "800", "Broadcom, Marvell, Cisco", "~$1,500-2,500/port", "~2-4 us", "UEC consortium", "Breaking InfiniBand lock-in"),
    ], columns=["Standard", "Speed (Gb/s)", "Silicon", "Cost/Port", "Latency", "Supplier", "Assessment"])
    st.dataframe(ib_data, use_container_width=True, hide_index=True)

    st.subheader("PCIe Evolution")
    pcie_data = pd.DataFrame([
        ("PCIe 4.0", "2017", "16", "~2 GB/s per lane", "A100 (x16 = 32 GB/s)"),
        ("PCIe 5.0", "2019", "32", "~4 GB/s per lane", "H100 (x16 = 64 GB/s)"),
        ("PCIe 6.0", "2022", "64", "~8 GB/s per lane", "B200 (x16 = 128 GB/s)"),
        ("PCIe 7.0", "2025", "128", "~16 GB/s per lane", "Rubin-era (x16 = 256 GB/s)"),
    ], columns=["Gen", "Year", "GT/s", "Bandwidth/Lane", "GPU Context"])
    st.dataframe(pcie_data, use_container_width=True, hide_index=True)

with tab_top:
    st.header("Scale-Up vs Scale-Out")
    scale_data = pd.DataFrame([
        ("Scale-Up", "NVLink/NVSwitch", "72-576 GPUs", "Coherent memory", "130 TB/s (NVL72)", "GPU-to-GPU in rack"),
        ("Scale-Out", "InfiniBand/Ethernet", "1,000-100,000+ GPUs", "Message-passing", "400-800 Gb/s per link", "Rack-to-rack"),
    ], columns=["Type", "Interconnect", "Scale", "Memory Model", "Bandwidth", "Scope"])
    st.dataframe(scale_data, use_container_width=True, hide_index=True)

    st.subheader("Network Topology Patterns")
    topo_data = pd.DataFrame([
        ("Fat-Tree", "Full bisection bandwidth", "Highest cost", "Most AI training", "Best perf, most expensive"),
        ("Dragonfly", "High radix, fewer switches", "Medium cost", "HPC, some AI", "Good perf/cost"),
        ("Rail-Optimized", "GPU-to-GPU aware", "Medium cost", "NVIDIA AI training", "GPU traffic optimized"),
        ("Torus/Mesh", "Nearest-neighbor only", "Lowest cost", "Tightly coupled HPC", "Cheap, high latency at scale"),
    ], columns=["Topology", "Feature", "Cost", "Best For", "Tradeoffs"])
    st.dataframe(topo_data, use_container_width=True, hide_index=True)

with tab_deep:
    st.header("Deep Dive")

    with st.expander("Why NVIDIA Owns InfiniBand — The Mellanox Acquisition"):
        st.markdown("""
**2019: NVIDIA acquires Mellanox for $6.9B**, outbidding Microsoft and Intel.

**Strategic rationale:** Without InfiniBand, large GPU clusters cannot communicate efficiently. By owning both the GPU and the networking, NVIDIA created a vertically integrated stack that competitors struggle to replicate. The "Superpod" concept — groups of GPU servers networked together — is built on Mellanox InfiniBand.

**UEC (Ultra Ethernet Consortium):** Formed to break this lock-in. Members include AMD, Broadcom, Cisco, Intel, Meta, Microsoft. Developing Ethernet-based alternatives that match InfiniBand performance at lower cost with multi-vendor support.

**Credit implication:** InfiniBand is a single-supplier dependency layered on top of the GPU single-supplier dependency. A borrower with an InfiniBand-based cluster has two NVIDIA lock-ins. UEC maturity (2026-27) is the key mitigant.
        """)

    with st.expander("RDMA — Why It Matters"):
        st.markdown("""
RDMA (Remote Direct Memory Access) allows one computer to access another's memory directly, bypassing the CPU and operating system entirely.

**Why GPU clusters need RDMA:** AI training requires constant GPU-to-GPU data exchange. Without RDMA, each transfer goes: GPU -> CPU -> OS -> network -> OS -> CPU -> GPU. With RDMA: GPU -> network -> GPU. This eliminates ~50-80% of latency and frees CPU cycles.

**RoCE (RDMA over Converged Ethernet):** RDMA over standard Ethernet. Cheaper but historically higher latency than native InfiniBand. UEC is closing this gap.

**GPU Direct RDMA:** NVIDIA technology that allows GPUs to directly initiate RDMA transfers without CPU involvement. AMD equivalent: ROCm RDMA. Both are essential for large-scale training.
        """)

    with st.expander("The Optical Transition"):
        st.markdown("""
**Copper limits:** ~3 meters at 200G PAM4 signaling. Beyond that, signal degrades too much for reliable data transmission.

**Co-Packaged Optics (CPO):** Optical transceivers integrated directly into switch ASIC package. Reduces power 30-50%, increases port density. Volume ramp begins 2026.

**Chip-to-chip optical:** Ayar Labs ($500M Series E), Lightmatter ($400M Series D) developing optical interconnects that could eventually replace copper for NVLink-level distances. When this happens (2028+), it could disrupt NVIDIA's NVLink advantage if optical standards become open.

**Credit implication:** Networking equipment purchased today (copper-based InfiniBand/Ethernet switches) may face a transition to optical in 3-5 years. CPO switches are drop-in replacements, but chip-to-chip optical could fundamentally change cluster architecture.
        """)

    with st.expander("Credit Implications"):
        st.markdown("""
**Collateral value risk:** Networking depreciates slower (5-7yr) than GPUs (3-6yr). InfiniBand switches retain value better than GPUs but face transition risk from Ethernet/UEC.

**Concentration risk:** NVIDIA Mellanox >90% InfiniBand. UEC is the first credible competitive threat but still maturing. Broadcom and Marvell provide Ethernet alternatives.

**Cost exposure:** Networking = ~8-14% of cluster CapEx. This scales with GPU count — larger clusters spend proportionally more on networking.

**Transition risk:** Two transitions in play: (a) InfiniBand -> Ethernet via UEC (2026-27), and (b) copper -> optics (2026-28). Borrowers with InfiniBand-only clusters face competitive pressure as UEC matures. Copper-based networking equipment faces optical transition in 3-5 years.
        """)
