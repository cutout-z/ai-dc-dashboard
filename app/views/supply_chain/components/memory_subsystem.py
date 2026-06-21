"""
Lane 2: Memory Subsystem — HBM, GDDR, memory wall.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.title("Memory Subsystem")

st.header("HBM vs GDDR")
hbm_gddr = pd.DataFrame([
    ("HBM3e", "3D-stacked on interposer", "819.2-bit", "8,000 GB/s", "36 GB", "1.2W", "~$15-18/GB", "~10 mm", "AI training/inference", "H200, B200"),
    ("HBM3", "3D-stacked on interposer", "614.4-bit", "3,350 GB/s", "24 GB", "0.8W", "~$12-15/GB", "~10 mm", "AI training/inference", "H100, MI300X"),
    ("GDDR7", "Discrete on PCB", "32-bit", "1,536 GB/s", "24 GB", "1.0W", "~$4-6/GB", "~50-80 mm", "Gaming, edge inference", "RTX 5090"),
    ("GDDR6X", "Discrete on PCB", "24-bit", "1,008 GB/s", "24 GB", "1.5W", "~$3-5/GB", "~50-80 mm", "Gaming, workstation", "RTX 4090"),
    ("LPDDR5X", "Discrete on PCB (CPU)", "64-bit", "500 GB/s", "128 GB", "0.5W", "~$3-4/GB", "~30-50 mm", "Mobile, Grace CPU", "Grace-Hopper"),
], columns=["Type", "Packaging", "Bus Width", "Bandwidth", "Capacity", "Power", "Cost/GB", "Distance to GPU", "Use Case", "Products"])

st.dataframe(hbm_gddr, use_container_width=True, hide_index=True)
st.caption("HBM advantage: 3D stacking + interposer proximity = orders of magnitude more bandwidth. Cost: ~3-4x per GB, consumes ~3x wafer capacity.")

st.header("HBM Generational Evolution")
hbm_gen = pd.DataFrame([
    ("HBM2", "2016", "256", "2.0", "256", "4-hi", "2.4", "1.2", "P100, V100"),
    ("HBM2e", "2018", "307", "3.6", "460", "8-hi", "3.2", "1.5", "A100"),
    ("HBM3", "2022", "450", "6.4", "819", "12-hi", "5.2", "2.5", "H100"),
    ("HBM3e", "2023", "560", "8.0", "1,024", "12-hi", "7.2", "3.5", "H200, B200"),
    ("HBM4", "2026", "700", "12.8", "2,048", "16-hi", "11.0", "5.0", "Rubin"),
], columns=["Gen", "Year", "Speed (GB/s/pin)", "BW/Stack", "Bus Width", "Stack", "Per-GPU BW (TB/s)", "Power (W)", "Platforms"])

fig_hbm = go.Figure()
fig_hbm.add_trace(go.Scatter(x=hbm_gen["Year"], y=hbm_gen["Per-GPU BW (TB/s)"], mode="lines+markers+text",
    text=hbm_gen["Gen"], textposition="top center", line=dict(color="#3b82f6", width=3), marker=dict(size=12)))
fig_hbm.update_layout(height=400, yaxis_title="Bandwidth (TB/s)", yaxis_type="log", xaxis_type="category",
    margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig_hbm, use_container_width=True)
st.dataframe(hbm_gen, use_container_width=True, hide_index=True)

st.header("The Memory Wall — Bytes per FLOP")
mem_wall = pd.DataFrame([
    ("A100 (Ampere)", "2020", "312", "2.0", "6.41", "Comfortable margin"),
    ("H100 (Hopper)", "2022", "1,979", "3.35", "1.69", "Wall approaching"),
    ("H200 (Hopper+)", "2023", "1,979", "4.8", "2.43", "Relief from HBM3e"),
    ("B200 (Blackwell)", "2024", "4,500", "8.0", "1.78", "Wall still present"),
    ("Rubin (est.)", "2026", "14,000", "11.0", "0.79", "Bandwidth-starved"),
], columns=["GPU", "Year", "FP16 TFLOPS", "HBM BW (TB/s)", "Bytes/FLOP", "Assessment"])

fig_wall = go.Figure()
fig_wall.add_trace(go.Bar(x=mem_wall["GPU"], y=mem_wall["Bytes/FLOP"], text=mem_wall["Bytes/FLOP"],
    texttemplate="%{text:.2f}", textposition="outside",
    marker_color=["#22c55e", "#f59e0b", "#22c55e", "#f59e0b", "#ef4444"]))
fig_wall.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Memory-starved")
fig_wall.update_layout(height=380, yaxis_title="Bytes per FLOP (higher = better)", margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig_wall, use_container_width=True)
st.caption("Below 1.0 bytes/FLOP, compute is memory-starved. Rubin (2026) projected at 0.79 B/F.")

st.header("HBM Supply Chain")
hbm_supply = pd.DataFrame([
    ("SK Hynix", "HBM3e", ">90%", "Sold out through H2 2026", "Dominant"),
    ("Samsung", "HBM3e", "<10%", "Qualification issues with NVIDIA", "Challenger"),
    ("Micron", "HBM3e", "~5%", "Qualified. Ramping 2025-26.", "Emerging"),
    ("SK Hynix", "HBM4", "~50-60% (est.)", "First mover. Mass production H2 2026.", "Leading"),
    ("Samsung", "HBM4", "~30-40% (est.)", "Hybrid bonding leadership.", "Competitive"),
], columns=["Supplier", "Generation", "Share", "Status", "Position"])
st.dataframe(hbm_supply, use_container_width=True, hide_index=True)

# Deep Dive
st.markdown("---")
st.header("Deep Dive")

with st.expander("How HBM Works — 3D Stacking"):
    st.markdown("""
