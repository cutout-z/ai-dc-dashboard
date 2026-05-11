#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ai-dc-dashboard}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"
REPORT_DIR="${REPORT_DIR:-/var/lib/ai-dc-dashboard/reports/research-briefs}"
LLM_RESEARCH_CMD="${LLM_RESEARCH_CMD:-}"

cd "${APP_DIR}"
mkdir -p "${REPORT_DIR}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PROMPT_PATH="${REPORT_DIR}/ai-dc-research-prompt-${STAMP}.md"
REPORT_PATH="${REPORT_DIR}/ai-dc-research-brief-${STAMP}.md"

"${PYTHON}" scripts/build_research_brief_prompt.py > "${PROMPT_PATH}"

if [[ -z "${LLM_RESEARCH_CMD}" ]]; then
  {
    echo "# AI & DC Research Brief — ${STAMP}"
    echo
    echo "LLM_RESEARCH_CMD is not configured. Prompt staged for supervised review:"
    echo
    echo "\`${PROMPT_PATH}\`"
  } > "${REPORT_PATH}"
  cat "${REPORT_PATH}"
  exit 0
fi

bash -lc "${LLM_RESEARCH_CMD} < '${PROMPT_PATH}' > '${REPORT_PATH}'"
cat "${REPORT_PATH}"

