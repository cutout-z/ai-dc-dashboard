#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/workspace/repos/ai-dc-dashboard}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"
PUSH_CHANGES="${PUSH_CHANGES:-1}"
# Default: no AU_FETCH_ARGS -> fetch_aemo_nemosis.py runs its publication-lag-aware
# INCREMENTAL demand refresh (only months after the last month already in
# nem_demand_actual.parquet are fetched, never a 2020+ replay).
# Legacy opt-outs still work: AU_FETCH_ARGS=--skip-demand (or --no-demand)
# skips demand; AU_FETCH_ARGS=--full-demand-backfill forces the full rebuild.
AU_FETCH_ARGS="${AU_FETCH_ARGS:-}"
RAW_CACHE_RETENTION_DAYS="${RAW_CACHE_RETENTION_DAYS:-540}"
COMMIT_MESSAGE_PREFIX="${COMMIT_MESSAGE_PREFIX:-Update AU DC dashboard data}"

cd "${APP_DIR}"

git fetch origin main
git checkout main
# Self-heal: this clone only ever holds regeneratable pipeline data commits, so
# when GitHub main has been rewritten (force-push/rebase) a fast-forward becomes
# impossible. Reset onto the fetched remote instead of aborting — a bare
# `git pull --ff-only` under `set -e` exited 128 and stalled the lane for weeks
# (2026-09-03 rewrite → ai-dc-etl / ai-dc-au-data dead until 2026-09-17).
if ! git pull --ff-only origin main; then
  echo "origin/main is not fast-forwardable (rewritten?) — resetting onto it."
  git reset --hard origin/main
fi

"${PYTHON}" etl/au_dc/fetch_aemo_nemosis.py ${AU_FETCH_ARGS}
"${PYTHON}" etl/au_dc/build_esoo.py
"${PYTHON}" etl/au_dc/build_project_db.py
"${PYTHON}" scripts/au_dc_project_evidence_audit.py
"${PYTHON}" scripts/prune_au_dc_raw_cache.py --retention-days "${RAW_CACHE_RETENTION_DAYS}"
"${PYTHON}" scripts/source_health_report.py --out-dir "${REPORT_DIR:-/workspace/reports/ai-dc-dashboard/source-health}" >/dev/null

git add data/au_dc/processed/ data/au_dc/reference/

if git diff --cached --quiet; then
  echo "No AU DC data changes."
  exit 0
fi

git config user.name "${GIT_AUTHOR_NAME:-ai-dc-nas-bot}"
git config user.email "${GIT_AUTHOR_EMAIL:-ai-dc-nas-bot@users.noreply.github.com}"
git commit -m "${COMMIT_MESSAGE_PREFIX} $(date -u +%Y-%m-%d)"

if [[ "${PUSH_CHANGES}" == "1" ]]; then
  git push origin main
else
  echo "PUSH_CHANGES=0; commit created but not pushed."
fi

