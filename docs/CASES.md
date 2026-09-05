# Retrospective case packs — proof that the system works on history-shaped problems

FinanceOps Agent is not a chat wrapper. These packs exist to **sell the control thesis with receipts**:

> Deterministic tools reconcile the cash. The agent explains with citations. Humans approve mutations. Eval gates keep us honest.

## Featured case: Aether Dynamics — Q3 2018 cash cut-off

**Would a tool-grounded agent have surfaced the cash that was not there?**

| | |
|---|---|
| **Period** | `2018-09` |
| **Expected bank − ledger** | **−$2,440,035** |
| **Pack** | `backend/data/cases/aether_2018q3/` |
| **Load** | Imports → *Load historic retrospective* · or `POST /api/imports/historic-case/aether_2018q3` |
| **Eval** | `cd backend && uv run python -m eval.run_case_eval` |

### What the pack contains

Reconstructed September 2018 operating activity (matched AP/AR cash) **plus three labeled breaks**:

| Break | Amount | Evidence side | Theme (public SEC pattern) |
|------|--------|---------------|----------------------------|
| Phantom affiliate / “cash in transit” | +$2,100,000 on books | GL only | Cash reported that never cleared a controlled bank account |
| Period-end collection cut-off | +$340,000 on books | GL only | Collection booked 2018-09-30; bank wire 2018-10-02 |
| Unrecorded wire fee | −$35 on bank | Bank only | Bank-only evidence retained |

### Honest methodology (read this before you tweet)

- **Amounts and the Aether entity are synthetic.** This is not a dump of any issuer’s confidential GL.
- Break *patterns* mirror themes repeatedly documented in [SEC Accounting & Auditing Enforcement Releases](https://www.sec.gov/enforce/accounting-and-auditing-enforcement-releases) on cash cut-off and improper cash reporting.
- Vendor names such as Dell Federal Systems L.P. and Regents of the University of California appear in **public** [USAspending](https://www.usaspending.gov/) data bundled with this repo — used as realistic counterparty color, **not** as allegations about those recipients.
- We claim: *the agent + recon tools recover the labeled breaks and the gap within $1.*  
  We do **not** claim: *this product would have prevented a specific historical fraud.*

### Demo script (90 seconds)

1. **Imports** → switch Acting as **Admin** → **Load historic retrospective**
2. **Reconciliation** → period **2018-09** → confirm bank−ledger ≈ **−$2,440,035**
3. **Investigate** → *Why is September 2018 cash overstated versus the bank?*
4. Open the imported **case brief** document for the controller narrative

### Eval gate

```bash
cd backend
uv run python -m eval.run_case_eval
# writes eval/case_eval_report.json ; exits 1 on failure
```

Gates today:

- Gap within $1 of −2,440,035  
- All three labeled breaks detected (GL-only phantom + cut-off; bank-only fee)  
- At least four matched operating items (system is not “unmatch everything”)

---

## Why this belongs in an FDE portfolio

Forward-deployed work is judged on **landing trust under constraints**, not model cleverness.

This pack shows you can:

1. Turn messy public themes into a **customer-shaped CSV ingress**
2. Keep math in **tools** with a **known gap**
3. Ship an **eval** someone else can re-run
4. Write the **disclaimer** that diligence readers look for

Next cases (same folder contract): add `backend/data/cases/<id>/` with the same CSV layout + `ground_truth.json`, then it appears automatically on `GET /api/imports/historic-cases`.
