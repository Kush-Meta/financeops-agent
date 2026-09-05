# Sources & methodology — Aether 2018-Q3

## Honest framing

This pack is a **reconstructed illustration**. Journal amounts and the Aether Dynamics entity are synthetic. The *shape* of the breaks deliberately mirrors issues the SEC has charged for decades: cash that never cleared a bank, period-end cut-off, and ignored bank fees/charges.

We cite public sources so a recruiter or diligence reader can verify the methodology — not so we can claim insider data.

## Primary references

1. [SEC Accounting and Auditing Enforcement Releases](https://www.sec.gov/enforce/accounting-and-auditing-enforcement-releases) — pattern library for cash cut-off and improper cash reporting.
2. [USAspending.gov](https://www.usaspending.gov/) — public federal award recipients (Dell Federal Systems L.P.; Regents of the University of California) appear as realistic AP counterparties; see bundled `backend/data/raw_usaspending_awards.json`.
3. Product public-data spine already in-repo: SEC companyfacts samples + Frankfurter FX under `backend/data/real/`.

## Reproducibility

```bash
curl -X POST http://127.0.0.1:8765/api/imports/historic-case/aether_2018q3 \
  -H "X-API-Key: fo_admin_dev"
curl -X POST http://127.0.0.1:8765/api/reconcile \
  -H "X-API-Key: fo_controller_dev" -H "Content-Type: application/json" \
  -d '{"period":"2018-09","persist":true}'
uv run python -m eval.run_case_eval
```
