# Threat model & production posture — FinanceOps Agent

Audience: diligence readers, controllers, and FDE interviewers.

## What we optimize for

FinanceOps keeps **money math out of the LLM**. Threats are therefore less about “model hallucination invents a JE” (the verifier + tools already constrain that) and more about **who can mutate books, who can see which tenant, and whether sync jobs can be spoofed**.

## Trust boundaries

| Boundary | Trust | Controls today | Production next step |
|----------|-------|----------------|----------------------|
| Browser → API | Low | Demo API keys / optional Clerk Bearer hook (`AUTH_PROVIDER`) | SSO (OIDC) + short-lived tokens |
| Tenant A vs B | Medium (demo) | `X-Org-Id` scopes connector sync cursors & receipts | Row-level `org_id` on all finance tables + RLS |
| Connector → bank/ERP | Medium | Sandbox feed with cursor receipts | mTLS / OAuth to Plaid/QBO; secret manager |
| Agent → ledger writes | High bar | Approvals + maker–checker for material amounts | Same + dual control on mapping changes |
| Audit log | High | Hash-chained append-only application rules | WORM storage / SIEM export |

## What we refuse to auto-post

Even with a perfect recon score, FinanceOps **does not** post adjusting entries without an approval record. Material amounts require a second, different controller when maker–checker is enabled.

## Spoofing & injection

- **Prompt injection** that asks to “approve everything” still hits the approval service gates.
- **CSV upload** is admin-scoped; parsers ignore unknown columns rather than executing content.
- **Clerk mode without JWKS** fails closed when `AUTH_ENABLED=true`.

## Cutover checklist (from demo → customer)

1. `AUTH_ENABLED=true`, `AUTH_PROVIDER=clerk` (or enterprise IdP), remove demo keys from prod.
2. Provision real `org_id`s; stop accepting free-form `X-Org-Id` from browsers — derive from token claims.
3. Replace `sandbox_bank_feed` with Plaid/QBO credentials in a secret manager; keep `ConnectorSyncRun` receipts.
4. Postgres + backups; disable SQLite.
5. CI must stay green: recon eval + **historic case eval** (`python -m eval.run_case_eval`).
6. Customer signs off on the exception queue workflow before enabling any auto-propose of JEs.

## Residual risks (acknowledge, don’t hand-wave)

- Demo tenancy is **header-based**, not cryptographic isolation.
- Sandbox JWT path without signature verification is for wiring tests only — never enable with `AUTH_ENABLED=true` without real JWKS verification (add PyJWT/jose in the customer fork).
- Public retrospective cases prove **control patterns**, not that any specific historical fraud would have been prevented.
