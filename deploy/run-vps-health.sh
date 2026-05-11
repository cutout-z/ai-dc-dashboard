#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ai-dc-dashboard}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"
REPORT_DIR="${REPORT_DIR:-/var/lib/ai-dc-dashboard/reports/source-health}"

cd "${APP_DIR}"
mkdir -p "${REPORT_DIR}"
"${PYTHON}" scripts/source_health_report.py --out-dir "${REPORT_DIR}"

