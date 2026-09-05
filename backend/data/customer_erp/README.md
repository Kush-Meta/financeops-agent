# Meridian Robotics — customer ERP extract (demo)

Synthetic **customer-shaped** export pack for a first-week finance-ops
integration. Formats mirror common NetSuite / QuickBooks Online / bank-portal
CSVs, with aliased column names the adapter accepts.

| File | Source system analogue | Maps to |
|------|------------------------|---------|
| `vendors.csv` | Vendor master | vendors |
| `ap_invoices.csv` | AP bills export | invoices |
| `bank_transactions.csv` | Operating-cash bank feed | bank_transactions |
| `gl_journal.csv` | GL journal line export | journal_entries + lines |

Period focus: **2024-09**. Cash account `1000`, AP `2000`, expenses `5xxx`
must already exist (seeded chart of accounts).

## Known breaks after import + reconcile (`2024-09`)

| Break | Amount | Why it shows up |
|-------|--------|-----------------|
| Deposit in transit | +$18,500 | Riverland OEM on bank feed, not booked to GL cash |
| Outstanding check 4488 | +$7,200 | GL cleared AP/cash; check not yet on bank statement |
| Unrecorded wire fee | −$35 | Bank fee only |
| **Bank − ledger gap** | **$25,665** | 18500 − 35 + 7200 |

## How to load

```bash
# Bundled Meridian Robotics pack
curl -X POST http://127.0.0.1:8765/api/imports/customer-erp \
  -H "X-API-Key: fo_admin_dev"

# Or upload your own CSVs (filenames should contain vendor/invoice/bank/gl)
curl -X POST http://127.0.0.1:8765/api/imports/csv \
  -H "X-API-Key: fo_admin_dev" \
  -F "files=@bank_transactions.csv" \
  -F "files=@gl_journal.csv"
```

Then reconcile period `2024-09` in the UI or via `POST /api/reconcile`.