HBM is a 3D-stacked DRAM architecture using Through-Silicon Vias (TSVs) to vertically integrate multiple memory dies.

1. **DRAM dies** thinned to ~30-50 um and vertically aligned.
2. **TSVs** — microscopic vertical interconnects drilled through silicon — pass signals and power between layers. HBM3E has thousands of TSVs, each ~5-10 um diameter.
3. **Microbumps** connect TSVs between adjacent dies. Stack sits on a **base logic die** that buffers signals.
4. Stack bonded to a **silicon interposer** carrying fine-pitch wiring (~3,000 traces per HBM stack) to the GPU die.

**Physical distance advantage:** HBM sits on-interposer, ~1 mm from the GPU die. GDDR sits on-PCB, ~20-50 mm away. Shorter trace = lower latency, lower power, wider bus.

**Shoreline constraint:** HBM stacks must sit on the edges of the GPU die because interposer routing density requires direct adjacency. This limits a GPU to 6-8 HBM stacks, creating a hard ceiling on per-GPU bandwidth.
    """)

with st.expander("Why Not GDDR? — The Fundamental Trade"):
    st.markdown("""
The fundamental trade is **bandwidth at any cost** vs. **cost-efficient capacity**.

| | HBM3E | GDDR7 | Why It Matters |
|---|---|---|---|
| Bandwidth per device | 1.2 TB/s (stack) | 112 GB/s (chip) | ~10x HBM advantage |
| Bus width | 1,024-bit | 32-bit | HBM: 32x wider |
| Power efficiency | ~3.5 pJ/bit | ~7 pJ/bit | HBM: 2x more efficient |
| Cost per GB | ~$10-15 | ~$5-7 | GDDR: 2-3x cheaper |
| Latency | ~80-100 ns | ~15-20 ns | GDDR has lower raw latency |

For AI training and large-model inference, memory bandwidth is the binding constraint — not compute, not capacity, not cost. HBM delivers ~6-8x the bandwidth per package area. The cost penalty (5-6x per GB vs DDR5) is accepted because the workload cannot run without it.

When GDDR is sufficient: gaming, edge inference, small-model serving, and workstations.
    """)

with st.expander("Memory Compression & Sparsity"):
    st.markdown("""
Several techniques reduce effective memory bandwidth demand without increasing physical bandwidth:

**Structured sparsity (2:4):** 2 out of every 4 weights can be zero. The hardware skips them, effectively doubling throughput. Available from Ampere onward. Real-world gain: ~1.7-1.9x (not quite 2x due to overhead).

**Quantization:** Lower precision reduces memory pressure.
- FP16 -> FP8: ~2x reduction in memory bandwidth per token
- FP8 -> FP4: another ~2x reduction
- FP4 -> INT4: further reduction for inference

**KV-cache compression:** For inference, the key-value cache storing previous tokens is the largest memory consumer. Techniques like TurboQuant achieve ~6x compression. This extends the useful life of memory-constrained GPUs for inference.
    """)

with st.expander("CXL Memory Pooling"):
    st.markdown("""
CXL (Compute Express Link) enables memory disaggregation — pooling memory across servers so GPUs can access more memory than physically attached.

- **CXL 1.1/2.0:** Device-attached memory. Single host.
- **CXL 3.0:** Multi-host shared memory. Enables memory pooling across servers.
- **CXL 3.1:** Peer-to-peer DMA. GPUs can directly access CXL-attached memory.

For AI clusters: CXL could enable GPU clusters to share a large memory pool, reducing the constraint of per-GPU HBM capacity. But CXL bandwidth (~64 GB/s per x16 link) is 2 orders of magnitude below HBM (~1,000+ GB/s), limiting its use to capacity-tier (not bandwidth-tier) workloads.
    """)

with st.expander("Credit Implications"):
    st.markdown("""
**Collateral value risk:** HBM is generation-locked to specific GPUs. HBM3e GPUs cannot use HBM4. An H200 GPU (HBM3e) has zero standalone memory value when HBM4 GPUs ship. HBM represents 35-47% of AI server BOM cost.

**Concentration risk:** SK Hynix controls >90% of HBM3e supply. Samsung and Micron are ramping but cannot fill the gap. HBM consumes ~3x wafer capacity per GB vs DDR — supply expansion is constrained by fab capacity.

**Cost exposure:** HBM = 35-47% of AI server manufacturing cost. This is the single largest line item. HBM pricing power rests with suppliers, not GPU vendors.

**Transition risk:** HBM3e -> HBM4 (2026) is a structural shift — 2,048-bit bus, 16-hi stacking, hybrid bonding. HBM4 marks the shift from microbump to Cu-Cu hybrid bonding, requiring new manufacturing equipment and qualification cycles. Inventory of HBM3e may face obsolescence if the transition accelerates.
    """)
