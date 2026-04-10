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
