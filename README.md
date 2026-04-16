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

The dashboard's reference data needs periodic refreshing as new figures are published. The ETL scripts in `scripts/` and `etl/` handle this:

```bash
# Refresh financial data (CAPEX, revenue, income statements via yfinance)
python scripts/fetch_financials.py

# Refresh LLM benchmark + leaderboard data
python scripts/fetch_llm_benchmarks.py
python scripts/refresh_llm_leaderboard.py

# Refresh analyst consensus estimates
python etl/refresh_consensus.py

# Refresh macro data (GDP via FRED)
python etl/fetch_macro.py
```

Run these before pushing updates to keep the Streamlit Cloud deployment current.

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
