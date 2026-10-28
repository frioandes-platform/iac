# GitHub Actions promotion pipeline (#23)

This implementation promotes one reviewed Git commit and one immutable container
image through **dev → test → prod**. It uses the existing Terraform roots from
#20/#21, and automatically includes #22 checks when that module is merged.
It does not change the approved address plan, firewall table, provider locks,
network outputs or security rules.

Cloud deployment is **disabled by default** in `.github/deployment-config.json`.
The subscription, OIDC identities, remote-state storage, private runners, Key
Vaults and protected GitHub Environments must be bootstrapped first. This is an
explicit initial state, not evidence that a deployment has run.

## Files and execution

| File | Responsibility |
| --- | --- |
| `.github/workflows/validate.yml` | Pull-request and main validation; no Azure login; mocked module tests; local container build/self-test |
| `.github/workflows/promote.yml` | Main-only release, serialized across all environments; build/push, ordered plans and applies |
| `.github/workflows/terraform-stage.yml` | Reusable plan and protected apply jobs; no independent manual or push trigger |
| `.github/deployment-config.json` | Reviewed, non-secret identifiers and state locations; disabled until configured |
| `scripts/pipeline/run.py` | OIDC, Key Vault reads, saved plans, independent policy comparisons, apply and receipts |
| `scripts/pipeline/policy.py` | Promotion, approval-configuration, plan-integrity, campaign and time-window checks |
| `environments/*/backend.tf` | Partial Azure Blob backend configuration, one state per root |
| `tests/pipeline/` | Boundary, rejection, workflow graph and driver-order tests |
| `containers/release-probe/` | Minimal non-root demonstration image; no business application or credentials |

A push to `main` runs steps 1 to 5 and stops after test. Production (steps 6 and
7) runs only from a manual run **on main** (`workflow_dispatch`), started inside
the change window: after 22:00 and early enough to finish before 03:00 (see the
gate below). A daytime merge must not plan prod, because the saved plan would be
older than six hours when the window opens and would be rejected. The manual run
repeats dev and test for the same commit, so the receipts stay in one run:

1. Validate #20/#21 and, when present, #22. Check pipeline policy and YAML.
2. Verify bootstrap configuration and the existing GitHub Environments.
3. Build and self-test the demonstration container, push it to ACR through OIDC,
   and retain its digest. Never rebuild the image during promotion.
4. Automatically plan dev. Apply the saved plan inside Environment `dev`, using
   a different Azure identity. Pull and self-test the selected image; check
   post-apply drift. Produce a successful dev receipt.
5. Repeat for test, requiring the dev receipt for the same commit, image,
   workflow run and attempt.
6. Automatically plan **connectivity and prod** after test succeeds. Review
   those saved plans before approving the production job.
7. Wait for the required reviewers of Environment `prod`. Then verify the
   protections again and check current operational controls immediately before
   **each** apply: first connectivity, then prod. Both roots count as production
   changes because the shared firewall can affect production.

A failed dependency stops downstream jobs. There is no target-environment input
or standalone deployment workflow that skips test. An incident does not change
this ordering or remove manual approval.

## What the container demonstrates

The build context contains only the Dockerfile and a statically compiled Go
binary. The image uses `scratch`, runs as UID/GID 65532 and has no embedded
secrets. `/healthz` reports the source revision; `--self-test` checks its release
metadata. The same ACR digest is pulled and self-tested at every environment.
The runtime uses Go 1.27.3, Terraform 1.9.8 and the existing AzureRM 4.62.0 locks.
Actions are pinned to full commit SHAs.

This is a **pipeline demonstration image**, not the logistics application or the
telemetry alert processor. #22 selected an Event Hubs ingestion component; it
has no container image input. Therefore this PR builds/pushes/promotes an image
and applies infrastructure, but does **not** deploy a fictitious Container App
or claim application end-to-end testing. A future compute module must consume
the promoted digest as a Terraform input, with its application tests added before
the next environment. Any production application update must stay in the same
protected, gated execution path; do not add a separate `az ... update` workflow.

## Authentication and secrets

See [bootstrap.md](bootstrap.md) for the concrete configuration contract.

