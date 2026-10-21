#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  echo 'Install the test dependency: python3 -m pip install PyYAML==6.0.3' >&2
  exit 1
fi
python3 -m unittest discover -s tests/pipeline -v
python3 scripts/verify_network.py
python3 -m unittest discover -s tests -v
if command -v actionlint >/dev/null 2>&1; then
  actionlint -shellcheck= -pyflakes= .github/workflows/*.yml
fi
printf '%s\n' 'Pipeline policy and workflow checks passed. No OIDC login, Azure plan/apply or hosted workflow was executed.'
