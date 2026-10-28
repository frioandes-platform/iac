# Pipeline validation record (#23)

## Local diagnostics revision — 2026-10-28

This verification was run on `fix/local-build-diagnostics`, based on updated
`main` at `01d9942b7237a58e5fe3fc4d317188016f47b9d2`. HEAD and main resolve
to that same commit; the results below include the uncommitted changes in
`scripts/pipeline/run.py` and this document. They replace the earlier local
results from `08fab5d` as evidence for this revision.

### Scope and merge review

Detailed stage labels, exit codes and stdout/stderr are enabled only for the
Go build, Docker build and container self-test reached through `build-local`.
Cloud build and promotion retain diagnostics disabled by default; Azure CLI,
Key Vault, Terraform and registry authentication keep raw output withheld.

Comparison with main confirmed that driver code outside the three diagnostic
functions and the local opt-in is unchanged, including the production budget
for every remaining root and the gate immediately before each apply. Existing
approval, runner separation, ordered promotion and stop-at-test checks pass.
The upstream `COPY --chmod=0555` correction is already present and unchanged.

Only the two files named above differ from main. CIDRs, approved CSVs,
provenance hashes, module contracts, lock files, workflows and the existing
TFLint, Checkov and Infracost integrations are unchanged.
`stash@{0}` was retained as backup without modification. No commit, push,
merge or branch synchronization was performed during this review.

### Versions and results obtained in this revision

Python 3.12.3; PyYAML 6.0.3 from the existing `.venv`; Go 1.22.2;
Terraform 1.16.6; AzureRM 4.62.0; Docker client/server 29.8.2;
actionlint 1.7.7. Local Go and Terraform differ from the workflow's pinned
Go 1.27.3 and Terraform 1.9.8; no local execution with those pinned versions
is claimed.

For the pipeline check, the existing virtual environment and actionlint
installation were selected with:

```bash
PATH="$PWD/.venv/bin:/tmp/frioandes-pipeline-repair/actionlint-bin:$PATH" bash scripts/check-pipeline.sh
```

| Command/check | Observed result |
| --- | --- |
| `git diff --check` | Passed |
| `bash scripts/check-pipeline.sh` with the PATH above | Passed: 47 pipeline tests, 17 network/security tests, snapshot checks and actionlint |
| `terraform fmt -check -recursive` | Passed |
| `bash scripts/check-ingest.sh` | Passed: 17 Python tests; backend-disabled init, validate and mocked tests in connectivity/dev/test/prod; seven firewall/NSG comparisons without discrepancies; local evidence hashes recorded |
| `python3 scripts/pipeline/run.py build-local` | Go build, Docker build and hardened non-root container self-test exited 0; `release-probe self-test passed` |
| Driver AST comparison against main | Passed: unchanged code outside the diagnostic functions and local opt-in |
| Synthetic subprocess failure assertions | Passed: local diagnostics include stage, stdout/stderr and exit 126; failed Azure/Key Vault, Terraform plan/apply and Docker login commands withhold raw output and stop execution |

The existing tests cover approvals, incident authorization, plan integrity,
dev→test→prod ordering, the Bogotá window and the budget for all remaining
production roots. These mocked tests and synthetic assertions do not represent
authenticated cloud operations. No additional test file was added.

### Historical container evidence

The earlier investigation on `08fab5d` reproduced
[run 39685042086](https://github.com/frioandes-platform/iac/actions/runs/39685042086):
the Docker build passed, but container execution exited 126 with
`/release-probe: permission denied`. The driver's `umask 077` produced a
`0700` binary; the original COPY preserved that mode, preventing execution
by user `65532:65532`. PR #5 incorporated `COPY --chmod=0555`.

The previously inspected
[run 40623395989](https://github.com/frioandes-platform/iac/actions/runs/40623395989)
passed for PR #5 head `4fc64744fa69c4db12b6d34438b2ff2b42aa2dda`, including
the container self-test. That historical run predates the new diagnostics
and is not evidence for this revision.

### Remaining verification

No GitHub Actions run containing these uncommitted changes was triggered or
verified. After an authorized commit/push to the follow-up PR, verify the new
workflow runs at that exact commit and record their URLs and conclusions here.
Rerunning the old failed execution would only retest its old commit.

TFLint, Checkov and Infracost were not executed in this local review. Their
existing integrations were neither duplicated nor expanded; passing structural
workflow tests does not establish new scanner or cost-estimation results.

Cloud promotion remains `enabled: false`. No OIDC login, Key Vault read,
registry push or authenticated Terraform plan/apply was performed. Real
approvals, campaign controls, incident deployment and live Azure behavior
remain subject to bootstrap and the validation matrix in
[bootstrap.md](bootstrap.md).
