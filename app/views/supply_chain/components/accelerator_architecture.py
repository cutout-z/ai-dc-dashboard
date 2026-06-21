"""
Lane 1: AI Accelerator Architecture — GPU/TPU/ASIC evolution.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.title("AI Accelerator Architecture")

st.header("NVIDIA Data Centre GPU — Generational Evolution")
gpu_data = pd.DataFrame([
    {"Architecture": "Volta", "GPU": "V100", "Year": "2017", "Process": "12nm FFN", "Transistors (B)": 21.1,
     "Die Size (mm2)": "815", "FP16 TFLOPS": 31.4, "HBM": "HBM2", "BW (TB/s)": 0.9, "TDP (W)": 300, "NVLink": "v2", "SMs": 80},
    {"Architecture": "Ampere", "GPU": "A100", "Year": "2020", "Process": "7nm N7", "Transistors (B)": 54.2,
     "Die Size (mm2)": "826", "FP16 TFLOPS": 78, "HBM": "HBM2e", "BW (TB/s)": 2.0, "TDP (W)": 400, "NVLink": "v3", "SMs": 108},
    {"Architecture": "Hopper", "GPU": "H100", "Year": "2022", "Process": "4nm 4N", "Transistors (B)": 80,
     "Die Size (mm2)": "814", "FP16 TFLOPS": 1979, "HBM": "HBM3", "BW (TB/s)": 3.35, "TDP (W)": 700, "NVLink": "v4", "SMs": 132},
    {"Architecture": "Hopper+", "GPU": "H200", "Year": "2023", "Process": "4nm 4N", "Transistors (B)": 80,
     "Die Size (mm2)": "814", "FP16 TFLOPS": 1979, "HBM": "HBM3e", "BW (TB/s)": 4.8, "TDP (W)": 700, "NVLink": "v4", "SMs": 132},
    {"Architecture": "Blackwell", "GPU": "B200", "Year": "2024", "Process": "4nm 4NP", "Transistors (B)": 208,
     "Die Size (mm2)": "dual-die", "FP16 TFLOPS": 4500, "HBM": "HBM3e", "BW (TB/s)": 8.0, "TDP (W)": 1000, "NVLink": "v5", "SMs": 148},
    {"Architecture": "BlackwellU", "GPU": "B300", "Year": "2025", "Process": "4nm 4NP", "Transistors (B)": 208,
     "Die Size (mm2)": "dual-die", "FP16 TFLOPS": 7500, "HBM": "HBM3e", "BW (TB/s)": 8.0, "TDP (W)": 1200, "NVLink": "v5", "SMs": 148},
])

st.dataframe(gpu_data, use_container_width=True, hide_index=True,
    column_config={
        "Transistors (B)": st.column_config.NumberColumn(format="%.0f B"),
        "FP16 TFLOPS": st.column_config.NumberColumn(format="%,.0f"),
        "TDP (W)": st.column_config.NumberColumn(format="%,.0f W"),
    })
st.caption("B200/B300 use two reticle-limited dies connected via 10 TB/s NV-HBI. First chiplet GPU generation.")

col1, col2 = st.columns(2)
with col1:
    fig_flops = px.line(gpu_data, x="Year", y="FP16 TFLOPS", text="GPU", markers=True,
        title="Tensor FP16 Performance (TFLOPS, log scale)", color_discrete_sequence=["#3b82f6"])
    fig_flops.update_traces(textposition="top center", marker=dict(size=12))
    fig_flops.update_layout(height=380, yaxis_type="log", margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_flops, use_container_width=True)
with col2:
    fig_pwr = px.scatter(gpu_data, x="Year", y="TDP (W)", size="FP16 TFLOPS", text="GPU",
        title="TDP vs Year (bubble = compute)", color_discrete_sequence=["#ef4444"])
    fig_pwr.update_traces(textposition="top center")
    fig_pwr.update_layout(height=380, yaxis_title="TDP (W)", margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_pwr, use_container_width=True)

st.header("Architecture Comparison")
comp_data = pd.DataFrame([
    ("NVIDIA", "Blackwell (B200)", "20,480 CUDA + 640 Tensor", "TSMC 4NP", "208B (dual-die)", "HBM3e 192GB", "1000W", "NVLink 5 (1.8 TB/s)", "CUDA (proprietary)"),
    ("AMD", "Instinct MI300X", "19,456 Stream + 304 Matrix", "TSMC 5/6nm", "153B", "HBM3 192GB", "750W", "Infinity Fabric", "ROCm (open source)"),
    ("Google", "TPU v5p", "Systolic Array (MXU)", "TSMC 5nm", "~90B (est.)", "HBM3 96GB", "450W (est.)", "ICI (proprietary)", "JAX/TensorFlow"),
    ("AWS", "Trainium2", "NeuronCores v2", "TSMC 5nm", "~80B (est.)", "HBM3e 96GB", "~500W (est.)", "NeuronLink", "Neuron SDK (AWS)"),
    ("Cerebras", "WSE-3", "900,000 (wafer-scale)", "TSMC 5nm", "4,000B", "44GB SRAM on-chip", "~15kW (per wafer)", "SwarmX (on-wafer)", "Cerebras SDK"),
], columns=["Vendor", "Architecture", "Cores", "Process", "Transistors", "Memory", "TDP", "Interconnect", "Software"])
st.dataframe(comp_data, use_container_width=True, hide_index=True)

# Deep Dive
st.markdown("---")
st.header("Deep Dive")

with st.expander("CUDA Core & SM Evolution"):
    st.markdown("""
