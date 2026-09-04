"""Seed synthetic finance data with known ground-truth reconciliation and anomalies."""

from __future__ import annotations

import json
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, get_settings
from app.core.database import Base, SessionLocal, engine, init_db
from app.models import (
    Account,
    AccountBalance,
    AnomalyFlag,
    BankTransaction,
    Customer,
    Document,
    Invoice,
    JournalEntry,
    JournalLine,
    Vendor,
)

RNG = random.Random(42)

VENDORS = [
    ("V-ACME", "Acme Cloud Services", "saas"),
    ("V-NWST", "Northwind Steel", "cogs"),
    ("V-GLOB", "Global Freight Co", "logistics"),
    ("V-BRGT", "BrightOffice Supplies", "opex"),
    ("V-CYBR", "CyberShield Inc", "security"),
    ("V-PAYR", "PayRight Payroll", "payroll"),
    ("V-UTIL", "Metro Utilities", "utilities"),
    ("V-LEAS", "Harbor Property Lease", "facilities"),
    ("V-ADVT", "Summit Advertising", "marketing"),
    ("V-CONS", "Delta Consulting LLC", "professional"),
    ("V-UNKN", "Midnight Wire Transfers LLC", "unknown"),  # suspicious vendor
]

CUSTOMERS = [
    ("C-APEX", "Apex Retail Group", "enterprise"),
    ("C-BLUE", "BlueHarbor Hospitals", "healthcare"),
    ("C-CANY", "Canyon Software", "technology"),
    ("C-DRFT", "Driftwood Hotels", "hospitality"),
    ("C-EAST", "Eastbay Manufacturing", "industrial"),
]

COA = [
    ("1000", "Operating Cash", "asset", True),
    ("1100", "Accounts Receivable", "asset", False),
    ("1200", "Prepaid Expenses", "asset", False),
    ("2000", "Accounts Payable", "liability", False),
    ("2100", "Accrued Expenses", "liability", False),
    ("3000", "Retained Earnings", "equity", False),
    ("4000", "Product Revenue", "revenue", False),
    ("4100", "Service Revenue", "revenue", False),
    ("5000", "Cost of Goods Sold", "expense", False),
    ("5100", "Cloud Infrastructure", "expense", False),
    ("5200", "Payroll Expense", "expense", False),
    ("5300", "Facilities & Lease", "expense", False),
    ("5400", "Marketing", "expense", False),
    ("5500", "Professional Services", "expense", False),
    ("5600", "Utilities", "expense", False),
    ("5700", "Office Supplies", "expense", False),
    ("5800", "Security & Compliance", "expense", False),
    ("5900", "Logistics & Freight", "expense", False),
]


def _period(d: date) -> str:
    return d.strftime("%Y-%m")


