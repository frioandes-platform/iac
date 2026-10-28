# Estimation inputs only — do not deploy

These public synthetic tfvars are explicitly selected by `infracost.yml`.
The zero subscription UUID, sample Entra identities, security test tokens and
`estimate-only` namespace are not Azure subscription or deployment configuration.
The DNS/VNet IDs illustrate references between the existing connectivity and
dev roots; they do not prove that those resources exist.

No file here is auto-loaded by the Terraform deployment roots. Ingestion and
its shared DNS remain disabled by default. See the scenarios, commands and
limitations in [the cost guide](../../docs/pipeline/static-analysis-and-costs.md).
