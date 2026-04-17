"""GPU Hardware & Pricing — lease prices, NVIDIA DC GPU performance, and compute efficiency."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.lib.hardware import ARCH_COLOURS, ARCH_ORDER, flagship_per_generation, load_nvidia_dc_gpus
from app.lib.llm_perf import chart_layout

_DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "reference"

CHART_LAYOUT = chart_layout()


def _compute_y_range(scores: list, max_score: float = 100.0, floor: float = 0.0) -> tuple:
    if not scores:
        return (floor, max_score)
    lo = min(scores)
    hi = max(scores)
    y_min = max(floor, lo - lo * 0.10)
    y_max = min(max_score, hi + hi * 0.05)
    if y_max <= y_min:
        y_max = y_min + 1
    return (y_min, y_max)


st.title("GPU Hardware & Pricing")

# ══════════════════════════════════════════════
# GPU LEASE PRICES
# ══════════════════════════════════════════════
st.header("GPU Lease Prices")
st.caption(
    "**What this measures**: Spot lease prices reflect the marginal clearing price for excess supply — "
    "a **stranded asset pricing signal**, not a direct obsolescence measure. "
    "H100 is not technically obsolete; the price decline reflects hyperscaler over-provisioning as Blackwell pulls workloads up-stack. "
    "**Key watch**: H100 spot *re-inflating* would be the more concerning bubble signal — "
    "it would mean demand is accelerating faster than Blackwell can absorb it. "
    "⚠️ VAST.ai is a thin peer-to-peer market — treat spot prices as directional, not precise."
)

gpu_path = _DATA_DIR / "gpu_lease_prices.csv"
if gpu_path.exists():
    df_gpu = pd.read_csv(gpu_path)
    df_gpu["date"] = pd.to_datetime(df_gpu["date"])

    _h100_spot = df_gpu[(df_gpu["gpu_model"] == "H100 80GB") & (df_gpu["commitment"] == "spot")].sort_values("date")
    _h100_od   = df_gpu[(df_gpu["gpu_model"] == "H100 80GB") & (df_gpu["commitment"] == "on-demand")].sort_values("date")
    _b200_od   = df_gpu[(df_gpu["gpu_model"] == "B200") & (df_gpu["commitment"] == "on-demand")].sort_values("date")

    if not _h100_spot.empty:
        _spot_latest = _h100_spot.iloc[-1]["price_per_hour"]
        _spot_peak   = _h100_spot["price_per_hour"].max()
        _spot_pct    = (_spot_latest / _spot_peak - 1) * 100
        _od_latest   = _h100_od.iloc[-1]["price_per_hour"] if not _h100_od.empty else None
        _b200_latest = _b200_od.iloc[-1]["price_per_hour"] if not _b200_od.empty else None
        _gen_gap     = _b200_latest / _spot_latest if _b200_latest else None
        _struct_sprd = _od_latest / _spot_latest if _od_latest else None

        _cm1, _cm2, _cm3, _cm4 = st.columns(4)
        _cm1.metric("H100 Spot (VAST.ai)", f"${_spot_latest:.2f}/hr",
                    f"{_spot_pct:+.0f}% from peak")
        _cm2.metric("H100 On-Demand (Lambda)", f"${_od_latest:.2f}/hr" if _od_latest else "—")
        _cm3.metric("Generation Gap", f"{_gen_gap:.1f}x" if _gen_gap else "—",
                    help="B200 on-demand ÷ H100 spot — compute-per-dollar migration pressure")
        _cm4.metric("Structured/Spot Spread", f"{_struct_sprd:.1f}x" if _struct_sprd else "—",
                    help="Lambda on-demand ÷ VAST spot — widening = structured buyers not paying up = stronger stranded asset signal")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("H100 Price History")
        st.caption("Spot (VAST.ai) vs on-demand (Lambda/CoreWeave) — spread between them is the structured buyer signal")
        df_h100_all = df_gpu[df_gpu["gpu_model"] == "H100 80GB"]
        if not df_h100_all.empty:
            fig_h100 = px.line(
                df_h100_all, x="date", y="price_per_hour",
                color="provider", line_dash="commitment",
                markers=True,
                labels={"price_per_hour": "$/hr", "date": ""},
            )
            fig_h100.update_layout(
                height=380,
                yaxis_title="$/hr",
                legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
                margin=dict(l=0, r=0, t=10, b=80),
            )
            st.plotly_chart(fig_h100, use_container_width=True)

    with col2:
        st.subheader("Generation Gap")
        st.caption("H100 spot vs H100/H200/B200 on-demand — the spread is the compute-per-dollar cost of not upgrading to Blackwell")
        _GEN_COLORS = {
            ("H100 80GB", "spot"):      "#ef4444",
            ("H100 80GB", "on-demand"): "#f59e0b",
            ("H200",      "on-demand"): "#3b82f6",
            ("B200",      "on-demand"): "#22c55e",
        }
        fig_gen = go.Figure()
        for (model, commitment), sub in df_gpu.groupby(["gpu_model", "commitment"]):
            color = _GEN_COLORS.get((model, commitment))
            if color is None:
                continue
            sub = sub.sort_values("date")
            fig_gen.add_trace(go.Scatter(
                x=sub["date"], y=sub["price_per_hour"],
                name=f"{model} ({commitment})",
                mode="lines+markers",
                line=dict(color=color, width=2),
                hovertemplate=f"{model} {commitment}: $%{{y:.2f}}/hr<extra></extra>",
            ))
        fig_gen.update_layout(
            height=380,
            yaxis_title="$/hr",
            legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
            margin=dict(l=0, r=0, t=10, b=80),
        )
        st.plotly_chart(fig_gen, use_container_width=True)

    if not _h100_spot.empty and len(_h100_spot) >= 2:
        _first = _h100_spot.iloc[0]["price_per_hour"]
        _last  = _h100_spot.iloc[-1]["price_per_hour"]
        st.caption(
            f"H100 spot: ${_first:.2f}/hr → ${_last:.2f}/hr "
            f"({(_last/_first - 1)*100:+.0f}% since {_h100_spot.iloc[0]['date'].strftime('%b %Y')}). "
            "For a more robust series, see Epoch AI and SemiAnalysis compute price indices."
        )
else:
    st.info("gpu_lease_prices.csv not found — run /ai-research to populate.")

# ══════════════════════════════════════════════
# COMPUTE & HARDWARE
# ══════════════════════════════════════════════
st.header("Compute & Hardware")

gpu_df = load_nvidia_dc_gpus()

if gpu_df.empty:
    st.warning(
        "NVIDIA hardware data missing. Expected at data/external/ml_hardware.csv "
        "(sourced from https://epoch.ai/data/ml_hardware.csv). Run `/ai-research` to refresh."
    )
else:
    st.subheader("NVIDIA Data-Centre GPU Performance")
    with st.expander("About this chart"):
        st.markdown("**What it shows.** Peak dense Tensor-FP16/BF16 throughput for each NVIDIA data-centre GPU SKU, plotted against release date. Log scale. Coloured by architecture family (Volta → Ampere → Hopper → Blackwell).")
        st.markdown("**Why it matters.** Training FLOPS per chip has grown ~20× in 8 years (125 TFLOPS V100 → 2500 TFLOPS GB300). Combined with cluster scaling, this is what enables each new frontier-model generation.")
        st.markdown("**Source.** Epoch AI — *Machine Learning Hardware* dataset (epoch.ai/data/machine-learning-hardware), CC-BY licence.")

    fig_gpu = go.Figure()
    for arch in ARCH_ORDER:
        sub = gpu_df[gpu_df["arch"] == arch]
        if sub.empty:
            continue
        hbm_txt = sub["hbm_gb"].map(lambda v: f"{v:.0f} GB HBM" if pd.notna(v) else "HBM —")
        bw_txt = sub["mem_bw_gb_s"].map(lambda v: f"{v:,.0f} GB/s" if pd.notna(v) else "bw —")
        price_txt = sub["price_usd"].map(lambda v: f"${v:,.0f}" if pd.notna(v) else "price —")
        custom = list(zip(sub["tdp_w"].fillna(0), hbm_txt, bw_txt, price_txt))
        fig_gpu.add_trace(go.Scatter(
            x=sub["release_date"],
            y=sub["tflops_tensor_fp16"],
            text=sub["name"],
            customdata=custom,
            name=arch,
            mode="markers",
            marker=dict(size=10, color=ARCH_COLOURS[arch], line=dict(width=1, color="#1f2937")),
            hovertemplate=(
                "%{text}<br>"
                "%{y:,.0f} TFLOPS (Tensor FP16/BF16)<br>"
                "TDP: %{customdata[0]:.0f} W<br>"
                "%{customdata[1]}<br>"
                "%{customdata[2]}<br>"
                "%{customdata[3]}"
                f"<extra>{arch}</extra>"
            ),
        ))

    fig_gpu.update_layout(
        yaxis_title="Tensor-FP16/BF16 Performance (TFLOPS)",
        yaxis_type="log",
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_gpu, use_container_width=True)

    st.subheader("Performance per Watt — Flagship Line")
    with st.expander("About this chart"):
        st.markdown("**What it shows.** Tensor-FP16 TFLOPS divided by TDP (W) for the flagship SKU of each NVIDIA data-centre generation.")
        st.markdown("**Why it matters.** Power (not silicon) is the binding constraint on hyperscale training clusters. Perf-per-watt determines whether the next cluster can be built inside a given power envelope.")
        st.markdown("**Source.** Derived from Epoch AI ML Hardware dataset.")

    flagships = flagship_per_generation(gpu_df)
    flagships = flagships[flagships["tdp_w"].notna()]
    flagships["perf_per_watt"] = flagships["tflops_tensor_fp16"] / flagships["tdp_w"]

    fig_ppw = go.Figure()
    fig_ppw.add_trace(go.Scatter(
        x=flagships["release_date"],
        y=flagships["perf_per_watt"],
        text=flagships["name"] + " (" + flagships["arch"] + ")",
        mode="lines+markers",
        line=dict(color="#10b981", width=2),
        marker=dict(size=10, color="#10b981"),
        hovertemplate="%{text}<br>%{y:.2f} TFLOPS/W<extra></extra>",
    ))

    y_min, y_max = _compute_y_range(flagships["perf_per_watt"].tolist(), max_score=10, floor=0.1)
    fig_ppw.update_layout(
        yaxis_title="Tensor FP16 TFLOPS per Watt",
        yaxis_range=[y_min, y_max],
        **CHART_LAYOUT,
    )
    st.plotly_chart(fig_ppw, use_container_width=True)
