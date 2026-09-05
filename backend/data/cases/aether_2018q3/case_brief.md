# Controller brief — Aether Dynamics Q3 2018 cash cut-off

**Status:** Retrospective reconstruction (demo)  
**Period:** 2018-09  
**Question the board asked in 2018:** *Why does book cash look fine when the bank says otherwise?*

## What a tool-grounded agent should surface

1. **Phantom affiliate cash — $2,100,000**  
   JE `AE-PHANTOM-EU` debits Operating Cash and credits Product Revenue for a "Wire from Aether EU treasury — cash in transit." It never appears on the controlled operating-bank feed.

2. **Period-end cut-off — $340,000**  
   Collection for Eastbay `PO-441` is booked to cash on 2018-09-30. The matching bank wire posts **2018-10-02** — after the close. Classic cut-off window dressing.

3. **Unrecorded wire fee — $35**  
   International wire fee on the bank statement only. Small, but it proves bank-only evidence is not dropped.

**Expected bank − ledger gap for 2018-09:** **−$2,440,035**

## What this is / is not

- **Is:** A labeled proof that FinanceOps Agent can reconstruct a close pack from public enforcement *themes*, run deterministic recon, and explain breaks with citations.
- **Is not:** A claim that this software would have "prevented" any specific historical fraud, or a dump of any issuer's confidential GL.

See `SOURCES.md` and `docs/CASES.md`.
