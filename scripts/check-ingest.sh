#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1

# Includes the unchanged #20/#21 regressions and every environment's test files.
# The new tests include mock applies; mock_provider prevents calls to Azure.
bash scripts/check-security.sh
printf '%s\n' 'Ingest checks completed, including mocked integration and rejection cases. No live Azure deployment was performed.'