NVIDIA's Streaming Multiprocessor (SM) is the fundamental compute unit. Each generation roughly doubles SM count AND per-SM throughput, yielding ~4x total compute jumps.

**Core ratios per SM:**
- **Volta (V100):** 64 FP32 + 32 INT32 + 8 Tensor Cores per SM. 80 SMs. First-gen Tensor Cores.
- **Ampere (A100):** 64 FP32 + 32 INT32 + 4 Tensor Cores per SM. 108 SMs. Doubled Tensor throughput despite half the count.
- **Hopper (H100):** 128 FP32 + 64 INT32 + 4 Tensor Cores per SM. 132 SMs. Transformer Engine.
- **Blackwell (B200):** 128 FP32 + 4 Tensor Cores per SM. 148 SMs. New Tensor Memory (TMEM).

**Credit insight:** A 3-year-old GPU is economically stranded for frontier training because each generation delivers 4x total compute. This is why GPU depreciation is much faster than accounting schedules suggest.
    """)

with st.expander("Tensor Core Generations"):
    st.markdown("""
Tensor Cores are dedicated matrix-multiply-accumulate (MMA) units. They execute a 4x4x4 matrix multiply in a single cycle: D = A x B + C.

**Generational progression:**
- **Volta (v1, 2017):** FP16 only. 125 TFLOPS. First dedicated AI hardware in GPUs.
- **Turing (v2, 2018):** Added INT8/INT4 for inference. Consumer-focused.
- **Ampere (v3, 2020):** TF32, FP64, BF16, INT8, INT4, INT1. 2:4 structured sparsity (2x throughput).
- **Hopper (v4, 2022):** FP8 (Transformer Engine). Dynamic precision switching. 4x Ampere throughput.
- **Blackwell (v5, 2024):** FP4, FP6. Second-gen Transformer Engine. 2.5-5x Hopper throughput depending on precision.

**Sparsity:** 2:4 structured sparsity means 2 out of every 4 values can be zero — the hardware skips them, giving 2x effective throughput. Only Ampere and later support this.
    """)

with st.expander("Process Nodes & Die Sizes — Why They Matter"):
    st.markdown("""
### What a Process Node Actually Is

A process node is the manufacturing technology used to fabricate a chip. The number (e.g. "4nm") is a marketing label, not a physical measurement. It roughly corresponds to the smallest feature the lithography tools can print, but what actually matters is **transistor density** — how many transistors you can fit per square millimetre.

### Why Smaller Nodes Matter

**1. More transistors per chip.** Each new node roughly doubles transistor density. V100 (12nm, 2017) packed ~33 million transistors per mm2. H100 (4nm, 2022) packs ~150 million — nearly 5x more. This means a chip of the same size can have 5x the compute units, cache, and specialised hardware.

**2. Better power efficiency.** Smaller transistors switch faster and use less energy per operation. This is why H100 (4nm) delivers ~60x more FP16 TFLOPS than V100 (12nm) while consuming only ~2.3x more power. Without node shrinks, GPU performance gains would require proportionally more power — and we are already hitting the thermal wall at 1,000-1,200W per GPU.

**3. Economics of die area.** Chip cost scales with die area (larger die = fewer chips per wafer = higher cost per chip). A smaller node lets you pack more compute into the same die area, keeping per-chip costs manageable even as transistor counts explode from 21B (V100) to 208B (B200).

### The Generation-by-Generation Story

