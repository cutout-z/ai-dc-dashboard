# VPS Automation

AI & DC uses the same frequency-driven model as the AEMO projects:

- The VPS runs deterministic ETL and data-quality checks.
- GitHub stores code plus compact dashboard-ready outputs.
- Research that needs LLM judgement is report-only until reviewed.
- Raw AU DC AEMO/NEMOSIS cache is bounded; processed parquet/CSV outputs are the durable dashboard layer.

## Lanes

| Lane | Timer | Script | Purpose |
| --- | --- | --- | --- |
| Deterministic ETL | `ai-dc-etl.timer` | `run-vps-etl.sh` | Refresh financials, macro, consensus, earnings dates, capex staleness, optional ZeroEval data, then commit changed dashboard data. |
| AU DC data | `ai-dc-au-data.timer` | `run-vps-au-data.sh` | Refresh AEMO generation/grid/project outputs, run AU DC checks, and prune raw cache. Routine lane skips the full 2020+ demand rebuild. |
| Source health | `ai-dc-health.timer` | `run-vps-health.sh` | Write a Markdown/JSON source-health report without changing repo data. |
| Research brief | `ai-dc-research-brief.timer` | `run-vps-research-brief.sh` | Build a structured research prompt and optionally run an LLM command. Report-only: no DB/CSV writes. |

## Recommended VPS Layout

```text
/opt/ai-dc-dashboard                 git checkout + virtualenv
/etc/ai-dc-dashboard/*.env           per-lane settings
/var/lib/ai-dc-dashboard/reports     report-only outputs
```

The service user needs a repo-scoped deploy key that can pull and push `cutout-z/ai-dc-dashboard`.

## Install

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

## Secrets

Use environment files or systemd credentials on the VPS, not macOS Keychain.

- `FMP_API_KEY` enables FMP consensus and earnings-date refresh.
- `ZEROEVAL_API_KEY` should be wired before enabling `RUN_ZEROEVAL=1`; the current scripts still support macOS Keychain locally, so VPS secret support should be added before that lane is turned on.
- `LLM_RESEARCH_CMD` is intentionally empty by default. When set, it receives the generated research prompt on stdin and writes the brief to stdout.

