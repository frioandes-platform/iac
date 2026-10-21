# Security module — planning issue #21

Creates one shared Azure Firewall Standard and Firewall Policy in the
connectivity subscription. Explicit network and application collections are
derived from the reviewed CSV. The `subnet-controls` submodule creates the
application NSGs and associations in each environment's own subscription.

## Source of truth

The exact upstream files are vendored in `data/` from planning commit
`bcb98b538ac7df7f8733c7ed949cef9290d650bc`:

| File | SHA-256 |
|---|---|
| `firewall-policy.csv` | `3f3e8359f220968fa873ee3fc050c44ac860f7cdb079db5858f9a3a489f7684a` |
| `firewall-settings.csv` | `c41ed2e0a2259101486961cfbc535c5bbfd9cc027bae5d7de8b08a8bdb45001d` |
| `ip-plan.csv` | `a520eba842e6d7781705613d539fcfd018bfd00481f3842814d07d97036b91a0` |

`source.json` also records the original paths and Git blob hashes. CSV content
and line endings are preserved. The policy has 100 rows: 41 Azure Firewall,
47 NSG, 10 WAF and 2 IoT Hub/DPS. These control points are not interchangeable.
Do not regenerate firewall rules from a diagram or edit the copied table
without an approved planning change and updated provenance.

The corrected network module from #20 is based on IaC commit
`80bce9aecfe653a6c81b8eda41d1473421325373`. Both modules now retain the exact
same corrected `ip-plan.csv` from planning PR #64. Their SHA-256 values match;
the security verifier checks this agreement. The network module reads its
source directly and retains the canonical copy only for verification.
Its inputs, outputs, names, CIDRs and delegations are preserved.

## Deployment composition and reference scope

- `environments/connectivity` owns the shared firewall, its two public-IP roles,
  the approved hub VNet and its two firewall subnets. Future gateway, Bastion,
  DNS resources, peering and routing are not created here. Import any existing
  hub/RG/subnets rather than managing them from two states.
- Application roots call `modules/network` and `modules/security/subnet-controls`.
  NSGs live beside the application subnets, not in the connectivity subscription.
- The reference environment is **dev**: 11 explicit stable firewall rules,
  implicit FW-999, and 14 stable NSG table rows. The final NSG deny expands to
  one rule in each of the 11 application subnet NSGs (24 actual NSG rules).
- Set `protected_environments` on the connectivity root deliberately to include
  test/prod in the same policy. The module supports all 34 explicit stable
  firewall rows plus six explicitly selected temporary firewall rows.
- No dev WAF or IoT service rule exists in the source table. The prod/test WAF,
  prod IoT/DPS credentials and hub DNS NSGs remain at their own control points;
  this delivery does not claim those resources are configured. The report
  classifies every source row rather than silently dropping them.

## Important translations

`tag:AzureMonitor` becomes the Azure service tag in a network rule;
`fqdn:...` becomes an application-rule FQDN. HTTP/80 and HTTPS/443 are paired
separately; the translator never opens HTTPS/80 by taking their cross product.

**FW-999 is implicit default denial.** It is not emitted as a wildcard
network-deny collection: Azure processes network rules before application
rules, so such a collection would block intended application access. The
firewall retains Azure platform infrastructure-rule and stateful-return
semantics; the table is not a complete packet-level description of Azure.

Threat intelligence is `Deny` (the API value for alert and deny), DNS proxy is
off, and no-SNAT ranges are copied exactly from settings. Broad RFC1918 defaults
must not replace that list, because private endpoint destinations require SNAT
in the reviewed design. One egress public IP is separate from the management IP.
TLS termination and DNAT publication are not enabled.

## Unresolved values and temporary migration access

Some source tokens require customer-confirmed values, for example
`fqdn:<registro>.azurecr.io`, `fqdn:<dominios-del-proveedor>` and
`<ip-publicas-cali>`. Supply whole-token mappings through `security_token_values`
on a root. Values are lists to allow explicitly approved multiple destinations.
No production endpoints or client IPs are guessed. Selected unresolved tokens
block a plan. A mapping cannot introduce a global `*` allow.

`tests/fixtures/security-tokens.json` contains only fictitious test domains
and documentation IPs. It is read by mocked tests; no real root loads it by
default. Never reuse it as deployment configuration.

Temporary access defaults to **disabled**. Select individual IDs using
`active_temporary_firewall_rules` in connectivity or
`active_temporary_nsg_rules` in an application root, and supply an approved
`migration_change_reference`. Collections, rule descriptions and the output
register identify temporary access and retain its retirement condition.

Remove FW-501/502 and NSG-prod-12 at the database cutover, FW-402 when hourly
loads end, NSG-prod-11 when archive copying ends, and the remaining rules when
rollback closes, according to the exact source milestones (no later than day
90 where specified). Terraform does not remove rules merely because time
passes: the responsible operator must change the selected IDs, review a plan
and apply the removal through the approved process. Each milestone can retire
a different subset; enabling migration is not one permanent boolean.

## Validation

Requirements: Terraform >= 1.7, < 2; AzureRM 4.62.0 in the environment roots;
Python >= 3.10. From the repository root:

```bash
terraform fmt -recursive
bash scripts/check-security.sh
```

The script initializes the four roots without a backend, validates them and
runs mocked plans. It then compares actual planned security resources with
the source table: IDs, type, action, source, destination, protocol/port pairs,
group priority, temporary marking and relevant firewall settings. JSON evidence
is stored under the ignored `.security-verification/` directory. No Azure
authentication or apply is required. Initialization still downloads providers.

For a real saved plan, use the same independent comparator, for example:

```bash
python3 scripts/verify_security.py --kind firewall --plan path/to/plan.json \
  --tokens path/to/approved-token-values.json --environments dev
```

Use `--kind nsg --environments dev` for an application root. Declare the
temporary IDs actually selected with `--temporary` when verifying migration.

The optional command below evaluates the exact module locals with Terraform
Core when a host cannot start providers. Its comparator records are synthetic;
it is **not** a substitute for validate or mocked provider plans:

```bash
python3 scripts/evaluate_security_contract.py --out .security-verification/core.json
```

The seven original network tests plus ten comparator/provenance regression tests run
with Python. A new denied connection or missing table row is not hidden by an
"all tests passed" statement: the report records exactly which checks ran.

The successful network-only run recorded in `VALIDATION.md` belongs to #20.
It does not substitute for running `check-security.sh` after adding this module.

## Before deployment

Configure the correct subscription per root and a separate remote-state key.
Register service namespaces through platform bootstrap. Provide approved token
values, diagnostics to the central workspace and the reviewed UDR/peering/DNS
integration. Confirm required platform traffic for Container Apps, Functions,
MySQL and Application Gateway before applying restrictive NSGs; mocked plans
cannot prove live service health. NSG defaults, DNS and return routing require
operational tests. No complete hybrid routing, WAF, IoT authentication or live
security enforcement is claimed by this module alone.

## References

- [Planning #21](https://github.com/frioandes-platform/planning/issues/21)
- [Planning #9](https://github.com/frioandes-platform/planning/issues/9)
- [Azure Firewall rule processing](https://learn.microsoft.com/en-us/azure/firewall/rule-processing)
- [AzureRM rule collection group](https://registry.terraform.io/providers/hashicorp/azurerm/4.62.0/docs/resources/firewall_policy_rule_collection_group)
