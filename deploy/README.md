# Hetzner VPS Automation

AI & DC uses the same frequency-driven model as the AEMO projects:

- The VPS runs deterministic ETL and data-quality checks.
- GitHub stores code plus compact dashboard-ready outputs.
- Research that needs LLM judgement is report-only until reviewed.
- Raw AU DC AEMO/NEMOSIS cache is bounded; processed parquet/CSV outputs are the durable dashboard layer.

The Streamlit app remains the front-end reader. It does not call systemd services live. The VPS refreshes data, commits changed tracked outputs, pushes to GitHub, and Streamlit renders the latest committed data on its normal redeploy/restart path.

## Active Hetzner Layout

The live Hetzner setup uses:

```text
/opt/ai-dc-dashboard                         git checkout + virtualenv
/etc/ai-dc-dashboard/*.env                   protected per-lane settings
/var/lib/ai-dc-dashboard/reports/source-health
/var/lib/ai-dc-dashboard/reports/research-briefs
```

The service user is `ai-dc`, with a repo-scoped deploy key named `ai-dc-vps-bot` that can pull and push `cutout-z/ai-dc-dashboard`.

## Lanes

| Lane | Timer | Cadence | Script | Purpose |
| --- | --- | --- | --- | --- |
| Source health | `ai-dc-health.timer` | Daily around 07:20 Perth | `run-vps-health.sh` | Write a Markdown/JSON source-health report without changing repo data. |
| Deterministic ETL | `ai-dc-etl.timer` | Mon/Wed/Fri around 07:40 Perth | `run-vps-etl.sh` | Refresh financials, macro, consensus, earnings dates, capex staleness, ZeroEval/LLM benchmark data when enabled, then commit changed dashboard data. |
| Research brief | `ai-dc-research-brief.timer` | Weekly Monday morning Perth | `run-vps-research-brief.sh` | Build a structured research prompt and optionally run an LLM command. Current production mode is report-only: no DB/CSV writes. |
| AU DC data | `ai-dc-au-data.timer` | Weekly Monday morning Perth | `run-vps-au-data.sh` | Refresh AEMO generation/grid/project outputs, run AU DC checks, prune raw cache, and commit changed processed outputs. Routine lane skips the full 2020+ demand rebuild. |

## Install

These commands install the unit files on a prepared VPS checkout:

```bash
sudo cp deploy/ai-dc-*.service /etc/systemd/system/
sudo cp deploy/ai-dc-*.timer /etc/systemd/system/
sudo mkdir -p /etc/ai-dc-dashboard
sudo cp deploy/env/*.env.example /etc/ai-dc-dashboard/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-dc-etl.timer
sudo systemctl enable --now ai-dc-au-data.timer
sudo systemctl enable --now ai-dc-health.timer
sudo systemctl enable --now ai-dc-research-brief.timer
```

Run once manually:

```bash
sudo systemctl start ai-dc-health.service
journalctl -u ai-dc-health.service -f
```

Useful status checks:

```bash
systemctl list-timers --all "ai-dc-*" --no-pager
sudo -u ai-dc git -C /opt/ai-dc-dashboard status --short
du -sh /opt/ai-dc-dashboard/data/au_dc/raw/aemo/nemosis_cache
```

## Secrets

Use environment files or systemd credentials on the VPS, not macOS Keychain.

- `FMP_API_KEY` enables FMP consensus and earnings-date refresh.
- `ZEROEVAL_API_KEY` enables the ZeroEval/LLM benchmark refresh when `RUN_ZEROEVAL=1`.
- `LLM_RESEARCH_CMD` is intentionally empty by default. When set, it receives the generated research prompt on stdin and writes the brief to stdout. Leave it empty until judgement-heavy research is ready to run unattended.

## Audit Behaviour

The VPS lanes distinguish processing failures from remediation queues:

- hard ETL or parsing errors fail the relevant service;
- reference-data warnings and AU project evidence weaknesses are logged and written into reports, but they do not block unrelated deterministic refreshes;
- weak evidence remains visible in Source Health and AU evidence-audit outputs for supervised remediation.