def _write_document(db: Session, **kwargs) -> Document:
    doc = Document(**kwargs)
    db.add(doc)
    db.flush()
    docs_dir = Path(get_settings().documents_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / doc.filename
    path.write_text(doc.content, encoding="utf-8")
    return doc


def clear_and_create_schema() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.drop_all(bind=engine)
    init_db()


def seed(db: Session) -> dict:
    accounts = {}
    for code, name, atype, is_bank in COA:
        acc = Account(account_code=code, name=name, account_type=atype, is_bank=is_bank)
        db.add(acc)
        db.flush()
        accounts[code] = acc

    vendors = {}
    for code, name, cat in VENDORS:
        v = Vendor(vendor_code=code, name=name, category=cat)
        db.add(v)
        db.flush()
        vendors[code] = v

    customers = {}
    for code, name, seg in CUSTOMERS:
        c = Customer(customer_code=code, name=name, segment=seg)
        db.add(c)
        db.flush()
        customers[code] = c

    # Policy document
    _write_document(
        db,
        doc_type="policy",
        title="Month-End Close & Reconciliation Policy",
        filename="policy_month_end_close.md",
        content=(
            "# Month-End Close Policy\n\n"
            "1. Bank reconciliations must be completed within 3 business days of month-end.\n"
            "2. Timing differences under $500 may be classified as timing if cleared within 5 days.\n"
            "3. Journal entries posted on weekends require dual approval.\n"
            "4. Vendor invoices above $50,000 require AP manager review.\n"
            "5. Duplicate invoice numbers or identical amount+vendor+date within 7 days are escalated.\n"
        ),
        related_entity_type="policy",
        related_entity_id="ME-CLOSE",
        tags=["policy", "reconciliation", "controls"],
    )

    start = date(2024, 6, 1)
    periods = ["2024-06", "2024-07", "2024-08"]
    ground_truth = {
        "recon_expected": {"matched": [], "probable": [], "unmatched_bank": [], "needs_review": []},
        "anomaly_ids": [],
        "bank_vs_ledger_gap": {},
    }

    invoices: list[Invoice] = []
    journal_lines_by_ref: dict[str, JournalLine] = {}
    bank_txns: list[BankTransaction] = []

    inv_counter = 1000
    je_counter = 5000
    bank_counter = 7000

    expense_accounts = {
        "saas": "5100",
        "cogs": "5000",
        "logistics": "5900",
        "opex": "5700",
        "security": "5800",
        "payroll": "5200",
        "utilities": "5600",
        "facilities": "5300",
        "marketing": "5400",
        "professional": "5500",
        "unknown": "5500",
    }

    # Baseline recurring AP invoices + payments for each period
    for period in periods:
        year, month = map(int, period.split("-"))
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        recurring = [
            ("V-ACME", 12450.00, "Cloud hosting"),
            ("V-PAYR", 186000.00, "Biweekly payroll funding"),
            ("V-LEAS", 28000.00, "HQ lease"),
            ("V-UTIL", 4100.00, "Electric and water"),
            ("V-CYBR", 8900.00, "Security monitoring"),
            ("V-BRGT", 1250.00, "Office supplies"),
            ("V-GLOB", 15600.00, "Outbound freight"),
            ("V-ADVT", 22000.00 if period != "2024-08" else 48000.00, "Campaign spend"),
            ("V-CONS", 17500.00, "Strategy retainers"),
            ("V-NWST", 33500.00, "Raw materials"),
        ]

        for vendor_code, amount, desc in recurring:
            inv_counter += 1
            inv_date = month_start + timedelta(days=RNG.randint(1, 8))
            due = inv_date + timedelta(days=vendors[vendor_code].payment_terms_days)
            ref = f"INV-{inv_counter}"
            doc = _write_document(
                db,
                doc_type="invoice",
                title=f"Invoice {ref} — {vendors[vendor_code].name}",
                filename=f"{ref.lower()}.md",
                content=(
                    f"# Invoice {ref}\n\nVendor: {vendors[vendor_code].name}\n"
                    f"Date: {inv_date.isoformat()}\nAmount: ${amount:,.2f}\n"
                    f"Description: {desc}\nPO: PO-{inv_counter}\n"
                    f"Payment terms: Net {vendors[vendor_code].payment_terms_days}\n"
                ),
                related_entity_type="invoice",
                related_entity_id=ref,
                period=period,
                tags=["invoice", vendor_code.lower()],
            )
            inv = Invoice(
                invoice_number=ref,
                vendor_id=vendors[vendor_code].id,
                direction="payable",
                invoice_date=inv_date,
                due_date=due,
                amount=amount,
                status="paid",
                description=desc,
                reference=f"PO-{inv_counter}",
                document_id=doc.id,
            )
            db.add(inv)
            db.flush()
            invoices.append(inv)

            # AP accrual JE
            je_counter += 1
            je = JournalEntry(
                entry_number=f"JE-{je_counter}",
                entry_date=inv_date,
                period=period,
                source="ap",
                memo=f"AP accrual {ref}",
                created_by="ap_bot",
            )
            db.add(je)
            db.flush()
            exp_code = expense_accounts[vendors[vendor_code].category]
            line_exp = JournalLine(
                journal_entry_id=je.id,
                account_id=accounts[exp_code].id,
                debit=amount,
                credit=0.0,
                description=desc,
                vendor_id=vendors[vendor_code].id,
                invoice_id=inv.id,
                reference=ref,
            )
            line_ap = JournalLine(
                journal_entry_id=je.id,
                account_id=accounts["2000"].id,
                debit=0.0,
                credit=amount,
                description=f"AP {vendors[vendor_code].name}",
                vendor_id=vendors[vendor_code].id,
                invoice_id=inv.id,
                reference=ref,
            )
            db.add_all([line_exp, line_ap])
            db.flush()

            # Cash payment JE + bank withdrawal (matched)
            pay_date = min(due, month_end - timedelta(days=RNG.randint(0, 3)))
            je_counter += 1
            je_pay = JournalEntry(
                entry_number=f"JE-{je_counter}",
                entry_date=pay_date,
                period=period,
                source="treasury",
                memo=f"Payment {ref}",
                created_by="treasury",
            )
            db.add(je_pay)
            db.flush()
            cash_line = JournalLine(
                journal_entry_id=je_pay.id,
                account_id=accounts["1000"].id,
                debit=0.0,
                credit=amount,
                description=f"Bank payment {ref}",
                vendor_id=vendors[vendor_code].id,
                invoice_id=inv.id,
                reference=ref,
            )
            ap_clear = JournalLine(
                journal_entry_id=je_pay.id,
                account_id=accounts["2000"].id,
                debit=amount,
                credit=0.0,
                description=f"Clear AP {ref}",
                vendor_id=vendors[vendor_code].id,
                invoice_id=inv.id,
                reference=ref,
            )
            db.add_all([cash_line, ap_clear])
            db.flush()
            journal_lines_by_ref[ref] = cash_line

            bank_counter += 1
            bt = BankTransaction(
                bank_account_code="1000",
                txn_date=pay_date,
                posted_date=pay_date,
                amount=-amount,
                description=f"ACH {vendors[vendor_code].name} {ref}",
                counterparty=vendors[vendor_code].name,
                reference=ref,
                txn_type="ach",
                reconciliation_status="unmatched",
            )
            db.add(bt)
            db.flush()
            bank_txns.append(bt)
            ground_truth["recon_expected"]["matched"].append(
                {"bank_txn_id": bt.id, "invoice": ref, "journal_line_id": cash_line.id}
            )

        # AR receipts
        for cust_code, amount in [
            ("C-APEX", 92000.00),
            ("C-BLUE", 64000.00),
            ("C-CANY", 41000.00),
            ("C-DRFT", 28500.00),
            ("C-EAST", 51000.00 if period != "2024-08" else 72000.00),
        ]:
            inv_counter += 1
            inv_date = month_start + timedelta(days=3)
            ref = f"AR-{inv_counter}"
            inv = Invoice(
                invoice_number=ref,
                customer_id=customers[cust_code].id,
                direction="receivable",
                invoice_date=inv_date,
                due_date=inv_date + timedelta(days=30),
                amount=amount,
                status="paid",
                description=f"Services — {customers[cust_code].name}",
                reference=ref,
            )
            db.add(inv)
            db.flush()

            recv_date = inv_date + timedelta(days=RNG.randint(10, 25))
            je_counter += 1
            je = JournalEntry(
                entry_number=f"JE-{je_counter}",
                entry_date=recv_date,
                period=period,
                source="ar",
                memo=f"Cash receipt {ref}",
                created_by="ar_bot",
            )
            db.add(je)
            db.flush()
            cash_line = JournalLine(
                journal_entry_id=je.id,
                account_id=accounts["1000"].id,
                debit=amount,
                credit=0.0,
                description=f"Deposit {ref}",
                invoice_id=inv.id,
                reference=ref,
            )
            ar_line = JournalLine(
                journal_entry_id=je.id,
                account_id=accounts["1100"].id,
                debit=0.0,
                credit=amount,
                description=f"Clear AR {ref}",
                invoice_id=inv.id,
                reference=ref,
            )
            db.add_all([cash_line, ar_line])
            db.flush()
            journal_lines_by_ref[ref] = cash_line

            bank_counter += 1
            bt = BankTransaction(
                bank_account_code="1000",
                txn_date=recv_date,
                posted_date=recv_date,
                amount=amount,
                description=f"WIRE {customers[cust_code].name} {ref}",
                counterparty=customers[cust_code].name,
                reference=ref,
                txn_type="wire",
            )
            db.add(bt)
            db.flush()
            bank_txns.append(bt)
            ground_truth["recon_expected"]["matched"].append(
                {"bank_txn_id": bt.id, "invoice": ref, "journal_line_id": cash_line.id}
            )

    # --- August-specific recon scenarios that create $82,000 bank > ledger gap ---
    # 1) Bank deposit in transit not yet in ledger: +45,000 (unmatched bank)
    bt_in_transit = BankTransaction(
        bank_account_code="1000",
        txn_date=date(2024, 8, 30),
        posted_date=date(2024, 8, 30),
        amount=45000.00,
        description="WIRE Canyon Software deposit-in-transit CANY-AUG",
        counterparty="Canyon Software",
        reference="DIT-AUG-45000",
        txn_type="wire",
    )
    db.add(bt_in_transit)
    db.flush()
    ground_truth["recon_expected"]["unmatched_bank"].append(
        {"bank_txn_id": bt_in_transit.id, "reason": "deposit_in_transit"}
    )

    # 2) Outstanding check recorded in ledger but not cleared bank: ledger cash lower by 22,000
    # Wait - if bank is HIGHER than ledger by 82k:
    # Bank - Ledger = 82000
    # Deposit in transit (in bank, not ledger): +45000 to gap
    # Outstanding check (in ledger as credit to cash, not in bank): +22000 to gap
    # Unrecorded bank fee? Actually bank fee would make bank LOWER.
    # Timing: customer payment in bank +15000 not in GL yet
    # TOTAL: 45000 + 22000 + 15000 = 82000 ✓

    je_counter += 1
    outstanding_check_je = JournalEntry(
        entry_number=f"JE-{je_counter}",
        entry_date=date(2024, 8, 28),
        period="2024-08",
        source="treasury",
        memo="Outstanding check to Northwind Steel — uncleared",
        created_by="treasury",
    )
    db.add(outstanding_check_je)
    db.flush()
    oc_amount = 22000.00
    oc_cash = JournalLine(
        journal_entry_id=outstanding_check_je.id,
        account_id=accounts["1000"].id,
        debit=0.0,
        credit=oc_amount,
        description="Outstanding check CHK-88421",
        vendor_id=vendors["V-NWST"].id,
        reference="CHK-88421",
    )
    oc_ap = JournalLine(
        journal_entry_id=outstanding_check_je.id,
        account_id=accounts["2000"].id,
        debit=oc_amount,
        credit=0.0,
        description="Pay Northwind outstanding",
        vendor_id=vendors["V-NWST"].id,
        reference="CHK-88421",
    )
    db.add_all([oc_cash, oc_ap])
    db.flush()
    ground_truth["recon_expected"]["unmatched_bank"].append(
        {
            "journal_line_id": oc_cash.id,
            "reason": "outstanding_check_not_cleared",
            "amount": oc_amount,
        }
    )

    bt_extra = BankTransaction(
        bank_account_code="1000",
        txn_date=date(2024, 8, 31),
        posted_date=date(2024, 8, 31),
        amount=15000.00,
        description="ACH Apex Retail Group late receipt APEX-LATE",
        counterparty="Apex Retail Group",
        reference="LATE-APEX-15K",
        txn_type="ach",
    )
    db.add(bt_extra)
    db.flush()
    ground_truth["recon_expected"]["unmatched_bank"].append(
        {"bank_txn_id": bt_extra.id, "reason": "unrecorded_receipt"}
    )

    ground_truth["bank_vs_ledger_gap"] = {
        "period": "2024-08",
        "account": "1000",
        "expected_gap": 82000.00,
        "components": [
            {"type": "deposit_in_transit", "amount": 45000.00},
            {"type": "outstanding_check", "amount": 22000.00},
            {"type": "unrecorded_bank_receipt", "amount": 15000.00},
        ],
    }

    # Probable match: amount close, date within window, fuzzy name
    je_counter += 1
    probable_je = JournalEntry(
        entry_number=f"JE-{je_counter}",
        entry_date=date(2024, 8, 12),
        period="2024-08",
        source="treasury",
        memo="Freight payment slight amount variance",
        created_by="treasury",
    )
    db.add(probable_je)
    db.flush()
    probable_amt_gl = 4999.50
    probable_line = JournalLine(
        journal_entry_id=probable_je.id,
        account_id=accounts["1000"].id,
        debit=0.0,
        credit=probable_amt_gl,
        description="Payment Global Freight",
        vendor_id=vendors["V-GLOB"].id,
        reference="GF-PROB-1",
    )
    probable_ap = JournalLine(
        journal_entry_id=probable_je.id,
        account_id=accounts["2000"].id,
        debit=probable_amt_gl,
        credit=0.0,
        description="Clear AP Global Freight",
        vendor_id=vendors["V-GLOB"].id,
        reference="GF-PROB-1",
    )
    db.add_all([probable_line, probable_ap])
    db.flush()
    bt_probable = BankTransaction(
        bank_account_code="1000",
        txn_date=date(2024, 8, 14),
        posted_date=date(2024, 8, 14),
        amount=-5000.00,
        description="ACH GLOBAL FREIGHT CO INV",
        counterparty="Global Freight Co",
        reference="GF-BANK-1",
        txn_type="ach",
    )
    db.add(bt_probable)
    db.flush()
    ground_truth["recon_expected"]["probable"].append(
        {"bank_txn_id": bt_probable.id, "journal_line_id": probable_line.id}
    )

    # Needs review: weekend wire to unusual vendor, large rounded amount
    weekend = date(2024, 8, 17)  # Saturday
    bt_suspicious = BankTransaction(
        bank_account_code="1000",
        txn_date=weekend,
        posted_date=weekend,
        amount=-100000.00,
        description="WIRE Midnight Wire Transfers LLC",
        counterparty="Midnight Wire Transfers LLC",
        reference="SUS-100K",
        txn_type="wire",
        is_anomaly_seed=True,
    )
    db.add(bt_suspicious)
    db.flush()
    ground_truth["recon_expected"]["needs_review"].append(
        {"bank_txn_id": bt_suspicious.id, "reason": "unusual_vendor_weekend_large_round"}
    )

    je_counter += 1
    sus_je = JournalEntry(
        entry_number=f"JE-{je_counter}",
        entry_date=weekend,
        period="2024-08",
        source="manual",
        memo="Weekend wire — unusual vendor",
        created_by="jsmith",
    )
    db.add(sus_je)
    db.flush()
    sus_cash = JournalLine(
        journal_entry_id=sus_je.id,
        account_id=accounts["1000"].id,
        debit=0.0,
        credit=100000.00,
        description="Wire Midnight Wire Transfers",
        vendor_id=vendors["V-UNKN"].id,
        reference="SUS-100K",
    )
    sus_exp = JournalLine(
        journal_entry_id=sus_je.id,
        account_id=accounts["5500"].id,
        debit=100000.00,
        credit=0.0,
        description="Consulting? Midnight Wire",
        vendor_id=vendors["V-UNKN"].id,
        reference="SUS-100K",
    )
    db.add_all([sus_cash, sus_exp])
    db.flush()

    # Duplicate invoice anomaly
    base_inv = next(i for i in invoices if i.invoice_number.startswith("INV-") and i.amount == 8900.00)
    dup = Invoice(
        invoice_number=f"{base_inv.invoice_number}-DUP",
        vendor_id=base_inv.vendor_id,
        direction="payable",
        invoice_date=base_inv.invoice_date + timedelta(days=1),
        due_date=base_inv.due_date + timedelta(days=1),
        amount=base_inv.amount,
        status="open",
        description=base_inv.description,
        reference=base_inv.reference,
        is_duplicate_flag=True,
    )
    db.add(dup)
    db.flush()

    # Seed anomaly ground truth flags (detector should find these)
    anomalies = [
        AnomalyFlag(
            entity_type="bank_transaction",
            entity_id=str(bt_suspicious.id),
            anomaly_type="weekend_entry",
            severity="high",
            score=0.95,
            explanation="Large wire posted on a weekend to an unexpected vendor.",
            evidence={"amount": 100000, "date": weekend.isoformat()},
            is_ground_truth=True,
        ),
        AnomalyFlag(
            entity_type="bank_transaction",
            entity_id=str(bt_suspicious.id),
            anomaly_type="unusual_vendor",
            severity="high",
            score=0.9,
            explanation="Counterparty Midnight Wire Transfers LLC is not a standard operating vendor.",
            evidence={"vendor": "Midnight Wire Transfers LLC"},
            is_ground_truth=True,
        ),
        AnomalyFlag(
            entity_type="bank_transaction",
            entity_id=str(bt_suspicious.id),
            anomaly_type="rounded_amount",
            severity="medium",
            score=0.7,
            explanation="Exact $100,000.00 rounded amount.",
            evidence={"amount": 100000},
            is_ground_truth=True,
        ),
        AnomalyFlag(
            entity_type="invoice",
            entity_id=str(dup.id),
            anomaly_type="duplicate_invoice",
            severity="high",
            score=0.98,
            explanation=f"Duplicate of {base_inv.invoice_number} same vendor/amount.",
            evidence={"original": base_inv.invoice_number, "duplicate": dup.invoice_number},
            is_ground_truth=True,
        ),
        AnomalyFlag(
            entity_type="journal_entry",
            entity_id=str(sus_je.id),
            anomaly_type="weekend_entry",
            severity="high",
            score=0.9,
            explanation="Manual journal entry posted on Saturday.",
            evidence={"entry": sus_je.entry_number},
            is_ground_truth=True,
        ),
        AnomalyFlag(
            entity_type="account_balance",
            entity_id="5400:2024-08",
            anomaly_type="expense_spike",
            severity="medium",
            score=0.85,
            explanation="Marketing expense nearly doubled MoM in August.",
            evidence={"july": 22000, "august": 48000},
            is_ground_truth=True,
        ),
    ]
    for a in anomalies:
        db.add(a)
        ground_truth["anomaly_ids"].append(
            {"entity_type": a.entity_type, "entity_id": a.entity_id, "anomaly_type": a.anomaly_type}
        )

    # Compute account balances from journal lines for each period
    db.flush()
    from sqlalchemy import select

    for period in periods:
        for acc in accounts.values():
            lines = (
                db.execute(
                    select(JournalLine, JournalEntry)
                    .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
                    .where(JournalEntry.period == period, JournalLine.account_id == acc.id)
                )
                .all()
            )
            debit = sum(l.debit for l, _ in lines)
            credit = sum(l.credit for l, _ in lines)
            if acc.account_type in ("asset", "expense"):
                ending = debit - credit
            else:
                ending = credit - debit
            budget = None
            if acc.account_type == "expense":
                budget = abs(ending) * (0.92 if period != "2024-08" or acc.account_code != "5400" else 0.55)
            db.add(
                AccountBalance(
                    account_id=acc.id,
                    period=period,
                    beginning_balance=0.0,
                    ending_balance=ending,
                    debit_total=debit,
                    credit_total=credit,
                    budget_amount=budget,
                )
            )

    # Memo explaining August bank variance
    _write_document(
        db,
        doc_type="memo",
        title="August Bank Reconciliation Notes",
        filename="memo_aug_bank_recon.md",
        content=(
            "# August 2024 Bank Reconciliation Working Notes\n\n"
            "Preliminary analysis indicates Operating Cash (1000) bank balance is approximately "
            "$82,000 higher than the general ledger due to:\n\n"
            "1. Deposit in transit $45,000 (Canyon Software) received by bank 8/30, not booked.\n"
            "2. Outstanding check CHK-88421 $22,000 to Northwind Steel still uncleared.\n"
            "3. Late ACH receipt $15,000 from Apex Retail Group on 8/31 not yet recorded in GL.\n\n"
            "Also investigate weekend wire $100,000 to Midnight Wire Transfers LLC.\n"
        ),
        related_entity_type="account",
        related_entity_id="1000",
        period="2024-08",
        tags=["reconciliation", "cash", "august"],
    )

    db.commit()

    gt_path = DATA_DIR / "ground_truth.json"
    # Serialize with simple types
    serializable = json.loads(json.dumps(ground_truth, default=str))
    gt_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    return {
        "vendors": len(vendors),
        "customers": len(customers),
        "accounts": len(accounts),
        "invoices": db.query(Invoice).count(),
        "journal_entries": db.query(JournalEntry).count(),
        "bank_transactions": db.query(BankTransaction).count(),
        "documents": db.query(Document).count(),
        "ground_truth_path": str(gt_path),
    }


def main() -> None:
    clear_and_create_schema()
    db = SessionLocal()
    try:
        summary = seed(db)
        print(json.dumps({"status": "ok", **summary}, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
