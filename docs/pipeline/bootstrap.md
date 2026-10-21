# Bootstrap and activation runbook

The workflow cannot create the resources or trust it needs to authenticate.
Perform this once with the approved platform administration process. No bootstrap
identity, password, subscription identifier or client-approved campaign calendar
has been invented in this delivery. Keep cloud promotion disabled until complete.

## 1. GitHub controls

In `frioandes-platform/iac`, create Environments **dev**, **test**, **prod**.
For each, select **Selected branches and tags**, add a **branch** named exactly
`main`, and no tag or wildcard rule. For prod:

- Add real independent required reviewers (a maintained operations/security team).
- Enable **Prevent self-review**.
- Disable **Allow administrators to bypass configured protection rules**.
- Verify the GitHub plan supports required reviewers for this repository's
  visibility. If it does not, do not replace approval with a workflow input.

Protect main with required PR review, the `validate` check, and reviews by the
actual owners of workflows, pipeline scripts, deployment config and IaC. Configure
CODEOWNERS with real existing teams; this delivery does not fabricate a team.
Disallow direct pushes and protection bypass for normal deployment operators.

The preflight and apply driver read the Environment REST API and check reviewers,
self-review prevention and branch policies. The documented API response does not
expose the administrator-bypass toggle; an administrator must verify its disabled
setting in the UI and record that check in the activation review. Confirm the Actions token can read them; failure is blocking. Production
protection must be set in GitHub, not merely described in YAML or a README.

## 2. Storage, vaults and networking

Provision a dedicated bootstrap/platform resource group outside the resource
groups managed by these application Terraform roots. Enable the approved regions,
tags, budgets, diagnostic destinations and resource-provider registrations from
#5/#7/#8/#9. Do not give workflow identities control over their own trust or roles.

Provide:

| Resource | Contract |
| --- | --- |
| State storage | Private Azure Blob endpoints; shared-key authentication disabled; public blob access disabled; soft delete/versioning; four separate containers: state-dev, state-test, state-prod, state-connectivity |
| State keys | dev.tfstate, test.tfstate, prod.tfstate, connectivity.tfstate |
| Plan storage | Private endpoints; no public blob access or shared keys; containers plans-dev, plans-test, plans-prod; access per stage; lifecycle deletion after 7 days |
| Key Vaults | One per dev/test/prod, private endpoints, Azure RBAC, soft delete and purge protection, auditing |
| ACR | Approved registry with administrator account disabled; private access for cloud jobs; image repository frioandes/release-probe |
| Runners | Disposable Linux x64 runners with approved private DNS/routes to their vault, storage, ACR and Azure/GitHub control planes |

Use the established hub/spoke and DNS design. **Do not** turn on public access to
Key Vault or state storage to make a hosted runner connect. Network and DNS paths,
peering and bootstrap resources are prerequisites, not resources created by #20
or magically supplied by a backend block. Any required firewall/NSG change must
first be reviewed in the #9 source table and then reflected through #21.
Do not give runners access to the dispatch application as a shortcut.

The shared firewall may affect its own runner's egress. Verify a bootstrap
management path and recovery procedure before changing shared connectivity.
Private runners must be ephemeral and isolated from the corporate dispatch network.
Use runner groups restricted to the trusted release workflows on main; PRs run
only on GitHub-hosted runners without cloud credentials. Where the GitHub plan
cannot enforce workflow restrictions, establish an equivalent approved isolation
control before enabling these runner groups for this repository.

Runner labels:

- Build: `self-hosted`, `linux`, `x64`, `fa-build`.
- Plan: the same base labels plus `fa-plan` and `fa-dev`, `fa-test` or `fa-prod`.
- Apply: base labels plus `fa-dev`, `fa-test` or `fa-prod` as appropriate.
- The prod pool needs access to both prod and the connectivity subscription's
  approved private endpoints. Plan/apply identities remain separate even if
  runner labels select the same freshly provisioned pool.

Install Python >=3.10 with timezone data, Azure CLI supporting federated-token
login, Git, curl, tar and Docker on the private runner image. The workflows install
pinned Terraform and, for the build job, Go. Outbound routes must allow the
approved tool downloads. Review and patch the runner image; retain its version
with live validation evidence. Destroy disks, Docker cache and temporary credential
material after each job, including cancellation and runner failure.

## 3. Entra OIDC identities and RBAC

Create seven distinct identities. Federated trust uses issuer
`https://token.actions.githubusercontent.com` and audience
`api://AzureADTokenExchange`. Do not create client secrets.

| Identity | Exact default GitHub subject | Minimum responsibility |
| --- | --- | --- |
| Build | repo:frioandes-platform/iac:ref:refs/heads/main | Push/pull the demonstration repository in ACR; no Terraform apply or Key Vault write |
| Plan dev/test/prod (one each) | repo:frioandes-platform/iac:ref:refs/heads/main | Read its infrastructure and approved input secrets; backend locking/read and upload its private plans |
| Apply dev | repo:frioandes-platform/iac:environment:dev | Manage the approved dev resource group and state; read dev plans; pull the image |
| Apply test | repo:frioandes-platform/iac:environment:test | Same, scoped to test |
| Apply prod | repo:frioandes-platform/iac:environment:prod | Approved prod and shared connectivity groups/states; read prod plans/control; pull the image |

If the organization customizes OIDC subjects, explicitly configure the equivalent
subjects in Entra and review the change; the table above assumes GitHub defaults.
Separate plan identities share a subject but have distinct scoped Azure roles.
Main branch/workflow review is therefore a trust boundary, not merely convention.

