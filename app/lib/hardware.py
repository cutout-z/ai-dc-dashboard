"""NVIDIA data-centre GPU performance data, sourced from Epoch AI's ML Hardware dataset.

Source: https://epoch.ai/data/ml_hardware.csv (CC-BY).
Cached locally at data/external/ml_hardware.csv. Refresh via /ai-research skill.

Exposes a loader that returns a DataFrame of NVIDIA data-centre GPUs with
normalised units (TFLOPS, GB, GB/s, W) and an inferred architecture family
(Volta / Ampere / Hopper / Blackwell).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

ML_HARDWARE_CSV = Path(__file__).parent.parent.parent / "data" / "external" / "ml_hardware.csv"

# SKU prefix → architecture family
_ARCH_RULES = [
    (re.compile(r"\bV100\b"), "Volta"),
    (re.compile(r"\bA100\b"), "Ampere"),
    (re.compile(r"\bL40\b"), "Ada Lovelace"),
    (re.compile(r"\bH100\b|\bH200\b|\bH800\b|\bGH100\b|\bGH200\b"), "Hopper"),
    (re.compile(r"\bB100\b|\bB200\b|\bGB200\b|\bB300\b|\bGB300\b"), "Blackwell"),
]

# Display order for legend (oldest → newest)
ARCH_ORDER = ["Volta", "Ampere", "Ada Lovelace", "Hopper", "Blackwell"]

ARCH_COLOURS = {
    "Volta":         "#6b7280",
    "Ampere":        "#3b82f6",
    "Ada Lovelace":  "#a855f7",
    "Hopper":        "#10b981",
    "Blackwell":     "#f59e0b",
}


def _classify_arch(name: str) -> str | None:
    for rx, arch in _ARCH_RULES:
        if rx.search(name):
            return arch
    return None


@st.cache_data(ttl=86400)
def load_nvidia_dc_gpus() -> pd.DataFrame:
    """Load NVIDIA data-centre GPUs with normalised units and arch family.

    Returns a DataFrame sorted by release date with columns:
    name, release_date, arch, tflops_tensor_fp16, tflops_fp8, hbm_gb,
    mem_bw_gb_s, tdp_w, price_usd, die_size_mm2, transistors_m, datasheet_url.
    """
    if not ML_HARDWARE_CSV.exists():
        return pd.DataFrame()

    df = pd.read_csv(ML_HARDWARE_CSV)
    df = df[df["Manufacturer"].str.upper() == "NVIDIA"]
    df = df[df["Type"] == "GPU"].copy()
    df["arch"] = df["Hardware name"].map(_classify_arch)
    df = df[df["arch"].notna()].copy()

    # Normalise units
    df["release_date"] = pd.to_datetime(df["Release date"], errors="coerce")
    df["tflops_tensor_fp16"] = pd.to_numeric(df["Tensor-FP16/BF16 performance (FLOP/s)"], errors="coerce") / 1e12
    df["tflops_fp8"] = pd.to_numeric(df["FP8 performance (FLOP/s)"], errors="coerce") / 1e12
    df["hbm_gb"] = pd.to_numeric(df["Memory (bytes)"], errors="coerce") / 1e9
    df["mem_bw_gb_s"] = pd.to_numeric(df["Memory bandwidth (byte/s)"], errors="coerce") / 1e9
    df["tdp_w"] = pd.to_numeric(df["TDP (W)"], errors="coerce")
    df["price_usd"] = pd.to_numeric(df["Release price (USD)"], errors="coerce")
    df["die_size_mm2"] = pd.to_numeric(df["Die Size (mm^2)"], errors="coerce")
    df["transistors_m"] = pd.to_numeric(df["Transistors (millions)"], errors="coerce")

    out = df[[
        "Hardware name",
        "release_date",
        "arch",
        "tflops_tensor_fp16",
        "tflops_fp8",
        "hbm_gb",
        "mem_bw_gb_s",
        "tdp_w",
        "price_usd",
        "die_size_mm2",
        "transistors_m",
        "Link to datasheet",
    ]].rename(columns={"Hardware name": "name", "Link to datasheet": "datasheet_url"})

    out = out.dropna(subset=["release_date", "tflops_tensor_fp16"])
    return out.sort_values("release_date").reset_index(drop=True)


def flagship_per_generation(df: pd.DataFrame) -> pd.DataFrame:
    """Return the highest-TFLOPS SKU per architecture family — the 'flagship line'.

    Used for clean per-generation trends (perf/watt, perf/dollar).
    """
    if df.empty:
        return df
    flagships = df.sort_values("tflops_tensor_fp16", ascending=False).drop_duplicates("arch")
    return flagships.sort_values("release_date").reset_index(drop=True)
