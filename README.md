# FinanceOps Agent

**Deterministic tools do the math. The agent plans and explains. Humans approve anything that mutates the books.**

AI-powered finance operations system for investigating, reconciling, and explaining accounting issues — with an auditable, human-controlled workflow.

> **Start here:** the full design narrative, architecture, reconciliation algorithm, HITL model, and evaluation results live in **[docs/DESIGN.md](docs/DESIGN.md)**. Customer landing notes: **[docs/CUSTOMER_DEPLOYMENT.md](docs/CUSTOMER_DEPLOYMENT.md)**..

[![Python 3.12](https://img.shields.io/badge/python-3.12-0f6b4c?style=flat-square)](#)
[![Next.js](https://img.shields.io/badge/Next.js-15-0f6b4c?style=flat-square)](#)
[![Eval](https://img.shields.io/badge/recon_precision-0.93-1f7a4c?style=flat-square)](docs/DESIGN.md#13-evaluation-methodology)
[![Safety](https://img.shields.io/badge/mutations-human_approval-a15c07?style=flat-square)](docs/DESIGN.md#11-human-in-the-loop-model)

## Business problem

Controllers and finance ops teams spend hours hunting cash gaps, unreconciled invoices, and unusual journal entries across ERPs, bank feeds, and PDFs. Generic chatbots invent numbers. FinanceOps Agent keeps investigation conversational while forcing **SQL, reconciliation scoring, variance math, and anomaly rules** through auditable tools.

Example questions it handles on the included synthetic ledger:

- Why does the August bank balance not match the general ledger?
- Which invoices are unreconciled?
- Find suspicious or unusual journal entries.
- Explain the largest month-over-month expense variances.
- Identify transactions that may need manual review.
- Prepare a month-end variance summary.
- Reconcile bank transactions against invoices and ledger entries.

## Quick start (local)

### Backend (FastAPI)

```bash
cd backend
# requires uv: https://docs.astral.sh/uv/
uv sync
uv run python -m app.scripts.seed
# Optional: re-import public datasets (USAspending + SEC + FX)
uv run python -c "from app.core.database import SessionLocal; from app.adapters.persist import import_real_public_data; db=SessionLocal(); print(import_real_public_data(db))"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

API docs: http://127.0.0.1:8765/docs

On first boot the API seeds the synthetic August 2024 close pack **and** imports real public data from `backend/data/real/` (USAspending awards, SEC AAPL/MSFT slim facts, ECB FX rates).

### Frontend (Next.js)

```bash
cd frontend
npm install
# NEXT_PUBLIC_API_URL=http://127.0.0.1:8765/api
npm run dev -- -p 3847 -H 127.0.0.1
```

UI: http://127.0.0.1:3847

Use the sidebar **Acting as** control to switch demo roles (`fo_controller_dev`, `fo_investigator_dev`, `fo_admin_dev`, `fo_viewer_dev`). Set `AUTH_ENABLED=true` on the API to enforce them.

### Docker Compose (Postgres)

```bash
docker compose up --build
```

This starts Postgres 16 + API + web. Override with SQLite by setting `DATABASE_URL=sqlite:////data/financeops.db` on the API service.




## Live demo

Public tunnel (ephemeral while this Cloud Agent session is up):

**https://pill-best-capability-convinced.trycloudflare.com**

1. Open **Imports** → switch Acting as to **Admin** → *Load customer ERP CSVs*
2. Open **Reconciliation** for `2024-09` → bank−ledger gap **$25,665**
3. Open **Investigate** and ask why September cash does not match the bank

For a durable URL, connect this repo to [Render](https://render.com) / [Railway](https://railway.app) using `docker-compose.yml` (Postgres + API + web). Set `NEXT_PUBLIC_API_URL=/api`, `API_PROXY_TARGET=http://api:8765`, `AUTH_ENABLED=true`, and `CORS_ORIGINS` to your web origin. See [docs/CUSTOMER_DEPLOYMENT.md](docs/CUSTOMER_DEPLOYMENT.md).

## Customer ERP / bank CSV integration

First-week FDE path: ingest NetSuite/QBO/bank-style CSVs, reconcile, explain.

```bash
# Load the bundled Meridian Robotics Sep-2024 extract
curl -X POST http://127.0.0.1:8765/api/imports/customer-erp \
  -H "X-API-Key: fo_admin_dev"

# Or upload your own files (name them with vendor / invoice / bank / gl)
curl -X POST http://127.0.0.1:8765/api/imports/csv \
  -H "X-API-Key: fo_admin_dev" \
  -F "files=@bank_transactions.csv" \
  -F "files=@gl_journal.csv"
```

Sample pack: `backend/data/customer_erp/` (known bank−ledger gap **$25,665** for 2024-09).
UI: **Imports** page. Details: [docs/CUSTOMER_DEPLOYMENT.md](docs/CUSTOMER_DEPLOYMENT.md).

## Production-oriented controls

| Control | What shipped |
|---------|----------------|
| Role-based API keys | Investigator / controller / admin / viewer (`AUTH_ENABLED`) |
| Maker–checker | Material amounts require a second, different controller |
| Immutable audit | Hash-chained `audit_logs` with update/delete blocked |
| Postgres path | `DATABASE_URL=postgresql+psycopg://...` + Compose service |
| Real public data | USAspending awards, SEC company facts, Frankfurter FX |
| Fee-tolerant matching | Bank fee / FX noise within `reconcile_fee_tolerance` |
| CI gates | Pytest + eval precision/recall/tool-selection thresholds |

## Real data sources

Bundled under `backend/data/real/`:

- **USAspending.gov** — federal award recipients used as vendors/AP/bank disbursements
- **SEC EDGAR companyfacts** — slim AAPL/MSFT cash, revenue, R&D, SG&A benchmarks
- **Frankfurter/ECB** — USD FX rates for multi-currency demo noise

Import is idempotent via `external_id` / invoice numbers and recorded in `import_batches`.

```
User Request
    ↓
Planner (rules or optional LLM)
    ↓
Select Tools
    ↓
SQL / Financial Logic / Document Search
    ↓
Evidence Aggregation
    ↓
Reasoning (explanation)
    ↓
Verification (ground amounts in evidence)
    ↓
Human Approval if action required
    ↓
Final Response + Audit Trail
```

**Key principle:** the LLM (when enabled) understands and explains; deterministic tools calculate, query, reconcile, and detect anomalies.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module-level detail.

### Stack

| Layer | Choice |
|-------|--------|
| API | Python 3.12, FastAPI, SQLAlchemy |
| Data | SQLite by default (Postgres-ready via `DATABASE_URL`) |
| Agent | Explicit single-path workflow (not a multi-agent swarm) |
| LLM | Optional OpenAI-compatible provider (`LLM_ENABLED=true`) |
| UI | Next.js 15, TypeScript, Tailwind |
| Ops | Docker Compose, structlog JSON, pytest, eval harness |

## Agent tools

| Tool | Purpose |
|------|---------|
| `query_ledger` | Journal line search by account/period/reference |
| `search_transactions` | Bank feed search |
| `retrieve_invoice` | Invoice lookup / unreconciled filter |
| `search_documents` | Policy, memo, invoice document retrieval |
| `calculate_variance` | MoM / budget variance drivers |
| `reconcile_transactions` | Bank ↔ ledger/invoice matching |
| `detect_duplicates` | Duplicate invoice pairs |
| `detect_anomalies` | Rules + z-score anomalies |
| `compare_periods` | Account balance comparison |

## Reconciliation logic

Matches use a weighted score over:

1. **Amount** — exact / near tolerance  
2. **Date** — same day or configurable window  
3. **Reference numbers** — invoice/PO/check IDs  
4. **Fuzzy counterparty** — normalized name similarity  
5. **Direction** — deposits vs cash debits, withdrawals vs credits  

Results are categorized as **matched**, **probable**, **unmatched**, or **needs review**. Unmatched GL cash lines (e.g. outstanding checks) are reported separately.

The August seed includes a constructed **~$82,000 bank − ledger gap** from:

| Component | Amount |
|-----------|--------|
| Deposit in transit (Canyon) | $45,000 |
| Outstanding check (Northwind) | $22,000 |
| Unrecorded Apex receipt | $15,000 |

## Anomaly detection

Interpretable rules first (ML only where it would clearly help — not required for v1):

- Weekend / off-hours postings  
- Unexpected vendors  
- Repeated large rounded amounts  
- Duplicate invoices (same vendor + amount within 7 days)  
- Statistical amount outliers (z-score)  
- Expense spikes (≥50% MoM and ≥$5k)

## Human approval model

Sensitive actions never auto-apply:

- Mark transactions reconciled / approve matches  
- Create adjusting entries / journal proposals  

Lifecycle: `pending → approved|rejected → executed`. Every proposal and decision is written to the audit log.

## Evaluation methodology

Synthetic ground truth lives in `backend/data/ground_truth.json` (generated by the seed).

```bash
cd backend
uv run python -m eval.run_eval
uv run pytest -q
```

Metrics:

| Metric | What it measures |
|--------|------------------|
| Reconciliation precision / recall | Matched bank txns vs known matches |
| Anomaly type recall | Detector coverage of seeded anomaly types |
| Calculation accuracy | Absolute error on bank−ledger gap |
| Tool-selection accuracy | Planner picks expected tools/intent |
| Unsupported-claim rate | Answer $ amounts missing from tool evidence |
| Task-completion rate | Required evidence appears in final answer |
| Latency / cost | Per-workflow ms and estimated LLM $ |

## UI capabilities

- Ask finance questions and inspect tool traces  
- Run and browse reconciliation results  
- Review anomalies  
- Open supporting records/documents  
- Approve or reject proposed actions  
- Inspect the agent audit trail  

## Security best practices (shipped & recommended)

- No secrets required for local demo; LLM key optional via env  
- CORS configurable; approval required before GL mutation  
- Parameterized SQLAlchemy queries (no raw string SQL from the LLM)  
- Audit trail of records accessed and actions proposed  
- For production: authN/Z, Postgres, secret manager, network isolation, PII minimization, rate limits  

## Production considerations

- Swap SQLite for Postgres (`DATABASE_URL`)  
- Enable LLM planner/explainer behind feature flags with prompt/version logging  
- Connect real bank/ERP extracts; keep tool interfaces stable  
- Add OpenTelemetry exporters alongside structlog  
- Separate read replicas for investigative queries  
- Retention policies for audit logs and documents  

## Limitations

- Synthetic dataset covers three months and a focused chart of accounts  
- Fuzzy matching is heuristic; multi-currency and partial payments are out of scope in v1  
- Document search is keyword-based, not embedding RAG  
- Deterministic planner covers the demo question set; unusual phrasings may need the LLM planner  
- “Bank balance” here is reconstructed from period cash movements for the demo gap narrative  

## Project layout

```
backend/          FastAPI app, tools, agent, seed, tests, eval
frontend/         Next.js operations console
docs/             Architecture notes
docker-compose.yml
```

## License

MIT — demo project for auditable AI finance workflows.