- Build, plan-dev/test/prod and apply-dev/test/prod use seven distinct Entra
  applications or user-assigned identities, with GitHub OIDC federated trust.
- Plan jobs have read-only permissions on the managed Azure infrastructure.
  Backend leasing and private plan storage need narrowly scoped data-plane
  permissions; those permissions are not permission to deploy resources.
- Apply identities use GitHub Environment subjects. Production cannot receive
  its job token until the protected environment allows the job to start.
- The driver requests a short-lived GitHub OIDC token and exchanges it with
  `az login --service-principal --federated-token`. Terraform uses OIDC too.
  No Azure client secret, account key, SAS or ACR administrator password is used.
- Terraform input JSON comes from the corresponding Key Vault. Production also
  reads the current operational-control secret. Complete secret payloads and authentication tokens are masked; raw
  CLI/provider output is withheld because it can contain inputs. Public release
  identifiers are not masked individually, so GitHub can pass promotion receipts.
- Temporary inputs, Azure/Docker credentials and plans live in a private runner
  temporary directory. Ephemeral runners are destroyed after every job, including
  cancellation. They are never reused for pull-request code.

GitHub's automatically issued `GITHUB_TOKEN` reads the main ref and Environment
settings. `actions: read` is declared for that inspection. A 403, malformed required field,
missing Environment, absent reviewer or overly broad branch policy stops the
release; the script never creates an unprotected Environment as a fallback.
The public REST schema does not expose the administrator-bypass toggle. Its
required disabled setting is confirmed separately in the GitHub UI during
bootstrap; the workflow does not claim to verify an undocumented API field.

## Remote state, saved plans and review

Each root has a separate state container and key. Storage uses Entra data-plane
authentication, Azure encryption at rest, private connectivity, versioning and
soft delete. Backend locking protects concurrent changes to each state.
The entire release is also serialized with `cancel-in-progress: false`.

Saved binary plans may contain secrets. They are stored in a **private Azure
Blob container per stage**, not uploaded as GitHub artifacts or committed.
The manifest binds each plan to its source commit, workflow run/attempt, image
digest, environment/root, configuration checksum and provider-lock checksum.
The apply job verifies the plan checksum, reuses that exact saved plan, and
rejects plans older than six hours. Terraform additionally rejects stale state.

The GitHub summary lists resource addresses/actions and the private review
location. Authorized reviewers can download the binary plan with their Entra
identity and inspect it with `terraform show` on an approved private workstation.
Do not publish that output in PR comments or Actions logs. Review both connectivity
and prod plans before approving. Runtime CLI diagnostics are deliberately not
printed; an authorized operator reproduces a failed operation privately.

An apply is followed by a read-only refresh-only plan using the saved input
values. Drift or failure prevents a successful promotion receipt. Neither this
check nor the image metadata self-test proves live application availability.

A newer `main` commit invalidates an older queued deployment. Rerun the **entire
workflow**, not only a failed job: receipts are bound to the run attempt.
If approval takes more than six hours, make fresh plans through a full run.
Two production roots are not an atomic transaction: connectivity can succeed
before prod is blocked or fails. Inspect state and plan a new complete release;
never pretend the first apply was rolled back.

## Dispatch and campaign gate

The authoritative timezone is **America/Bogota**, not the runner's UTC clock.
Normal production changes are forbidden from **04:00 inclusive to 22:00
exclusive**, and throughout campaign. The gate runs after approval and immediately
before each shared or production apply, using a newly fetched Key Vault version.

Operational control must explicitly report `campaign_active`, include the
confirmed `campaign_windows` calendar, and be valid now and for the full change
budget. Missing, malformed, future-dated, expired or unknown controls block the
release. A control version may span at most 24 hours. Operations must refresh it
and keep the campaign calendar authoritative; the speculative dates in the
migration design are not silently treated as client-approved campaign dates.

Each apply has a 20-minute process deadline. The gate reserves 30 minutes per
pending root, including margin, before dispatch or any scheduled campaign starts.
Production has two roots, so the gate before connectivity reserves 60 minutes and
the gate before prod reserves 30. The clock alone therefore cannot stop prod after
connectivity was applied; only a newly published freeze or campaign can. Normal
production changes cannot start at or after **03:00**, even though dispatch
starts at 04:00. Approval at 02:00 does not authorize an apply that starts at 04:00.
No sleeping job waits for the next window; a denied release fails for review.

