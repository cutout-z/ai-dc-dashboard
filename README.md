# AI & DC Dashboard

A Streamlit dashboard for tracking the AI infrastructure and data centre investment thesis — covering frontier labs, hyperscaler capex, supply chain, financial statements, model performance, and curated news.

**Live demo:** [ai-dc-dashboard.streamlit.app](https://ai-dc-dashboard.streamlit.app)

---

## What's inside

| Section | Pages |
|---|---|
| **Fundamentals** | Model Performance · Equity Analysis · Financial Statements · Hyperscaler CAPEX · Other Signals |
| **Supply Chain** | AI Infra Value Chain · DC & AI Inputs · Prospecting |
| **News** | Unified AI/DC news feed (Frontier Labs, Hyperscaler CAPEX, Supply Chain, Model Releases, ANZ DC, China/Export Controls) |
| **System** | Source Health |

### Data sources

All data is fetched live or maintained in public reference CSVs — no proprietary data is included.

- **Market data / financials** — [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance)
- **Analyst consensus** — yfinance (Yahoo Finance analyst estimates)
- **News** — Google News RSS + curated DC/AI feeds (Data Center Dynamics, The Register)
- **Reference data** — hand-curated CSVs for CAPEX guidance, frontier lab valuations, model releases, GPU lease prices, DC power forecasts, TSMC monthly revenue
- **Supply chain universe** — curated stock mapping across AI infra segments (included in repo)

### Australian data-centre capacity treatment

The Australian Market pages separate public-source data into distinct capacity layers:

- **Included project capacity** — named project or campus rows with source-backed MW evidence; these feed default project totals and risked MW.
- **Quarantined project MW** — named rows retained for audit where MW evidence is weaker or not yet reconciled; excluded from default totals.
- **Unmatched aggregate guidance** — operator, platform, contract, order-book, or precinct disclosures that do not map cleanly to named project rows; shown as screening intelligence, not additive project capacity.
- **Physical site leads** — named public-source site leads with MW where available; excluded until promoted through the project evidence audit.

The dashboard's excluded-capacity overlay combines the latter three as a screening signal only. It should not be read as a standalone market-capacity estimate because components can use different capacity bases and may overlap until reconciled.

---

## Run locally

```bash
git clone https://github.com/cutout-z/ai-dc-dashboard.git
cd ai-dc-dashboard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/Home.py
```

Requires Python 3.10+.

---

## Deploy on Streamlit Community Cloud

1. Fork or clone this repo to your GitHub account
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select the repo, set **Main file path** to `app/Home.py`
4. Click **Deploy**

No secrets or environment variables are required — all data sources are public.

---

## Keeping data current

The Streamlit app is a reader of committed dashboard data. It does not call
the NAS lanes during page load.

The active production refresh process runs on the NAS runner (QNAP
`ai-wif-runner` container), scheduled by QNAP scheduled tasks and dispatched
by `nas-job ai-dc-*`:

1. Scheduled lanes run ETL, AU DC refreshes, source-health checks, and
   report-only research briefs (lane registry + cadence windows in
   `tools/nas-runner/configs/brain-ops.nas.toml`).
2. The dispatcher reuses this repo's `deploy/run-vps-*.sh` scripts as entry
   points, overriding `APP_DIR`/`PYTHON`/`REPORT_DIR` for the container
   layout. The `run-vps-*` names are retained for compatibility — they are
   NAS lanes now, not VPS services.
3. Refresh scripts rebuild compact dashboard-ready outputs under `data/`.
4. If tracked outputs change, the lane commits and pushes to GitHub.
5. Streamlit Community Cloud picks up the latest committed data on its
   normal redeploy/restart path.

Current NAS lanes (definitive cadence: `tools/nas-runner/configs/brain-ops.nas.toml`):

| Lane | Dashboard impact |
|---|---|
| Source health (`ai-dc-health`) | Runs source-health checks; writes Markdown/JSON operational reports. |
| Deterministic ETL (`ai-dc-etl`) | Refreshes financials, macro, consensus, earnings dates, capex staleness, news catalogue snapshots, and ZeroEval/LLM benchmark data; commits changed dashboard data. |
| Research brief (`ai-dc-research-brief`) | Stages a review prompt/report only; no CSV/DB writes. |
| AU DC data (`ai-dc-au-data`) | Refreshes AEMO generation/grid/project outputs, runs AU DC checks, prunes raw cache, and commits changed processed outputs. |

The earlier Hetzner VPS + systemd timers era is **historical** — see
`deploy/README.md` for the current NAS runner setup and what remains of the
old VPS instructions.

Operational details live in `deploy/`.

### Manual refreshes

The dashboard's reference data can still be refreshed manually when needed. The ETL scripts in `scripts/` and `etl/` handle this:

```bash
# Refresh financial data (CAPEX, revenue, income statements via yfinance)
python scripts/fetch_financials.py

# Refresh LLM benchmark data — writes the full-field model snapshot
# (data/reference/llm_leaderboard.json) and the separately-identified TrueSkill
# index snapshot (data/reference/llm_indexes.json), both schema-validated
python scripts/refresh_llm_leaderboard.py

# Snapshot the curated news feed into an append-only event catalogue
python scripts/catalog_news.py

# Refresh analyst consensus estimates
python etl/refresh_consensus.py

# Refresh macro data (GDP via FRED)
python etl/fetch_macro.py
```

Run these before pushing updates when doing a supervised local refresh.

### NAS automation

Production automation lives in `deploy/` and runs on the NAS runner. The
model is:

- deterministic ETL refreshes commit dashboard-ready data when outputs change;
- AU DC refreshes run as a separate lane and skip the full historical demand rebuild by default;
- source-health reports are written as Markdown/JSON under the lane's
  `REPORT_DIR` (container path — see `tools/nas-runner/configs/brain-ops.nas.toml`);
- LLM-backed research is report-only until reviewed and promoted manually.

The `run-vps-*.sh` filenames in `deploy/` are historical compatibility names —
the NAS dispatcher invokes them with its own environment overrides.

Raw AU DC AEMO/NEMOSIS cache is pruned with `scripts/prune_au_dc_raw_cache.py`; processed parquet/CSV outputs are the durable dashboard layer.

### Research pass pattern

For data the ETL scripts can't cover — DC pipeline announcements, new funding deals, nuclear PPAs — we use a **research pass** pattern: a structured web research session (manual or AI-assisted) that collects new datapoints and appends them to `data/reference/funding_deals.csv` and the research findings database.

The two targets for a research pass:

- **DC pipeline** — new construction announcements >100MW, nuclear/renewable PPAs, grid constraint news, Australia-specific DC developments
- **Funding deals** — new AI equity rounds, debt raises, data center financing; flag circular financing (investor is also a customer or supplier)

Findings are stored in the `research_findings` table in `data/db/ai_research.db` via `scripts/research_pass.py`:

```python
from scripts.research_pass import add_finding, log_run, init_research_tables

init_research_tables()
add_finding(
    category="dc_pipeline",
    metric_name="dc_capacity_mw",
    metric_value="500",
    company="NextDC",
    unit="MW",
    period="2025",
    source_url="https://...",
    notes="S7 Sydney campus launch",
    confidence="high",
)
```

The table is append-only — rows form a time series for tracking changes across research passes.

The live News page itself is a 30-minute RSS cache. To make news durable over time, run
`python scripts/catalog_news.py`; it writes material High/Medium feed items to
`data/reference/news_catalog.csv` — one row per article keyed by its normalised
source URL (S2-09), with first-seen, last-seen, source, tier, and score. The optional
`event_key` column groups distinct articles that carry the exact same headline
(syndicated coverage); it is never used to collapse rows, so two different stories
about the same company or two lifecycle updates on one IPO remain separate articles.
For historical catch-up, run `python scripts/catalog_news.py --backfill-days 60 --window-days 7`;
the News page reads the same catalog for the High/Medium history tables. Catalogs keyed
by the pre-2026-09 title-derived keys can be migrated with
`python scripts/migrate_news_catalog.py` (dry-run report first; `--write` persists).
Display tiers obey a common source-quality (trust) gate before any visible material
tier (S2-10): HIGH and MEDIUM both require a verified source (trust >= 0.70), so an
article from an unrecognised/aggregator outlet stays LOW no matter how large the
claimed magnitude. Stored HIGH rows from before the gate can be reclassified with
`python scripts/migrate_news_catalog_tiers.py` (dry-run report first; `--write`
persists) — rows are kept as historical evidence, only `last_tier` changes.

---

## Project structure

```
app/
  Home.py                        # Entry point + navigation
  lib/                           # Data fetching + processing
  views/                         # One file per page
data/
  db/                            # SQLite database (supply chain universe)
  processed/                     # Processed CSVs (supply chain mapping)
  reference/                     # Hand-curated reference data CSVs
scripts/                         # ETL scripts (rebuild DB from source data)
```

---

## License

MIT
