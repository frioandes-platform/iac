#!/usr/bin/env bash
# Local static checks: tfsec, TFLint and Checkov.
# Install tfsec with python3 scripts/tfsec.py install first.
# Also needs tflint (GITHUB_TOKEN for the plugin download) and checkov.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/tfsec.py scan
python3 scripts/tfsec.py test-detection
tflint --init
tflint --recursive --format compact
checkov --config-file .checkov.yaml
printf '%s\n' 'tfsec, its detection probe, TFLint and Checkov passed.'