The gate controls admission and execution deadlines; it cannot atomically undo
Azure operations already accepted by a service. A timeout or cancellation can
leave an Azure operation completing asynchronously. Before production enablement,
measure the selected operations in test and confirm they finish within the budget.
A first firewall provisioning or a long migration may not fit: use an approved
separate maintenance design instead of increasing timeouts without review.
An incident is the documented path for an actual operational emergency.

## Declared incidents

1. Open or identify the incident record in `frioandes-platform/planning`.
2. Start the full workflow on main with an ID such as `INC-123`. This input
   requests an exception; it does not authorize one.
3. The incident commander/control publisher, using a separate audited identity,
   adds an authorization to the current operational-control secret. Bind it to
   the repository, exact commit, run ID, run attempt, prod, approver and a short
   validity interval; link the incident issue. See the example in bootstrap.md.
4. Complete dev and test, review the saved production plans, and obtain the
   normal independent GitHub production approval.
5. The gate accepts the exception only when every field matches and the
   authorization remains valid for the complete change budget. Record the
   deployment outcome on the incident and revoke the exception afterward.

Pipeline identities can **read but cannot publish or alter** operational control.
Only the designated incident/control authority may mark a record `declared`.
Key Vault version history and audit logs provide the authorization trail.
The driver treats this independently maintained record as authoritative; it does
not infer approval from a label or text typed by the deployment requester.

## Local checks

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install PyYAML==6.0.3
bash scripts/check-pipeline.sh
terraform fmt -check -recursive
bash scripts/check-security.sh
# Once #22 is present, use this instead of check-security.sh:
# bash scripts/check-ingest.sh
```

`check-pipeline.sh` runs the pipeline and existing Python tests. It also runs
`actionlint` if installed. GitHub CI installs and runs the pinned linter.
`check-security.sh` and `check-ingest.sh` execute mocked Terraform tests; they
still need Terraform and the provider download but no Azure subscription.
The new backend blocks are ignored by their existing `init -backend=false`.

With Go 1.27.3 and Docker installed, the optional local container check is:

```bash
python3 scripts/pipeline/run.py build-local
```

See [validation.md](validation.md) for executed checks and pending live evidence.

## Acceptance mapping

| Criterion | Implementation | External prerequisite / evidence still needed |
| --- | --- | --- |
| Automatic plan and manual approval before prod apply | Main-triggered plans; reusable apply job uses Environment prod; API inspection rejects missing reviewers/self-review and broad branch policies | Configure a real protected Environment, disable admin bypass in the UI and observe approval |
| OIDC, managed secrets and dev→test→prod | Separate federated identities, Key Vault reads, immutable image, DAG dependencies and bound receipts | Entra trust/RBAC, vaults, private state/plan storage and runners |
| Dispatch/campaign gate with incident exception | Fresh control after approval, Bogotá clock, duration margin, bound incident authorization | Confirm operational calendar and control publisher; exercise allowed and denied live runs |

These are code-level controls with automated tests. Completion of the operational
acceptance demonstration requires the bootstrap and the live tests below.

## References

- [Planning #23](https://github.com/frioandes-platform/planning/issues/23),
  [#20](https://github.com/frioandes-platform/planning/issues/20),
  [#21](https://github.com/frioandes-platform/planning/issues/21),
  [#22](https://github.com/frioandes-platform/planning/issues/22).
- Planning: `seguridad-iam-cifrado.md` (#7), `red-acceso-remoto-segunda-nube.md`
  (#11), `carga-c-migracion-y-campana.md` and the unchanged #8/#9 source snapshots.
- [GitHub Environments and deployment protection](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
- [Environment REST inspection](https://docs.github.com/en/rest/deployments/environments).
- [GitHub OIDC subject claims](https://docs.github.com/en/actions/reference/security/oidc).
- [Azure federated identity trust](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust).
- [Key Vault with GitHub OIDC](https://learn.microsoft.com/en-us/azure/developer/github/github-actions-key-vault).
- [Terraform Azure Blob backend and OIDC](https://developer.hashicorp.com/terraform/language/backend/azurerm).
