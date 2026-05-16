"""DC operator risk signals for a hidden review page.

This module deliberately avoids scoring weak AI-revenue, circular-finance, and
GPU spot-price signals as primary data-centre operator risks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


DATA_DIR = Path(__file__).parent.parent.parent / "data" / "reference"
AU_DC_DIR = Path(__file__).parent.parent.parent / "data" / "au_dc" / "reference"

STATUS_ORDER = {"green": 0, "gray": 0, "amber": 1, "red": 2}
STATUS_LABELS = {
    "green": "Supported",
    "amber": "Watch",
    "red": "Warning",
    "gray": "Insufficient data",
}
STATUS_COLORS = {
    "green": "#22c55e",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "gray": "#6b7280",
}


@dataclass
class RiskSignal:
    name: str
    status: str
    value: str
    detail: str
    why_it_matters: str
    watch_for: str
    evidence: list[str]
    table: pd.DataFrame | None = None

    @property
    def score(self) -> int:
        return STATUS_ORDER.get(self.status, 0)


def _empty(name: str, why: str, watch_for: str) -> RiskSignal:
    return RiskSignal(
        name=name,
        status="gray",
        value="No score",
        detail="Required source data is unavailable or too thin to score.",
        why_it_matters=why,
        watch_for=watch_for,
        evidence=[],
    )


def _read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        return pd.DataFrame()


def capex_commitment_signal(data_dir: Path = DATA_DIR) -> RiskSignal:
    """Score unexpected capex cuts/pushouts, not natural maturity of build-out."""
    path = data_dir / "capex_guidance_history.csv"
    df = _read_csv(path, parse_dates=["announced_date"])
    if df.empty:
        return _empty(
            "Hyperscaler commitment",
            "DC operators depend on hyperscalers continuing to lease and fund committed capacity.",
            "Unexpected capex cuts, cancellations, pushouts, or language shifting from supply-constrained to demand-constrained.",
        )

    df = df.copy()
    df["notes"] = df["notes"].fillna("")
    df["is_actual"] = df["notes"].str.contains("actual full-year", case=False, na=False)
    guidance = df[~df["is_actual"]].sort_values(["company", "fiscal_year", "announced_date"]).copy()
    guidance["prev_guidance"] = guidance.groupby(["company", "fiscal_year"])["guidance_usd_b"].shift(1)
    guidance["revision_pct"] = (guidance["guidance_usd_b"] / guidance["prev_guidance"] - 1) * 100

    latest_date = guidance["announced_date"].max()
    recent_cutoff = latest_date - pd.Timedelta(days=365)
    recent = guidance[guidance["announced_date"] >= recent_cutoff].copy()
    cuts = recent[recent["revision_pct"] <= -5].copy()
    big_cuts = recent[recent["revision_pct"] <= -15].copy()
    pushout_words = r"delay|delayed|push|pushed|slip|slipped|cancel|cancelled|canceled"
    pushouts = recent[recent["notes"].str.contains(pushout_words, case=False, regex=True, na=False)].copy()

    if len(big_cuts) >= 2 or (len(big_cuts) >= 1 and len(pushouts) >= 2):
        status = "red"
    elif len(cuts) >= 1 or len(pushouts) >= 1:
        status = "amber"
    else:
        status = "green"

    latest_by_company = (
        guidance.sort_values("announced_date")
        .groupby("company")
        .tail(1)
        .sort_values("company")
    )
    if cuts.empty and pushouts.empty:
        value = "No recent cuts"
        detail = "Latest tracked capex guidance is still rising or being reaffirmed. That supports near-term DC demand, but a later plateau is not automatically bearish."
    else:
        value = f"{len(cuts)} cut(s), {len(pushouts)} pushout flag(s)"
        detail = "Recent guidance contains cut or delay language. Treat this as execution-risk evidence, not proof of demand failure."

    evidence = []
    for _, row in pd.concat([big_cuts, pushouts]).drop_duplicates().tail(4).iterrows():
        rev = row.get("revision_pct")
        rev_txt = f"{rev:+.0f}%" if pd.notna(rev) else "n/a"
        evidence.append(
            f"{row['company']} {row['fiscal_year']}: {rev_txt} revision on {row['announced_date'].date()} - {row['notes']}"
        )
    if not evidence:
        for _, row in latest_by_company.tail(4).iterrows():
            rev = row.get("revision_pct")
            rev_txt = f"{rev:+.0f}%" if pd.notna(rev) else "initial"
            evidence.append(
                f"{row['company']} {row['fiscal_year']}: {row['guidance_usd_b']:.0f}B, {rev_txt}"
            )

    table_cols = [
        "company", "fiscal_year", "guidance_usd_b", "prev_guidance",
        "revision_pct", "announced_date", "source", "notes",
    ]
    table = latest_by_company[[c for c in table_cols if c in latest_by_company.columns]].copy()
    if "announced_date" in table:
        table["announced_date"] = table["announced_date"].dt.strftime("%Y-%m-%d")

    return RiskSignal(
        name="Hyperscaler commitment",
        status=status,
        value=value,
        detail=detail,
        why_it_matters="Unexpected commitment deterioration hits DC operators through leasing demand, delivery schedules, preleasing confidence, and financing appetite.",
        watch_for="Cuts or pushouts paired with weak backlog, falling utilization, or explicit demand uncertainty. A mature-build plateau alone should not be scored as bearish.",
        evidence=evidence,
        table=table,
    )


def power_deliverability_signal(data_dir: Path = DATA_DIR) -> RiskSignal:
    path = data_dir / "dc_queue_metrics.csv"
    df = _read_csv(path)
    if df.empty:
        return _empty(
            "Power deliverability",
            "Power and interconnection are binding constraints for DC development timelines.",
            "Queue wait times, completion rates, large-load queues, PPA pricing, and contracted firm power coverage.",
        )

    df = df.copy()
    us = df[df["region"] == "United States"]
    wait = us[us["metric"] == "Avg Wait Time"].sort_values("year").tail(1)
    completion = us[us["metric"] == "Completion Rate"].sort_values("year").tail(1)
    queue = us[us["metric"] == "Queue Depth"].sort_values("year").tail(1)
    ercot = df[(df["region"] == "ERCOT") & (df["metric"] == "Large Load Queue")].sort_values("year")

    wait_v = float(wait["value"].iloc[0]) if not wait.empty else None
    comp_v = float(completion["value"].iloc[0]) if not completion.empty else None
    queue_v = float(queue["value"].iloc[0]) if not queue.empty else None
    ercot_latest = float(ercot["value"].iloc[-1]) if not ercot.empty else None
    ercot_prev = float(ercot["value"].iloc[-2]) if len(ercot) >= 2 else None
    ercot_growth = (ercot_latest / ercot_prev - 1) * 100 if ercot_latest and ercot_prev else None

    red_flags = 0
    amber_flags = 0
    if wait_v is not None:
        red_flags += int(wait_v >= 6)
        amber_flags += int(4 <= wait_v < 6)
    if comp_v is not None:
        red_flags += int(comp_v <= 15)
        amber_flags += int(15 < comp_v <= 25)
    if ercot_latest is not None:
        red_flags += int(ercot_latest >= 150)
        amber_flags += int(75 <= ercot_latest < 150)

    status = "red" if red_flags >= 2 else ("amber" if red_flags or amber_flags else "green")
    value_bits = []
    if wait_v is not None:
        value_bits.append(f"{wait_v:.1f}yr wait")
    if comp_v is not None:
        value_bits.append(f"{comp_v:.0f}% completion")
    value = " / ".join(value_bits) or "Tracked"

    detail = "Interconnection friction remains a direct schedule and development-risk signal for DC operators."
    if queue_v is not None:
        detail += f" Latest US queue depth is {queue_v:,.0f} GW."
    if ercot_growth is not None:
        detail += f" ERCOT large-load queue is {ercot_latest:,.0f} GW, {ercot_growth:+.0f}% vs prior point."

    evidence = []
    for label, frame in [("US wait", wait), ("US completion", completion), ("US queue", queue)]:
        if not frame.empty:
            row = frame.iloc[0]
            evidence.append(f"{label}: {row['value']:,.0f} {row['unit']} in {int(row['year'])} - {row['source']}")
    if ercot_latest is not None:
        evidence.append(f"ERCOT large-load queue: {ercot_latest:,.0f} GW")

    return RiskSignal(
        name="Power deliverability",
        status=status,
        value=value,
        detail=detail,
        why_it_matters="Even strong demand can become risky if projects cannot secure interconnection, firm power, or acceptable power pricing.",
        watch_for="Rising queue times, falling completion rates, power procurement gaps, regional moratoriums, and load forecasts outrunning firm supply additions.",
        evidence=evidence,
        table=df.tail(20),
    )


def contracted_demand_signal(au_dc_dir: Path = AU_DC_DIR) -> RiskSignal:
    """Use disclosed contracted MW/backlog where available, without estimating AI revenue."""
    path = au_dc_dir / "operator_aggregate_guidance.csv"
    df = _read_csv(path, parse_dates=["announcement_date", "last_verified_at"])
    if df.empty:
        return _empty(
            "Contracted demand quality",
            "Signed capacity and forward order books are cleaner DC demand signals than AI revenue estimates.",
            "Contracted utilisation, forward order books, churn, cancellations, and customer concentration.",
        )

    df = df.copy()
    for col in [
        "contracted_capacity_mw", "forward_order_book_mw", "new_contract_mw",
        "named_project_mw_in_db", "total_capacity_mw",
    ]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    demand_rows = df[
        df[["contracted_capacity_mw", "forward_order_book_mw", "new_contract_mw"]]
        .fillna(0)
        .sum(axis=1) > 0
    ].copy()
    if demand_rows.empty:
        return _empty(
            "Contracted demand quality",
            "Signed capacity and forward order books are cleaner DC demand signals than AI revenue estimates.",
            "Contracted utilisation, forward order books, churn, cancellations, and customer concentration.",
        )

    contracted_mw = float(demand_rows["contracted_capacity_mw"].fillna(0).sum())
    forward_mw = float(demand_rows["forward_order_book_mw"].fillna(0).sum())
    new_mw = float(demand_rows["new_contract_mw"].fillna(0).sum())
    named_mw = float(demand_rows["named_project_mw_in_db"].fillna(0).sum())
    coverage = contracted_mw / named_mw * 100 if named_mw else None

    if contracted_mw <= 0:
        status = "gray"
    elif coverage is not None and coverage < 25:
        status = "amber"
    else:
        status = "green"

    evidence = []
    for _, row in demand_rows.sort_values("announcement_date", ascending=False).head(5).iterrows():
        parts = []
        if pd.notna(row.get("contracted_capacity_mw")):
            parts.append(f"{row['contracted_capacity_mw']:.0f}MW contracted")
        if pd.notna(row.get("forward_order_book_mw")):
            parts.append(f"{row['forward_order_book_mw']:.0f}MW forward order book")
        if pd.notna(row.get("new_contract_mw")):
            parts.append(f"{row['new_contract_mw']:.0f}MW new contract")
        evidence.append(
            f"{row['operator']}: {', '.join(parts)} - {row.get('evidence_summary', '')}"
        )

    table_cols = [
        "operator", "announcement_date", "geography", "contracted_capacity_mw",
        "forward_order_book_mw", "new_contract_mw", "named_project_mw_in_db",
        "source", "treatment_notes",
    ]
    table = demand_rows[[c for c in table_cols if c in demand_rows.columns]].copy()
    if "announcement_date" in table:
        table["announcement_date"] = table["announcement_date"].dt.strftime("%Y-%m-%d")

    detail = (
        f"Tracked AU/ANZ operator disclosures show {contracted_mw:,.0f}MW contracted"
        f" and {forward_mw:,.0f}MW in forward order book."
    )
    if coverage is not None:
        detail += f" Contracted MW equals {coverage:.0f}% of named project MW in the database."

    return RiskSignal(
        name="Contracted demand quality",
        status=status,
        value=f"{contracted_mw:,.0f}MW contracted",
        detail=detail,
        why_it_matters="Signed utilisation and order books are closer to DC operator economics than broad AI revenue estimates.",
        watch_for="Cancellations, delays to signed-but-not-commenced capacity, tenant concentration, or contracted MW no longer converting into operating MW.",
        evidence=evidence,
        table=table,
    )


def power_procurement_coverage_signal(data_dir: Path = DATA_DIR) -> RiskSignal:
    """Portfolio-level power coverage from existing sourcing disclosures."""
    path = data_dir / "dc_power_sourcing.csv"
    df = _read_csv(path, parse_dates=["announced_date"])
    if df.empty:
        return _empty(
            "Portfolio power coverage",
            "Power procurement is a gating item for new DC capacity.",
            "Campus-level firm power coverage, PPA pricing, delivery dates, and whether contracted power matches announced IT load.",
        )

    df = df.copy()
    df["capacity_gw"] = pd.to_numeric(df.get("capacity_gw"), errors="coerce")
    df_known = df[df["capacity_gw"].notna()].copy()
    if df_known.empty:
        return _empty(
            "Portfolio power coverage",
            "Power procurement is a gating item for new DC capacity.",
            "Campus-level firm power coverage, PPA pricing, delivery dates, and whether contracted power matches announced IT load.",
        )

    firm_statuses = {"Contracted", "PPA", "Actual"}
    df_known["is_firm_or_ppa"] = df_known["status"].isin(firm_statuses)
    firm_gw = float(df_known.loc[df_known["is_firm_or_ppa"], "capacity_gw"].sum())
    total_gw = float(df_known["capacity_gw"].sum())
    firm_share = firm_gw / total_gw * 100 if total_gw else 0

    if firm_share >= 75:
        status = "green"
    elif firm_share >= 50:
        status = "amber"
    else:
        status = "red"

    by_company = (
        df_known.groupby(["company", "is_firm_or_ppa"])["capacity_gw"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    if True not in by_company:
        by_company[True] = 0.0
    if False not in by_company:
        by_company[False] = 0.0
    by_company = by_company.rename(columns={True: "firm_or_ppa_gw", False: "pipeline_or_soft_gw"})
    by_company["total_gw"] = by_company["firm_or_ppa_gw"] + by_company["pipeline_or_soft_gw"]
    by_company["firm_share"] = by_company["firm_or_ppa_gw"] / by_company["total_gw"] * 100
    by_company = by_company.sort_values("total_gw", ascending=False)

    evidence = [
        f"{row['company']}: {row['firm_or_ppa_gw']:.1f}GW firm/PPA of {row['total_gw']:.1f}GW tracked ({row['firm_share']:.0f}%)"
        for _, row in by_company.head(5).iterrows()
    ]

    table_cols = ["company", "source_type", "capacity_gw", "status", "counterparty", "announced_date", "details", "reference"]
    table = df_known[[c for c in table_cols if c in df_known.columns]].sort_values(
        ["company", "capacity_gw"], ascending=[True, False]
    )
    if "announced_date" in table:
        table["announced_date"] = table["announced_date"].dt.strftime("%Y-%m-%d")

    return RiskSignal(
        name="Portfolio power coverage",
        status=status,
        value=f"{firm_share:.0f}% firm/PPA",
        detail=(
            f"Existing sourcing disclosures show {firm_gw:.1f}GW firm/PPA capacity out of "
            f"{total_gw:.1f}GW with known MW. This is portfolio-level, not campus-level."
        ),
        why_it_matters="Operators are exposed when tenant demand is real but power delivery is soft, delayed, or not matched to the campus.",
        watch_for="Soft MOUs replacing firm PPAs, power delivery dates slipping beyond lease commitments, and campuses with announced MW but no firm power evidence.",
        evidence=evidence,
        table=table,
    )


def project_execution_signal(au_dc_dir: Path = AU_DC_DIR) -> RiskSignal:
    """AU project database execution risk: proposed concentration and missing power fields."""
    path = au_dc_dir / "projects_seed.csv"
    df = _read_csv(path)
    if df.empty:
        return _empty(
            "Project execution and permitting",
            "Large development pipelines only matter if capacity can progress through site, power, and delivery milestones.",
            "Status migration from proposed to under construction, power-secured flags, startup dates, and remediation status.",
        )

    df = df.copy()
    df["facility_mw"] = pd.to_numeric(df.get("facility_mw"), errors="coerce").fillna(0)
    if "include_in_project_totals" in df:
        include = df["include_in_project_totals"].astype(str).str.lower().isin(["true", "1", "yes"])
        df = df[include].copy()

    total_mw = float(df["facility_mw"].sum())
    pipeline = df[~df["status"].astype(str).str.lower().isin(["operating"])].copy()
    pipeline_mw = float(pipeline["facility_mw"].sum())
    proposed = df[df["status"].astype(str).str.lower().str.contains("proposed", na=False)].copy()
    proposed_mw = float(proposed["facility_mw"].sum())
    proposed_share = proposed_mw / total_mw * 100 if total_mw else 0
    missing_power = 0
    if "power_secured" in pipeline:
        missing_power = int(pipeline["power_secured"].isna().sum() + (pipeline["power_secured"].astype(str).str.strip() == "").sum())
    missing_power_share = missing_power / len(pipeline) * 100 if len(pipeline) else 0

    if proposed_share >= 60 or missing_power_share >= 75:
        status = "amber"
    else:
        status = "green"

    by_status = (
        df.groupby("status", dropna=False)["facility_mw"]
        .sum()
        .reset_index()
        .sort_values("facility_mw", ascending=False)
    )

    evidence = [
        f"Total included AU project database: {total_mw:,.0f}MW",
        f"Pipeline / non-operating capacity: {pipeline_mw:,.0f}MW",
        f"Proposed capacity: {proposed_mw:,.0f}MW ({proposed_share:.0f}% of included MW)",
    ]
    if len(pipeline):
        evidence.append(f"Pipeline rows without explicit power_secured field: {missing_power} of {len(pipeline)}")

    table_cols = [
        "project_name", "operator", "state", "status", "facility_mw", "startup_year",
        "full_capacity_year", "power_strategy", "power_secured", "remediation_status",
        "capacity_basis", "source_url",
    ]
    table = df[[c for c in table_cols if c in df.columns]].sort_values("facility_mw", ascending=False).head(50)

    return RiskSignal(
        name="Project execution and permitting",
        status=status,
        value=f"{proposed_share:.0f}% proposed MW",
        detail=(
            "Uses the AU project database to separate announced capacity from operating or more advanced capacity. "
            "This is an execution-readiness signal, not a demand signal."
        ),
        why_it_matters="DC operators can have strong demand but still miss economics if projects slip through permitting, power, or construction gates.",
        watch_for="Large proposed MW not converting into under-construction/operating MW, blank power evidence, remediation issues, and startup-year slippage.",
        evidence=evidence,
        table=table,
    )


def capital_markets_signal(data_dir: Path = DATA_DIR) -> RiskSignal:
    """Use current news catalog as a proxy until direct credit-spread feeds exist."""
    path = data_dir / "news_catalog.csv"
    df = _read_csv(path, parse_dates=["published", "first_seen_at", "last_seen_at"])
    if df.empty:
        return _empty(
            "Capital markets",
            "DC operators and neocloud tenants depend on deep debt markets and refinancing access.",
            "Bond spreads, failed deals, rating actions, maturity walls, covenant pressure, and emergency equity raises.",
        )

    terms = r"bond|loan|debt|refinanc|credit|rating|spread|pricing disappoint|ices|covenant|liquidity"
    text = (
        df.get("title", pd.Series(dtype=str)).fillna("")
        + " "
        + df.get("summary", pd.Series(dtype=str)).fillna("")
    )
    hits = df[text.str.contains(terms, case=False, regex=True, na=False)].copy()
    hits = hits.sort_values("published", ascending=False)
    high_hits = hits[hits.get("last_tier", "").isin(["HIGH", "MEDIUM"])] if "last_tier" in hits else hits

    if len(high_hits) >= 5:
        status = "red"
    elif len(high_hits) >= 1:
        status = "amber"
    else:
        status = "green"

    value = f"{len(high_hits)} credit event(s)"
    detail = "This is a proxy, not a spread model. It should be replaced or supplemented with actual bond/yield data when available."
    evidence = [
        f"{row.get('published').date() if pd.notna(row.get('published')) else 'n/a'}: {row.get('title', '')}"
        for _, row in high_hits.head(5).iterrows()
    ]
    if not evidence:
        evidence = ["No material credit-market headlines in the catalog."]

    table_cols = ["published", "last_tier", "last_bucket", "title", "source", "url"]
    table = high_hits[[c for c in table_cols if c in high_hits.columns]].head(20).copy()
    if "published" in table:
        table["published"] = table["published"].dt.strftime("%Y-%m-%d")

    return RiskSignal(
        name="Capital markets",
        status=status,
        value=value,
        detail=detail,
        why_it_matters="Credit stress can hit DC operators before operating metrics crack, especially where growth depends on debt-funded campuses or tenant financing.",
        watch_for="Wider spreads, undersubscribed deals, lender haircuts on GPU collateral, rating downgrades, and refinancing windows closing.",
        evidence=evidence,
        table=table,
    )


def buildout_financing_signal(data_dir: Path = DATA_DIR) -> RiskSignal:
    """Track debt/private-credit reliance without mechanically scoring circularity."""
    path = data_dir / "funding_deals.csv"
    df = _read_csv(path, parse_dates=["date"])
    if df.empty:
        return _empty(
            "Buildout financing exposure",
            "Large DC and neocloud buildouts can become fragile if they depend on debt markets staying open.",
            "Debt-heavy financings, private-credit concentration, refinancing risk, and failed or repriced deals.",
        )

    df = df.copy()
    df["amount_bn"] = pd.to_numeric(df.get("amount_bn"), errors="coerce").fillna(0)
    df["type"] = df["type"].fillna("").str.lower()
    financing = df[df["type"].isin(["debt", "hybrid"])].copy()
    debt_rows = df[df["type"] == "debt"].copy()
    if financing.empty:
        return RiskSignal(
            name="Buildout financing exposure",
            status="green",
            value="No debt/hybrid deals",
            detail="Tracked funding file contains no debt or hybrid buildout financing rows.",
            why_it_matters="Debt-funded growth is more sensitive to credit conditions than balance-sheet or pure-equity funded growth.",
            watch_for="Large maturities, refinancing at higher cost, lender haircuts on GPU collateral, and private-credit appetite fading.",
            evidence=["No debt/hybrid rows in funding_deals.csv."],
            table=df,
        )

    total_financing = float(financing["amount_bn"].sum())
    debt_only = float(debt_rows["amount_bn"].sum())
    hybrid = float(financing[financing["type"] == "hybrid"]["amount_bn"].sum())
    all_deployed = df[df["type"] != "balance_sheet"]["amount_bn"].sum()
    debt_share = debt_only / all_deployed * 100 if all_deployed else 0

    if debt_only >= 150 or debt_share >= 50:
        status = "red"
    elif debt_only >= 50 or debt_share >= 25:
        status = "amber"
    else:
        status = "green"

    evidence = []
    for _, row in financing.sort_values("amount_bn", ascending=False).head(5).iterrows():
        evidence.append(
            f"{row['entity']}: ${row['amount_bn']:.1f}B {row['type']} - {row.get('notes', '')}"
        )

    table_cols = ["date", "entity", "amount_bn", "type", "counterparty", "source", "notes"]
    table = financing[[c for c in table_cols if c in financing.columns]].sort_values("amount_bn", ascending=False)
    if "date" in table:
        table["date"] = table["date"].dt.strftime("%Y-%m-%d")

    return RiskSignal(
        name="Buildout financing exposure",
        status=status,
        value=f"${debt_only:.0f}B debt",
        detail=(
            f"Tracked funding rows include ${debt_only:.0f}B debt and ${hybrid:.0f}B hybrid/JV financing. "
            "Only debt rows drive the score; hybrid rows are shown as context because commitments and JV structures are not equivalent to debt."
        ),
        why_it_matters="Debt and private-credit funded AI/DC growth is more exposed to credit-market closure, collateral haircuts, and refinancing shocks.",
        watch_for="Debt deals repricing wider, failed syndications, equity cures, collateral disputes, and tenant contracts used to support increasingly leveraged campuses.",
        evidence=evidence,
        table=table,
    )


def market_breadth_signal(stocks: list[dict] | None = None) -> RiskSignal:
    if not stocks:
        return _empty(
            "Market breadth",
            "Narrow AI/DC leadership is a useful crowding and risk-appetite signal.",
            "AI infrastructure and DC operators underperforming while a few mega-cap leaders hold up.",
        )

    rows = []
    for s in stocks:
        returns = s.get("returns", {}) or {}
        rows.append({
            "symbol": s.get("symbol"),
            "name": s.get("name"),
            "group": s.get("group"),
            "1M": returns.get("1M"),
            "3M": returns.get("3M"),
            "6M": returns.get("6M"),
            "1Y": returns.get("1Y"),
            "pct_from_high": s.get("pct_from_high"),
        })
    df = pd.DataFrame(rows)
    if df.empty or "group" not in df:
        return _empty(
            "Market breadth",
            "Narrow AI/DC leadership is a useful crowding and risk-appetite signal.",
            "AI infrastructure and DC operators underperforming while a few mega-cap leaders hold up.",
        )

    group_perf = df.groupby("group", dropna=False)[["1M", "3M", "6M", "1Y"]].mean(numeric_only=True)
    dc_6m = group_perf.loc["DC Operators", "6M"] if "DC Operators" in group_perf.index and "6M" in group_perf else None
    mag7_6m = group_perf.loc["Mag 7", "6M"] if "Mag 7" in group_perf.index and "6M" in group_perf else None
    dc_drawdowns = df[(df["group"] == "DC Operators") & (df["pct_from_high"].notna())]["pct_from_high"]
    deep_drawdowns = int((dc_drawdowns <= -20).sum()) if not dc_drawdowns.empty else 0
    underperf = (dc_6m - mag7_6m) if dc_6m is not None and mag7_6m is not None else None

    if deep_drawdowns >= 2 or (underperf is not None and underperf <= -25):
        status = "red"
    elif deep_drawdowns >= 1 or (underperf is not None and underperf <= -10):
        status = "amber"
    else:
        status = "green"

    value = "Tracked"
    if underperf is not None:
        value = f"{underperf:+.0f}ppt 6M vs Mag 7"
    detail = "Looks for whether DC operators are cracking while headline AI leaders remain supported."
    evidence = []
    if dc_6m is not None:
        evidence.append(f"DC operators average 6M return: {dc_6m:+.0f}%")
    if mag7_6m is not None:
        evidence.append(f"Mag 7 average 6M return: {mag7_6m:+.0f}%")
    if deep_drawdowns:
        evidence.append(f"{deep_drawdowns} DC operator(s) are more than 20% below 52-week high.")

    return RiskSignal(
        name="Market breadth",
        status=status,
        value=value,
        detail=detail,
        why_it_matters="A narrowing trade often precedes broader de-risking. For DC operators, relative weakness can flag financing or tenant-quality doubts.",
        watch_for="DC operators and AI-infra secondaries rolling over while Mag 7 concentration rises.",
        evidence=evidence or ["Equity data loaded but no major breadth warning triggered."],
        table=df,
    )


def model_economics_signal(data_dir: Path = DATA_DIR) -> RiskSignal:
    path = data_dir / "token_prices_history.csv"
    df = _read_csv(path, parse_dates=["date"])
    if df.empty:
        return _empty(
            "Model economics",
            "Tenant willingness to pay for premium capacity depends on durable model-unit economics.",
            "Capability saturation, open-model catch-up, and faster price compression than usage growth.",
        )

    df = df.copy()
    df["blended_price"] = (3 * df["input_usd_per_mtok"] + df["output_usd_per_mtok"]) / 4
    latest = df.sort_values("date").tail(1)
    first = df.sort_values("date").head(1)
    if latest.empty or first.empty:
        return _empty(
            "Model economics",
            "Tenant willingness to pay for premium capacity depends on durable model-unit economics.",
            "Capability saturation, open-model catch-up, and faster price compression than usage growth.",
        )

    first_price = float(first["blended_price"].iloc[0])
    latest_price = float(latest["blended_price"].iloc[0])
    price_drop = (1 - latest_price / first_price) * 100 if first_price else None

    status = "green"
    if price_drop is not None and price_drop >= 90:
        status = "amber"

    return RiskSignal(
        name="Model economics",
        status=status,
        value=f"{price_drop:.0f}% cheaper" if price_drop is not None else "Tracked",
        detail="Falling inference prices are not automatically bad, but they increase the burden on usage growth and tenant margin expansion.",
        why_it_matters="If model capability saturates while prices compress, weaker tenants may reduce appetite for premium AI capacity.",
        watch_for="Price compression combined with slowing usage, benchmark convergence, open-model catch-up, or weaker cloud AI commentary.",
        evidence=[
            f"Oldest tracked blended API price: ${first_price:.2f}/M tokens",
            f"Latest tracked blended API price: ${latest_price:.2f}/M tokens",
        ],
        table=df.sort_values("date", ascending=False).head(20),
    )


def unscored_context(data_dir: Path = DATA_DIR) -> list[dict[str, str]]:
    return [
        {
            "Signal": "AI revenue / ARR",
            "Treatment": "Context only",
            "Reason": "Disclosure is too incomplete and inconsistent to support a headline score.",
            "Useful when": "A company gives explicit cloud AI revenue, ARR, backlog, or usage growth tied to capacity demand.",
        },
        {
            "Signal": "Circular financing",
            "Treatment": "Qualitative watchlist",
            "Reason": "Can be risky, but can also be rational supply-chain financing or demand lock-in by well-capitalised firms.",
            "Useful when": "The financing is large, off-market, necessary for customer solvency, or paired with weak third-party demand.",
        },
        {
            "Signal": "GPU spot prices",
            "Treatment": "Neocloud / GPU-lessor context",
            "Reason": "Older GPUs naturally depreciate and DC operators usually do not own the GPUs.",
            "Useful when": "GPU price declines create tenant credit stress, collateral pressure, or lease renegotiation risk.",
        },
    ]


def overall_status(signals: list[RiskSignal]) -> dict[str, str]:
    reds = sum(1 for s in signals if s.status == "red")
    ambers = sum(1 for s in signals if s.status == "amber")
    grays = sum(1 for s in signals if s.status == "gray")

    if reds >= 2:
        return {
            "status": "red",
            "label": "Demand/capital stress emerging",
            "detail": f"{reds} warning, {ambers} watch, {grays} insufficient-data signal(s)",
        }
    if reds == 1 or ambers >= 2:
        return {
            "status": "amber",
            "label": "Execution risk rising",
            "detail": f"{reds} warning, {ambers} watch, {grays} insufficient-data signal(s)",
        }
    return {
        "status": "green",
        "label": "Expansion supported",
        "detail": f"{reds} warning, {ambers} watch, {grays} insufficient-data signal(s)",
    }
