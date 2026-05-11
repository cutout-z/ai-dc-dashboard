#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ai-dc-dashboard}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"
PUSH_CHANGES="${PUSH_CHANGES:-1}"
AU_FETCH_ARGS="${AU_FETCH_ARGS:---skip-demand}"
RAW_CACHE_RETENTION_DAYS="${RAW_CACHE_RETENTION_DAYS:-540}"
COMMIT_MESSAGE_PREFIX="${COMMIT_MESSAGE_PREFIX:-Update AU DC dashboard data}"

cd "${APP_DIR}"

git fetch origin main
git checkout main
git pull --ff-only origin main

"${PYTHON}" etl/au_dc/fetch_aemo_nemosis.py ${AU_FETCH_ARGS}
"${PYTHON}" etl/au_dc/build_esoo.py
"${PYTHON}" etl/au_dc/build_project_db.py
"${PYTHON}" scripts/au_dc_project_evidence_audit.py
"${PYTHON}" scripts/prune_au_dc_raw_cache.py --retention-days "${RAW_CACHE_RETENTION_DAYS}"
"${PYTHON}" scripts/source_health_report.py --out-dir "${REPORT_DIR:-/var/lib/ai-dc-dashboard/reports/source-health}" >/dev/null

git add data/au_dc/processed/ data/au_dc/reference/

if git diff --cached --quiet; then
  echo "No AU DC data changes."
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

