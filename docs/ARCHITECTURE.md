# Architecture — FinanceOps Agent

## Principle

Use the LLM (optional) to understand requests, plan investigations, and explain findings.
Use deterministic tools for calculations, database queries, reconciliation, and financial logic.

## Components

```
User → Next.js UI → FastAPI → Planner → Tool Executor → Evidence → Reasoner → Verifier
                                              ↓
                                    SQLAlchemy / SQLite|Postgres
                                              ↓
                                    Approval Service (HITL) → Audit Log
```

### Backend (`backend/app`)

| Module | Role |
|--------|------|
| `models/` | Vendors, invoices, journal entries/lines, bank txns, balances, documents, anomalies, approvals, audit, workflows |
| `tools/` | Deterministic tools registered in a registry |
| `agent/planner.py` | Maps request → intent + ordered tool plan (deterministic rules; optional OpenAI) |
| `agent/workflow.py` | Controlled single-path orchestration |
| `agent/reasoner.py` | Evidence-grounded explanation + unsupported-claim verification |
| `services/approvals.py` | Propose / approve / reject / execute sensitive actions |
| `services/audit.py` | Append-only audit events |
| `scripts/seed.py` | Synthetic Aug 2024 dataset with ground truth |

### Frontend (`frontend`)

Operations console: Investigate, Reconciliation, Anomalies, Approvals, Audit trail, Records.

## Agent workflow

1. **User request** recorded in `workflow_runs` + audit
2. **Planner** selects tools (not an unconstrained multi-agent swarm)
3. **Tools** run with retries-friendly pure functions; results + record IDs logged
4. **Evidence aggregation** collects calculations and records accessed
5. **Reasoning** produces markdown explanation
6. **Verification** checks dollar amounts against tool evidence
7. **Human approval** if action proposed (mark reconciled / JE adjustment)
8. **Final response** + complete audit trail

## Reconciliation logic

Score candidates on:

- amount tolerance (exact / near)
- date window
- reference match
- fuzzy counterparty name (`SequenceMatcher`)
- cash direction alignment

Categories: `matched` | `probable` | `needs_review` | `unmatched` (+ `unmatched_gl`).

## Anomaly detection

Interpretable rules first:

- weekend / off-hours entries
- unusual / unknown vendors
- large rounded amounts
- duplicate invoices (vendor+amount within 7 days)
- z-score amount outliers
- MoM expense spikes ≥ 50% and ≥ $5k

## Human approval model

Actions in `SENSITIVE_ACTIONS` never auto-execute. Status lifecycle:

`pending → approved|rejected → executed|failed`

## Observability

- structlog JSON logs
- per-event `audit_logs` with duration_ms
- workflow latency and estimated LLM cost

## Evaluation

`python -m eval.run_eval` measures reconciliation precision/recall, anomaly type recall,
calculation accuracy (bank gap), tool-selection accuracy, unsupported-claim rate,
task-completion rate, latency, and cost against `data/ground_truth.json`.
