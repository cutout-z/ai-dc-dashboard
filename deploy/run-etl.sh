#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/workspace/repos/ai-dc-dashboard}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"
PUSH_CHANGES="${PUSH_CHANGES:-1}"
RUN_ZEROEVAL="${RUN_ZEROEVAL:-0}"
RUN_REFERENCE_AUDIT="${RUN_REFERENCE_AUDIT:-1}"
COMMIT_MESSAGE_PREFIX="${COMMIT_MESSAGE_PREFIX:-Update AI & DC dashboard data}"

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

"${PYTHON}" scripts/fetch_financials.py
"${PYTHON}" etl/fetch_macro.py
"${PYTHON}" etl/refresh_consensus.py
"${PYTHON}" etl/refresh_earnings_dates.py
"${PYTHON}" etl/refresh_capex_guidance.py
"${PYTHON}" scripts/catalog_news.py

if [[ "${RUN_ZEROEVAL}" == "1" ]]; then
  "${PYTHON}" scripts/refresh_llm_leaderboard.py
fi

if [[ "${RUN_REFERENCE_AUDIT}" == "1" ]]; then
  set +e
  "${PYTHON}" scripts/audit_reference_data.py
  audit_status=$?
  set -e
  if [[ "${audit_status}" -ge 2 ]]; then
    exit "${audit_status}"
  elif [[ "${audit_status}" -ne 0 ]]; then
    echo "Reference audit emitted warnings; continuing because no hard errors were found."
  fi
fi

"${PYTHON}" scripts/source_health_report.py --out-dir "${REPORT_DIR:-/workspace/reports/ai-dc-dashboard/source-health}" >/dev/null

git add data/reference/ data/db/ai_research.db data/fetcher_log.json data/stale_guidance.json

if git diff --cached --quiet; then
  echo "No AI & DC ETL data changes."
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
