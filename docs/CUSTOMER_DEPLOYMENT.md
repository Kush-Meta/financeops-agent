# Customer deployment writeup — FinanceOps Agent

This note is written the way an FDE would debrief after a first customer
landing: what constrained the build, what we traded off, and what we would
harden before a production cutover.

## Scenario

**Customer:** Meridian Robotics (demo stand-in for a mid-market manufacturer)  
**Pain:** Month-end cash reconciliation burns 1–2 controller days; AI chat tools invent amounts.  
**Ask:** Stand up an investigation console that can ingest ERP/bank exports, explain the cash gap with evidence, and require human approval before any adjusting entry posts.

## Constraints (week-one reality)

1. **No ERP write access on day one.** NetSuite/QBO sandboxes lag procurement. We had to win trust with *read* exports first.
2. **Controllers will not accept LLM arithmetic.** Every dollar in an answer must trace to SQL / recon scoring / variance math.
3. **Mutations are political.** Even a correct JE needs maker–checker for material amounts.
4. **Messy CSVs beat clean APIs.** Column names differ by subsidiary (`FITID` vs `external_id`, `account_code` vs `Account`).
5. **Eval before demos.** If recon precision regresses, we do not ship the narrative layer.

## What we shipped for the landing

| Capability | Implementation | Why this shape |
|------------|----------------|----------------|
| ERP/bank ingress | `adapters/csv_erp.py` + `POST /imports/customer-erp` / `/imports/csv` | Alias-tolerant CSV parsers land without a custom connector |
| Seeded close pack | Synthetic Aug-2024 + Meridian Sep-2024 extract | Labeled gaps for demos and eval |
| Investigation workflow | plan → tools → evidence → explain → verify → approve | Controlled path, not an agent swarm |
| HITL | Approval queue + maker–checker threshold | Matches how controllers already work |
| Audit | Hash-chained audit log | Reconstructibility for SOX-minded buyers |
| Ops console | Next.js UI (Investigate / Recon / Imports / Approvals) | FDEs can walk the story live |

## Tradeoffs

- **CSV before native connectors.** Faster time-to-first-value; accepts that refresh is manual until SFTP/API lands.
- **SQLite default, Postgres path.** Demo portability vs multi-user durability — Compose ships Postgres for anything shared.
- **Demo API keys, not SSO.** Enough to show RBAC; not enough for a real tenant.
- **Rules planner with optional LLM.** Determinism first; LLM narrates only after tools return evidence.
- **Fee-tolerant matching vs perfect precision.** Real banks have noise; we measure precision/recall so tolerance is explicit.

## Demo script (10 minutes)

1. Open **Imports** → load Meridian Robotics ERP pack.
2. Run **Reconciliation** for `2024-09` → show bank−ledger gap **$25,665**.
3. **Investigate**: “Why doesn’t September cash match the bank?” → tool-cited deposit in transit, outstanding check, fee.
4. Propose an adjusting entry → lands in **Approvals** (maker–checker if above threshold).
5. Show **Audit trail** hash chain for the workflow.

## What we’d harden next (production cutover)

1. **Identity:** OIDC/SAML, SCIM groups → roles; kill demo keys.
2. **Connectors:** SFTP drop + NetSuite saved search / QBO CDC; webhook for bank feeds.
3. **Tenancy:** org_id on every row; encrypted-at-rest secrets; per-tenant data dirs.
4. **Controls:** dual-control for mapping changes; immutable export of audit packs; retention policy.
5. **Reliability:** managed Postgres, backups, rate limits, structured SLOs on recon jobs.
6. **Eval gate in CI against customer-labeled fixtures** (anonymized), not only the synthetic pack.

## Success criteria for “landed”

- Controller can reproduce the cash gap from Imports → Recon without engineering help.
- Every dollar in the agent answer cites a bank line, JE line, or document.
- No GL mutation occurs without an approval record in the audit chain.
- Recon precision on the labeled pack stays above the CI gate.

