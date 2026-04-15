# AI & DC Research Dashboard

Streamlit multi-page app: `streamlit run app/Home.py`

## Project Structure

- `app/` — Streamlit pages (views grouped by section: fundamentals, supply_chain, news, system)
- `data/reference/` — hand-curated CSV seed data (power forecasts, CAPEX, sourcing, queue metrics, etc.)
- `data/` — SQLite DB (`ai_research.db`) + other generated data
- `etl/` — ETL pipelines (universe loading, financial fetches)
- `scripts/` — maintenance and audit scripts
- `models/` — data models
- `monitors/` — monitoring/alerting

## Data Provenance Rules (CRITICAL)

**Every data point in `data/reference/*.csv` must be an actual reported figure from a named, verifiable source.**

### What is NOT allowed
- Interpolated or estimated values presented as actual data
- "Synthesis" sources that don't correspond to a real publication
- Round-number placeholders (e.g. filling gaps with interpolated values)
- Forward projections attributed to sources that don't publish them
- Any value where you are not confident it matches a specific published figure

### What IS required
- Every CSV row must have a non-empty `source` or `reference` column
- Source must name the actual publication (e.g. "LBNL Queued Up 2024 Edition", "IEA Electricity 2025", "EIA Today in Energy")
- If a data point is an estimate, the source column must say so explicitly (e.g. "Industry estimates") — never present estimates as facts
- `published_date` should reflect when the source was published, not when the data was entered
- If data doesn't exist for a year/period, leave the gap — do not fill it

### Audit script
Run `python scripts/audit_reference_data.py` before committing changes to reference CSVs. It checks:
- Source attribution on every row
- Column count consistency (catches shifted fields from bad CSV edits)
- Flags suspect source terms ("estimate", "synthesis", "projected")
- Flags perfectly uniform numeric sequences (sign of interpolation)

### When adding new reference data
1. **Hit an official API first** — always prefer programmatic, authoritative sources over web searches
2. If no API exists, verify figures against the named published source
3. Include the publication name and date in the source column
4. Run the audit script
5. If a figure can't be verified, don't include it

### Available APIs for verification

| Domain | API / Tool | Covers |
|--------|-----------|--------|
| US electricity (capacity, generation, consumption) | **EIA Open Data API** (`api.eia.gov`) | Grid capacity, planned additions, generation mix — most of `dc_power_supply.csv` |
| Company financials (CAPEX, revenue, income) | **yfinance** (already in project) | Quarterly CAPEX actuals, market caps |
| Company financials (detailed) | **OpenBB MCP** (`mcp__openbb__equity_fundamental_*`) | Income, balance sheet, cash flow, metrics |
| SEC filings | **SEC EDGAR API** (`efts.sec.gov`) | 10-Q/10-K source of truth for CAPEX |
| TSMC revenue | **TSMC IR monthly reports** | `tsmc_monthly_revenue.csv` — structured PDF/HTML, no API |
| Interconnection queue | **LBNL Queued Up reports** (no API) | Published editions only — cite edition year |
| DC power demand forecasts | **IEA data explorer** (no public API) | Reports only — cite report name + year |
| Power sourcing deals | **Company press releases** (no API) | Announcements — cite press release + date |

Prefer API → structured report → press release → news article, in that order.

## Key Data Files

| File | Content | Key Sources |
|------|---------|-------------|
| `dc_power_forecasts.csv` | DC power demand projections | IEA, McKinsey, Goldman Sachs |
| `dc_power_supply.csv` | Grid capacity, DC consumption, planned additions | EIA, IEA |
| `dc_queue_metrics.csv` | Interconnection queue depth, wait times, completion | LBNL Queued Up reports |
| `dc_power_sourcing.csv` | Hyperscaler power deals (PPAs, nuclear, etc.) | Company announcements, press |
| `capex_quarterly_seed.csv` | Quarterly CAPEX actuals | SEC filings via stockanalysis |
| `capex_guidance.csv` | Current-year CAPEX guidance | Earnings calls |
| `capex_guidance_history.csv` | Guidance revision history | Earnings calls |
