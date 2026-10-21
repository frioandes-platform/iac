# Telemetry alert ingestion module — planning #22

Creates the representative **alert event hub** from planning #13 (Carga B),
sections 3.2 and 5.2. Stream Analytics will write detected alerts to this buffer;
the notifier will consume them. This is not a replacement for IoT Hub/DPS and
does not connect real sensors or trucks to development.

## Architecture and provenance

- IaC base: `ba083b0e5d802527b13b09e679ab8f4c5037952d` (#21), incorporating
  #20 corrections from `80bce9aecfe653a6c81b8eda41d1473421325373`.
- Planning commit: `bcb98b538ac7df7f8733c7ed949cef9290d650bc`.
- [Telemetry design, sections 3.2 and 5.2](https://github.com/frioandes-platform/planning/blob/bcb98b538ac7df7f8733c7ed949cef9290d650bc/docs/architecture/carga-b-telemetria.md),
  Git blob `40503eae841674b66f060baa3cdc53a4241b538d`.
- [Network design, sections 5.6 and 6.1](https://github.com/frioandes-platform/planning/blob/bcb98b538ac7df7f8733c7ed949cef9290d650bc/docs/architecture/red-topologia-subnetting.md).
- Existing network/security source manifests and CSV files are unchanged. In
  particular, the corrected IP plan SHA-256 remains
  `a520eba842e6d7781705613d539fcfd018bfd00481f3842814d07d97036b91a0`.

This module copies no address plan or policy table. It consumes module outputs.
The caller owns the reviewed source snapshots and their integrity checks.

## Resources and decisions

| Resource | Configuration and reason |
|---|---|
| Event Hubs namespace | Standard, one throughput unit, matching the telemetry design. No auto-inflate for this small reference instance. |
| `alerts` event hub | Active, two partitions, seven-day retention. Seven days follows the alert-buffer design; two partitions is an explicit initial implementation assumption, not a measured sizing result. Standard partition counts are not freely changeable in place. |
| Consumer groups | `notifier`; development also has `verification` so a smoke test does not compete with notifier checkpoints. |
| Private endpoint | `namespace` subresource, in the existing `snet-data-pe`. No CIDR or static IP allocation. |
| DNS zone group | Uses the shared `privatelink.servicebus.windows.net` ID supplied by connectivity. Does not create a zone in every environment. |
| Data permissions | Optional named maps of Entra object IDs, scoped to the single `alerts` event hub, Sender or Receiver. Empty maps grant no application access. |

The namespace denies general public network access at both namespace and rule-set
levels. SAS/local authentication is disabled; TLS 1.2 is required. The trusted
Microsoft services exception remains enabled for the future Stream Analytics
managed identity, as designed in #13. The exception does **not** authorize every
trusted service to read/write: the relevant Entra identity still needs its data
role. There are no namespace keys or connection strings in outputs. AzureRM may
still retain service-returned sensitive attributes in state; protect the state
using the deployment workflow from #23.

## Integration contract

See the complete root call in [environments/dev/ingest.tf](../../environments/dev/ingest.tf).

- `network.vnet_id`, `network.subnet_id` and endpoint policy mode come directly
  from `module.network`; the selected key is `snet-data-pe`.
- `security.nsg_id` and rule IDs come directly from `module.subnet_security`.
- The root explicitly depends on `module.subnet_security`, including its rules
  and associations; an NSG ID alone is insufficient to guarantee this ordering.
- NSG enforcement must be enabled for the private endpoint. The notifier allow
  rule (`NSG-dev-13`, `NSG-test-13`, or `NSG-prod-17`) and default denial must exist.
- The module does not recreate, change or broaden the #21 rules. An NSG controls
  IP/port traffic, not the Event Hubs entity or its Entra identity. In particular,
  approved HTTPS rules to the shared data subnet can also reach this endpoint;
  entity-scoped RBAC remains essential.
- Within the application VNet, the existing NSG is the relevant network control.
  No claim is made that this local path traverses the hub firewall: #20/#21 do not
  yet provision the complete reviewed routing and peering topology.

`snet-ingest` is reserved for IoT Hub/DPS private endpoints. Selecting it for this
Event Hubs component fails the module precondition.

## Inputs and outputs

Required inputs: environment, globally unique namespace name, resource group,
location, governance tags, the network/security objects above, and shared DNS
zone ID. Optional `sender_principal_ids` and `receiver_principal_ids` are maps
with stable labels as keys and Entra **object IDs**, not application/client IDs.
Use managed identities for the future Stream Analytics job and notifier.

Outputs include namespace ID/FQDN, event hub ID/name, notifier consumer group,
private endpoint ID and configured integration properties. Application resource
IDs must be passed from outputs, not recreated as strings in production code.

The root only enables this module in development and only when `ingest` is set.
Test and production remain unchanged. Reuse in those environments requires
reviewed inputs and live validation; this PR does not certify production.

## Shared DNS and activation order

[environments/connectivity/eventhub-dns.tf](../../environments/connectivity/eventhub-dns.tf)
optionally owns one shared zone, a hub link and explicit spoke links. Application
links enable Azure-provided DNS inside each VNet without waiting for the hybrid
resolver. They do not replace the hub Private DNS Resolver required for Cali.
VNets using custom DNS need the corresponding forwarding path as well.

There are separate Terraform states/subscriptions. Outputs are explicit inputs
between roots; this module does not assume a local backend or invent remote-state
locations before #23. During an authorized deployment:

1. Provision the reviewed dev network/security root with `ingest = null`.
2. Pass its `vnet_id` output as `eventhub_dns_spoke_vnet_ids.dev` to connectivity.
   Set `enable_eventhub_private_dns = true`. Provision the shared zone and links.
3. Pass `eventhub_private_dns.zone_id` from connectivity to `ingest.private_dns_zone_id`
   in dev; select a unique namespace name and real approved sender/receiver object
   IDs. Review and deploy the resulting dev plan.

If the shared zone already exists, import it into its designated state or reuse
its current owner/output. Do not create a second zone with the same name or import
a resource into two states. Reusing an externally managed zone also requires a
verified VNet link. Cross-subscription deployments require permissions to link the
VNet and manage the zone group. The IDs come from actual deployed outputs; the
UUIDs in tests are fictional and must never be used for deployment.

This sequence is a runbook, not evidence that these resources have been deployed.
No subscription, sender identity or live endpoint has been supplied in this task.

## Checks

From the repository root:

```bash
terraform fmt -recursive
bash scripts/check-ingest.sh
```

The script includes all #20/#21 Python and Terraform regressions. Seven additional
Terraform runs cover the opt-in root, integration with actual network/security
configuration under a mocked provider, shared DNS, and rejected subnet/policy/rule
inputs. `command = apply` appears only inside the mocked integration test; it
applies to disposable test state and does not call Azure. Tests still require
Terraform to start the AzureRM provider and load its schema.

See [docs/ingest-validation.md](../../docs/ingest-validation.md) for the recorded
authoring results and remaining validation, rather than assuming that the
previous #21 validation automatically validates #22.

## Live acceptance test after an authorized deployment

1. Confirm the private endpoint connection is approved. Obtain its actual private
   IP, and confirm the normal namespace FQDN resolves to that address from an
   authorized dev agent/workload. A public workstation is not a valid positive
   test location.
2. Use an approved dev identity with Sender and Receiver on the `alerts` entity.
   The existing admin-subnet HTTPS rule can support an approved agent using AMQP
   over WebSockets (443); verify the effective NSG and route path. Do not put a VM
   in a subnet delegated to Container Apps or Functions just to run this test.
3. In an isolated Python environment, install `azure-identity` and `azure-eventhub`.
   Provide the normal identity mechanism (managed identity or an authenticated
   developer session), then run:

```bash
python3 scripts/smoke_alert_ingest.py \
  --namespace "$ALERT_NAMESPACE_FQDN" \
  --expected-private-ip "$ALERT_PRIVATE_IP" \
  --confirm-dev
```

The script sends and receives one synthetic correlation-tagged event using the
`verification` group. It does not contain temperature, GPS or personal data.
Record the deployed IaC SHA, UTC time, environment, identity type and result.
Also verify denial from an unauthorized network and from an identity without a
data role. A TCP handshake alone is not proof of data access or denial.

This demonstrates the representative ingestion component, not the sensor-to-screen
alert SLA: IoT Hub, Stream Analytics, the notifier and real clients are outside
this delivery. The smoke-test timeout is not evidence of a sub-minute alert SLO.

## Service documentation

- [AzureRM 4.62.0 namespace](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.62.0/website/docs/r/eventhub_namespace.html.markdown)
- [AzureRM 4.62.0 event hub](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.62.0/website/docs/r/eventhub.html.markdown)
- [Microsoft: private endpoints and trusted services](https://learn.microsoft.com/en-us/azure/event-hubs/private-link-service)
- [HashiCorp: mocked tests](https://developer.hashicorp.com/terraform/language/tests/mocking)
