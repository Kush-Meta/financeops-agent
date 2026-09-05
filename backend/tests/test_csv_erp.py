"""Customer ERP CSV adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.adapters.csv_erp import (
    DEFAULT_CUSTOMER_DIR,
    load_customer_erp_bundle,
    parse_bank_csv,
    parse_gl_journal_csv,
    parse_upload_bundle,
)
from app.adapters.persist import apply_adapter_result, import_customer_erp_data
from app.core.database import Base, SessionLocal, engine
from app.models import BankTransaction, ImportBatch, Invoice, JournalEntry, Vendor
from app.scripts.seed import seed
from app.tools.reconcile import reconcile_transactions


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed(session)
    yield session
    session.close()


def test_bank_csv_aliases_and_us_dates():
    text = "Date,Amount,Description,Payee,FITID\n09/18/2024,\"18,500.00\",Deposit,Riverland,ABC-1\n"
    rows = parse_bank_csv(text)
    assert len(rows) == 1
    assert rows[0].amount == 18500.0
    assert rows[0].external_id == "ABC-1"
    assert rows[0].txn_date.isoformat() == "2024-09-18"


def test_gl_rejects_unbalanced_entry():
    text = (
        "entry_number,entry_date,account_code,debit,credit,memo\n"
        "JE-1,2024-09-01,1000,100,0,bad\n"
        "JE-1,2024-09-01,2000,0,50,bad\n"
    )
    assert parse_gl_journal_csv(text) == []


def test_bundled_customer_pack_loads(db):
    assert DEFAULT_CUSTOMER_DIR.exists()
    result = import_customer_erp_data(db)
    assert result["created"]["bank_txns"] >= 8
    assert result["created"]["journal_entries"] >= 5
    assert result["created"]["vendors"] >= 5
    assert result["created"]["invoices"] >= 5
    batches = db.execute(select(ImportBatch)).scalars().all()
    assert any(b.source == "customer_erp_csv" for b in batches)


def test_customer_september_recon_finds_known_breaks(db):
    import_customer_erp_data(db)
    recon = reconcile_transactions(db, period="2024-09", persist=False)
    gap = recon.data["bank_minus_ledger"]
    # Deposit in transit 18500 - unrecorded fee 35 + outstanding check 7200 = 25665
    assert abs(gap - 25665.0) < 1.0
    unmatched_bank = [
        r for r in recon.data["results"] if r["match_category"] in ("unmatched", "probable")
    ]
    assert any(abs(r["bank_amount"] - 18500) < 0.01 for r in unmatched_bank)
    assert any(abs(r["bank_amount"] + 35) < 0.01 or abs(r["bank_amount"] - (-35)) < 0.01 for r in unmatched_bank)


def test_upload_bundle_idempotent(db):
    bundle = load_customer_erp_bundle()
    first = apply_adapter_result(db, bundle)
    second = apply_adapter_result(db, parse_upload_bundle([
        ("bank_transactions.csv", (DEFAULT_CUSTOMER_DIR / "bank_transactions.csv").read_text()),
        ("gl_journal.csv", (DEFAULT_CUSTOMER_DIR / "gl_journal.csv").read_text()),
        ("vendors.csv", (DEFAULT_CUSTOMER_DIR / "vendors.csv").read_text()),
        ("ap_invoices.csv", (DEFAULT_CUSTOMER_DIR / "ap_invoices.csv").read_text()),
    ]))
    assert first["created"]["bank_txns"] > 0
    assert second["created"]["bank_txns"] == 0
    assert db.execute(select(func.count()).select_from(BankTransaction)).scalar() >= first["created"]["bank_txns"]
    assert db.execute(select(func.count()).select_from(Vendor)).scalar() >= 1
    assert db.execute(select(func.count()).select_from(Invoice)).scalar() >= 1
    assert db.execute(select(func.count()).select_from(JournalEntry)).scalar() >= 1
