#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
terraform fmt -check -recursive
python3 scripts/verify_network.py
python3 -m unittest discover -s tests -v
mkdir -p .security-verification

for environment in connectivity dev test prod; do
  terraform -chdir="environments/$environment" init -backend=false -input=false
  terraform -chdir="environments/$environment" validate
  if ! terraform -chdir="environments/$environment" test -json -verbose > ".security-verification/$environment.jsonl"; then
    cat ".security-verification/$environment.jsonl"
    exit 1
  fi
  printf '%s\n' "Mocked Terraform tests passed: $environment"
done

tokens="tests/fixtures/security-tokens.json"
python3 scripts/verify_security.py --kind firewall --plan .security-verification/connectivity.jsonl --run development_stable_policy --tokens "$tokens" --environments dev
python3 scripts/verify_security.py --kind firewall --plan .security-verification/connectivity.jsonl --run all_environments_stable_policy --tokens "$tokens" --environments dev test prod
python3 scripts/verify_security.py --kind firewall --plan .security-verification/connectivity.jsonl --run migration_explicitly_selected --tokens "$tokens" --environments dev test prod --temporary FW-401 FW-402 FW-501 FW-502 FW-503 FW-504
for environment in dev test prod; do
  python3 scripts/verify_security.py --kind nsg --plan ".security-verification/$environment.jsonl" --run subnet_policy_matches_table --tokens "$tokens" --environments "$environment"
done
python3 scripts/verify_security.py --kind nsg --plan .security-verification/prod.jsonl --run subnet_migration_explicitly_selected --tokens "$tokens" --environments prod --temporary NSG-prod-11 NSG-prod-12 NSG-prod-14
python3 - <<'PY'
import hashlib, json
from pathlib import Path
from scripts.verify_security import security_content_hashes
directory = Path('.security-verification')
record = {
    'code_hashes': security_content_hashes(),
    'plan_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob('*.jsonl')},
    'checks': 'validate, mocked plans, Python tests and independent comparisons passed',
}
(directory / 'provenance.json').write_text(json.dumps(record, indent=2) + '\n')
print('Security verification completed; evidence hashes recorded.')
PY
