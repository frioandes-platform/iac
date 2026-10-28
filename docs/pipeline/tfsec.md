# tfsec integration and detection demonstration

## Reproducible installation

The repository uses tfsec **1.28.14**, the release requested by this integration,
on Linux amd64 (the contributor's Ubuntu system and GitHub's ubuntu-24.04 runner).
Python 3.10+, network access for installation, and the Python standard library
are sufficient. Neither Azure credentials nor an Azure subscription are needed.

```bash
python3 scripts/tfsec.py install
python3 scripts/tfsec.py scan
python3 scripts/tfsec.py test-detection
```

`install` downloads only the versioned official release archive, verifies its
SHA-256 before reading it, extracts only the `tfsec` regular file, then checks
the binary SHA-256. Both hashes and the version are fixed in `scripts/tfsec.py`.
Every scan verifies the binary again. A changed binary fails closed; remove the
local binary and reinstall from the reviewed release instead of accepting drift.

| Item | SHA-256 |
| --- | --- |
| Official Linux amd64 archive | `329ae7f67f2f1813ebe08de498719ea7003c75d3ca24bb0b038369062508008e` |
| Extracted binary | `a32d0799bbefababaa4fcd814da9f4d251cd932789590b99d1d5fcb89ace6f68` |

The binary is stored under `.tools/tfsec/1.28.14/`, ignored by Git. It is not
committed or downloaded from a moving `latest` or branch URL. Aqua now directs
tfsec users toward Trivy; this integration intentionally retains tfsec for the
academic requirement. Its migration notice on stderr is expected.

## Coverage and failure behavior

The scanner runs independently against eight explicit targets:

- `modules/network`
- `modules/security`
- `modules/security/subnet-controls`
- `modules/ingest`
- `environments/connectivity`
- `environments/dev`
- `environments/test`
- `environments/prod`

Local child modules are followed as well; findings across target runs can refer
to the same underlying resource. Counts must not be added as unique resources.
Remote module downloads are disabled; this repository uses local modules.
There are no severity filters, ignore comments, excluded checks or accepted
tfsec findings added by this integration. All severities use the scanner's
defaults. Ambient `TFSEC_*` flags are removed from its subprocess environment.

Any nonzero scan exit makes the wrapper fail. The workflow does not use
`continue-on-error`, `soft-fail` or an event condition to skip PRs. The dedicated
`tfsec` job runs independently from TFLint/Checkov, with repository contents read
permission and no Azure login or repository secrets. Merge blocking additionally
requires the repository owner to select this check in branch protection/rulesets;
the workflow alone does not configure GitHub's merge rules.

## Interpretation limits

The current source uses `csvdecode`, complex expressions and `for_each` to create
rules. tfsec's supported checks/adapters do not fully evaluate this design.
During the authoring scan, all eight targets parsed and completed, but the
scanner reported **zero passed checks and zero findings**. This is not evidence
that every generated firewall/NSG rule, Event Hubs property or AzureRM 4.x
attribute was checked. Future literal changes can still match its supported
rules, as the live detection probe demonstrates.

Keep TFLint, Checkov, `terraform validate`, the mocked module tests and the
independent CSV/policy comparators. tfsec supplements those controls; it does
not replace them or prove that deployed traffic, identities or Azure behave as
designed. Do not introduce blanket exceptions to hide evaluation limitations.

## Reproducible negative and corrected example

`test-detection` creates a complete, synthetic `azurerm_network_security_rule`
inside a temporary directory. It first permits inbound SSH from `0.0.0.0/0` and
requires both exit code **1** and the actual
`azure-network-ssh-blocked-from-internet` finding in the scanner's JSON report.
The same rule is restricted to a synthetic private `/24`; the probe then requires
exit code **0** and no findings. A crash, missing report or unrelated error does
not count as a successful detection. The temporary fixture and reports are
removed automatically and no Terraform deployment command is called.

This is a detector self-test. It does not intentionally commit unsafe Terraform
to the project's modules, alter the address plan or prove coverage of dynamic
CSV translation. For the live presentation, show the two exit-code assertions
and then the separate source-policy comparisons.

## Local checks and CI evidence

`bash scripts/check-static.sh` runs the tfsec scan and detector probe, followed
by the existing TFLint and Checkov commands. Install those existing tools first
when running the combined command. `python3 scripts/tfsec.py scan` runs only tfsec.

The change is based on main commit
`01d9942b7237a58e5fe3fc4d317188016f47b9d2`, independently of pending PRs #7 and #8.
No Terraform HCL, policy CSV, source manifest, provider lock, deployment gate or
cloud configuration is changed by this integration.

Authoring checks on 2026-10-28 completed installation, eight-target scanning and
the real negative/corrected tfsec probe. Workflow and helper regressions are
recorded in the delivery instructions. They do not constitute a hosted Actions
execution of this new job. After pushing the integration, record the new commit
and Actions URL and verify the `tfsec` job completes all three steps. The
existing jobs remain responsible for module and source-policy regression checks.

## Primary references

- [Official release](https://github.com/aquasecurity/tfsec/releases/tag/v1.28.14)
- [Official archive checksums](https://github.com/aquasecurity/tfsec/releases/download/v1.28.14/tfsec_1.28.14_checksums.txt)
- [Pinned usage documentation](https://github.com/aquasecurity/tfsec/blob/v1.28.14/docs/guides/usage.md)
- [Public SSH check](https://aquasecurity.github.io/tfsec/latest/checks/azure/network/ssh-blocked-from-internet/)