Typical RBAC building blocks are Azure Reader for plans, scoped Contributor for
apply, Storage Blob Data Contributor for state leasing/update and plan upload,
Storage Blob Data Reader for apply-plan download, Key Vault Secrets User for
approved secret reads, and the registry's appropriate pull/push roles. For ACR
ABAC-enabled registries, use repository-scoped roles/conditions instead of assuming
legacy AcrPush/AcrPull grants are sufficient. Review exact actions with #7.
Backend data access is sensitive even for plan identities; do not grant them broad
storage management, account-key access, Owner or User Access Administrator.

Existing roots create their resource groups. Prefer bootstrap-created groups
with tightly scoped apply roles, then import those groups into the correct remote
states before the first automated plan. Otherwise document an explicitly approved
initial group-creation permission; do not silently give subscription-wide
Contributor to every pipeline. Never let two states own the same resource group.

If #22 enables Event Hub role assignments, ordinary Contributor cannot create
Azure role assignments. Supply the approved constrained authorization for only
those Event Hubs data roles/scopes, or bootstrap their assignments through the
approved ownership model. Do not solve this with unrestricted Owner.

The operational-control publisher is a **separate** identity. No build/plan/apply
identity can write that secret, change its access policy, grant itself privileges,
or alter GitHub Environment rules. Route Key Vault and deployment auditing to the
existing security workspace from #6/#7; this workflow does not provision that sink.

## 4. Key Vault input contract

Create these JSON-valued secrets with approved inputs, not the fictitious test
fixture `tests/fixtures/security-tokens.json`:

| Vault | Secret | Contents |
| --- | --- | --- |
| dev | terraform-dev | Variables for environments/dev |
| test | terraform-test | Variables for environments/test |
| prod | terraform-prod | Variables for environments/prod |
| prod | terraform-connectivity | Variables for the shared root; protected_environments must be ["dev", "test", "prod"] |
| prod | production-change-control | Current operational control and independently authorized incidents |

Use the roots' documented variables. Supply real approved `security_token_values`
and deliberately selected migration IDs/change references if needed. Keep
credentials out of Terraform input variables when managed identities can be used.
Never include a state storage account key, client secret or SAS in these inputs.
The binary plan pins input values and the manifest records the Key Vault version.

For #22, keep its existing opt-in and cross-root DNS activation procedure. This
pipeline does not guess a DNS zone ID, sender/receiver identity, or enable ingest
in test/prod without the corresponding root integration. If DNS must exist before
the first enabled ingest plan, finish that approved bootstrap first. The optional
module's development integration does not imply three deployed telemetry stacks.

`operational-control.example.json` is intentionally expired and frozen. Replace
it with client-approved current data before publishing to Key Vault. Fields:

- `campaign_active`: required Boolean, including emergency campaign extensions.
- `campaign_windows`: required list of `{ "start": "...timezone...", "end": "...timezone..." }`
  covering the confirmed upcoming campaigns. Empty is an explicit operator
  statement that none is scheduled in the control's validity horizon.
- `issued_at` and `valid_until`: timezone-aware times, maximum 24-hour span;
  publish again before expiry and whenever campaign status changes.
- `incidents`: independently authorized, short-lived exception entries.

An incident entry has this shape; replace every example value and publish it
through the incident commander's approved process:

```json
{
  "id": "INC-123",
  "status": "declared",
  "repository": "frioandes-platform/iac",
  "environment": "prod",
  "sha": "EXACT_40_CHARACTER_COMMIT_SHA",
  "run_id": "ACTUAL_ACTIONS_RUN_ID",
  "run_attempt": "ACTUAL_ATTEMPT_NUMBER",
  "approved_by": "ACTUAL_INCIDENT_COMMANDER",
  "record_url": "https://github.com/frioandes-platform/planning/issues/ACTUAL_ISSUE_NUMBER",
  "valid_from": "CURRENT_TIME_WITH_TIMEZONE",
  "valid_until": "SHORT_EXPIRY_WITH_TIMEZONE"
}
```

The control and incident validity must extend beyond the 30-minute change budget.
The ID alone cannot authorize a deployment. It bypasses only dispatch/campaign
restrictions, never test promotion, saved-plan integrity or GitHub approval.

## 5. Enable and demonstrate

1. Populate `.github/deployment-config.json` with real **non-secret** IDs/names.
   Confirm each root's subscription, per-root state and per-stage plan container.
2. Verify runner connectivity, state imports, least-privilege permissions and
   GitHub Environment settings. Confirm resource operations fit the allowed
   execution budget in test.
3. Review the config PR and set `enabled` to `true` only when deploying dev/test
   automatically is intended. The merge to main will start a real release and
   can create billable Azure resources.
4. Run once during an approved window without campaign. Confirm actual OIDC
   authentication, Key Vault reads, ACR push/digest, authenticated plans,
   dev/test applies, paused prod approval, saved-plan review and prod applies.
5. Exercise denied dispatch and campaign cases; verify **no prod or connectivity
   apply starts**. Use a disposable reference deployment or no-change release.
6. Exercise an authorized incident, wrong incident/run/attempt, stale controls,
   stale plans, failed test and failed Environment protection checks.
7. Record run URLs, commit SHA, image digest, reviewer, applied plan checksums,
   input/control versions and outcomes in `validation.md`. Never attach secret
   values, state or binary plans to the PR.

The delivered code has local test evidence only. Do not mark these live steps
complete until the corresponding GitHub/Azure evidence exists.