| Node | Year | Density (MTr/mm2) | What It Enabled |
|---|---|---|---|
| 12nm (Volta) | 2017 | ~33 | First Tensor Cores. HBM2. Baseline AI GPU. |
| 7nm (Ampere) | 2020 | ~91 | 2.5x more transistors. TF32, sparsity, MIG. |
| 4nm (Hopper) | 2022 | ~150 | FP8 Transformer Engine. 4x Ampere throughput. |
| 4NP (Blackwell) | 2024 | ~165 | Two dies (reticle limit exceeded). FP4. |
| 3nm (Rubin) | 2026 | ~215 | HBM4. First 3nm AI GPU. |
| N2 (Feynman) | 2028 | ~280 | GAA transistors. Backside power delivery. |

### The Reticle Limit — Why B200 Is Two Dies

A single die cannot exceed ~858 mm2 — that is the maximum area the lithography tool's light beam can expose in one shot. A100 and H100 both maxed out near this limit (~814-826 mm2). To grow beyond it, NVIDIA had to split B200 into two dies connected by a 10 TB/s bridge (NV-HBI). This is the chiplet era: all future high-end GPUs will stitch multiple smaller dies together rather than trying to make one giant die.

### Credit Relevance

- **Collateral obsolescence accelerates with node cadence.** A GPU on an old node (e.g. 7nm A100) cannot be upgraded — the entire chip must be replaced. Each node transition strands the previous generation.
- **Node shrinks are slowing.** The jump from 7nm to 4nm delivered ~1.6x density (not 2x). N3 to N2 is projected at ~1.3x. Future GPU gains will come more from architecture and packaging than from process shrinks alone — but those architectural gains require new chips, not upgrades.
- **TSMC is the only foundry delivering these nodes at volume.** Any disruption to TSMC's N3/N2 ramp delays the entire AI GPU roadmap. This is a single-supplier risk embedded in every GPU generation.
    """)

with st.expander("GPU Virtualization (MIG)"):
    st.markdown("""
**Multi-Instance GPU (MIG)** partitions one physical GPU into up to 7 isolated instances, each with dedicated compute, memory, and cache.

- **A100:** Up to 7 instances (1x 80GB, 2x 40GB, 3x 20GB, 7x 10GB configs).
- **H100:** Up to 7 instances. Improved isolation. Each MIG instance appears as a separate GPU to software.
- **B200:** Enhanced MIG with confidential computing support.

**Why this matters for credit:** MIG enables cloud providers to sell fractional GPUs, increasing revenue per GPU. A neocloud with MIG-enabled GPUs can serve more customers per physical unit, improving debt service coverage. GPUs without MIG (older generations) generate less revenue per unit.

**AMD alternative:** MxGPU (SR-IOV-based). Less granular than MIG but works across the AMD stack. Intel GPU virtualization is still maturing.
    """)

with st.expander("Software-Hardware Coupling"):
    st.markdown("""
The software stack determines which hardware can be used for AI workloads. This creates a moat: hardware without software support is useless.

| Software Stack | Hardware Support | Maturity | Lock-in Risk |
|---|---|---|---|
| **CUDA** | NVIDIA only | Mature (15+ years) | High — proprietary, 5M+ developers |
| **ROCm** | AMD | Maturing (v7.0) | Low — open source |
| **JAX** | Google TPU, GPU (via XLA) | Mature at Google | Medium — TPU-optimised |
| **Neuron SDK** | AWS Trainium/Inferentia | Maturing | Low — AWS-only |
| **Triton** | NVIDIA, AMD (via OpenXLA) | Growing | Low — open source, hardware-agnostic |
| **ZLUDA** | AMD (CUDA compatibility) | Early | Low — runs unmodified CUDA on AMD |

**Credit insight:** The CUDA moat is the single largest barrier to competitive GPU adoption. If ZLUDA or Triton reach production maturity (2027-28), AMD GPUs become viable alternatives to NVIDIA, potentially reducing GPU collateral concentration risk.
    """)

with st.expander("Credit Implications"):
    st.markdown("""
**Collateral value risk:** GPU economic life is 18-36 months for frontier training. Each generation delivers 2-4x performance improvement, making previous generations economically uncompetitive. Accounting depreciation of 5-6 years far exceeds economic life.

**Concentration risk:** NVIDIA controls ~95% of AI training GPU market. TSMC manufactures essentially all advanced AI chips. Dual dependency: if either supplier fails, no AI chips ship.

**Cost exposure:** GPU TDP has grown from 300W (V100) to 1,200W (B300). Power costs represent the dominant OpEx for AI clusters. A 1,000 GPU cluster at $0.08/kWh costs ~$560K/year in power alone.

**Transition risk:** The GPU-to-ASIC shift (Google TPU, AWS Trainium) is accelerating. ASICs now dominate inference and are targeting training parity by 2027-29. A GPU-heavy collateral portfolio faces competitive displacement risk.
    """)
