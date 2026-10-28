#!/usr/bin/env bash
# Local run of the static checks in validate.yml: TFLint and Checkov.
# Needs tflint (with GITHUB_TOKEN set for the plugin download) and checkov.
set -euo pipefail
cd "$(dirname "$0")/.."
tflint --init
tflint --recursive --format compact
checkov --config-file .checkov.yaml
printf '%s\n' 'TFLint and Checkov passed.'
