#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 scripts/verify_network.py
python3 -m unittest discover -s tests -v
terraform fmt -check -recursive

for environment in dev test prod; do
  terraform -chdir="environments/$environment" init -backend=false -input=false
  terraform -chdir="environments/$environment" validate
  terraform -chdir="environments/$environment" test
done
