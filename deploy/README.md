# Automation — NAS runner (production)

AI & DC uses the same frequency-driven model as the AEMO projects:

- The **NAS runner** (QNAP `ai-wif-runner` container) runs deterministic ETL
  and data-quality checks, scheduled by QNAP scheduled tasks.
- GitHub stores code plus compact dashboard-ready outputs.
- Research that needs LLM judgement is report-only until reviewed.
- Raw AU DC AEMO/NEMOSIS cache is bounded; processed parquet/CSV outputs are
  the durable dashboard layer.

The Streamlit app remains the front-end reader. It does not call the lanes
live. The NAS refreshes data, commits changed tracked outputs, pushes to
GitHub, and Streamlit renders the latest committed data on its normal
redeploy/restart path.

## Current NAS layout (authoritative)

The lane registry, cadence windows, report paths and project checkout live in
`tools/nas-runner/configs/brain-ops.nas.toml` (the NAS runner tooling). The
QNAP scheduled task invokes `nas-job ai-dc-*`, which runs this repo's
`deploy/run-*.sh` entry scripts inside the container with its own
environment overrides (`APP_DIR`, `PYTHON`, `REPORT_DIR`, `RUN_*` toggles).

## Lanes

| Lane | Entry script | Purpose |
| --- | --- | --- |
| Source health | `run-health.sh` | Write a Markdown/JSON source-health report without changing repo data. |
| Deterministic ETL | `run-etl.sh` | Refresh financials, macro, consensus, earnings dates, capex staleness, news catalogue snapshots, ZeroEval/LLM benchmark data when enabled, then commit changed dashboard data. |
| Research brief | `run-research-brief.sh` | Build a structured research prompt and optionally run an LLM command. Current production mode is report-only: no DB/CSV writes. |
| AU DC data | `run-au-data.sh` | Refresh AEMO generation/grid/project outputs, run AU DC checks, prune raw cache, and commit changed processed outputs. Registration snapshot month + demand horizon are resolved dynamically from the latest published AEMO MMS archive (publication-lag aware; S2-08); demand refreshes incrementally (missing months only, never a full 2020+ replay — the full rebuild stays behind the explicit `--full-demand-backfill` flag, and `--skip-demand`/`--no-demand` remain available). |

The `deploy/run-*.sh` names are NAS-native (renamed from the retired
VPS-era `run-vps-*.sh` in the 2026-09 cleanup); the NAS dispatcher invokes them
with environment overrides.

Both committing lanes (`run-etl.sh`, `run-au-data.sh`) open with a self-healing
sync: they try `git pull --ff-only` and, if GitHub `main` has been rewritten
(force-push/rebase) so a fast-forward is impossible, they
`git reset --hard origin/main` and carry on. The clone's only local commits are
regeneratable pipeline data, so a rewrite costs at most one stale cycle instead
of a hard abort.

## Secrets

Secrets are provided to the container at runtime (Bitwarden Secrets Manager
via `bws`); the repo carries no `.env` files. The env-var names the scripts
read are:

- `FMP_API_KEY` enables FMP consensus and earnings-date refresh.
- `ZEROEVAL_API_KEY` enables the ZeroEval/LLM benchmark refresh when `RUN_ZEROEVAL=1`.
- `LLM_RESEARCH_CMD` is intentionally empty by default. When set, it receives the generated research prompt on stdin and writes the brief to stdout. Leave it empty until judgement-heavy research is ready to run unattended.

## Audit Behaviour

The NAS lanes distinguish processing failures from remediation queues:

- hard ETL or parsing errors fail the relevant lane;
- reference-data warnings and AU project evidence weaknesses are logged and written into reports, but they do not block unrelated deterministic refreshes;
- weak evidence remains visible in Source Health and AU evidence-audit outputs for supervised remediation.

---

## Historical: Hetzner VPS + systemd timers (retired)

Before the NAS migration (2026-05) this project ran on a Hetzner VPS under
systemd timers. That setup is **historical** — do not reinstall it:

- layout: `/opt/ai-dc-dashboard`, `/etc/ai-dc-dashboard/*.env`,
  `/var/lib/ai-dc-dashboard/reports/{source-health,research-briefs}`;
- service user `ai-dc` with a repo-scoped deploy key named `ai-dc-nas-bot`;
- timers: `ai-dc-health.timer` (daily ~07:20), `ai-dc-etl.timer`
  (Mon/Wed/Fri ~07:40), `ai-dc-research-brief.timer` (weekly Monday),
  `ai-dc-au-data.timer` (weekly Monday) — Perth time;
- the retired `.service`/`.timer` unit files were deleted in the 2026-09 NAS
  cleanup; `env/*.env.example` remain as NAS-path templates. The QNAP scheduled
  tasks are the live scheduler;
- ✅ the repo-scoped GitHub deploy key titled `ai-dc-vps-bot` (write-enabled,
  created 2026-05-11) has been **revoked** (2026-09-19). The NAS lanes push over
  HTTPS with a stored token; no deploy key is in use.
