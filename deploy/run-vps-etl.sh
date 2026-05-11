#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ai-dc-dashboard}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"
PUSH_CHANGES="${PUSH_CHANGES:-1}"
RUN_ZEROEVAL="${RUN_ZEROEVAL:-0}"
RUN_REFERENCE_AUDIT="${RUN_REFERENCE_AUDIT:-1}"
COMMIT_MESSAGE_PREFIX="${COMMIT_MESSAGE_PREFIX:-Update AI & DC dashboard data}"

cd "${APP_DIR}"

git fetch origin main
git checkout main
git pull --ff-only origin main

"${PYTHON}" scripts/fetch_financials.py
"${PYTHON}" etl/fetch_macro.py
"${PYTHON}" etl/refresh_consensus.py
"${PYTHON}" etl/refresh_earnings_dates.py
"${PYTHON}" etl/refresh_capex_guidance.py
"${PYTHON}" scripts/catalog_news.py

if [[ "${RUN_ZEROEVAL}" == "1" ]]; then
  "${PYTHON}" scripts/fetch_llm_benchmarks.py
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

"${PYTHON}" scripts/source_health_report.py --out-dir "${REPORT_DIR:-/var/lib/ai-dc-dashboard/reports/source-health}" >/dev/null

git add data/reference/ data/db/ai_research.db data/fetcher_log.json data/stale_guidance.json

if git diff --cached --quiet; then
  echo "No AI & DC ETL data changes."
  exit 0
fi

git config user.name "${GIT_AUTHOR_NAME:-ai-dc-vps-bot}"
git config user.email "${GIT_AUTHOR_EMAIL:-ai-dc-vps-bot@users.noreply.github.com}"
git commit -m "${COMMIT_MESSAGE_PREFIX} $(date -u +%Y-%m-%d)"

if [[ "${PUSH_CHANGES}" == "1" ]]; then
  git push origin main
else
  echo "PUSH_CHANGES=0; commit created but not pushed."
fi
