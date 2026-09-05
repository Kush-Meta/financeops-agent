"""Persist adapter results into the ledger."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterResult
from app.adapters.real_public import default_real_bundle
from app.core.config import get_settings
from app.models import (
    Account,
    BankTransaction,
    Document,
    ImportBatch,
    Invoice,
    JournalEntry,
    JournalLine,
    Vendor,
)


def _ensure_account_map(db: Session) -> dict[str, Account]:
    rows = db.execute(select(Account)).scalars().all()
    return {a.account_code: a for a in rows}


def apply_adapter_result(db: Session, result: AdapterResult) -> dict:
    settings = get_settings()
    docs_dir = Path(settings.documents_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    accounts = _ensure_account_map(db)

    vendor_by_code: dict[str, Vendor] = {
        v.vendor_code: v for v in db.execute(select(Vendor)).scalars().all()
    }
    created = {"vendors": 0, "invoices": 0, "bank_txns": 0, "documents": 0, "journal_entries": 0}

    for nv in result.vendors:
        if nv.vendor_code in vendor_by_code:
            continue
        v = Vendor(vendor_code=nv.vendor_code, name=nv.name, category=nv.category)
        db.add(v)
        db.flush()
        vendor_by_code[nv.vendor_code] = v
        created["vendors"] += 1

    for ni in result.invoices:
        exists = db.execute(select(Invoice).where(Invoice.invoice_number == ni.invoice_number)).scalar_one_or_none()
        if exists:
            continue
        vendor = vendor_by_code.get(ni.vendor_code)
        inv = Invoice(
            invoice_number=ni.invoice_number,
            vendor_id=vendor.id if vendor else None,
            direction=ni.direction,
            invoice_date=ni.invoice_date,
            due_date=ni.due_date,
            amount=ni.amount,
            currency=ni.currency,
            status=ni.status,
            description=ni.description,
            reference=ni.reference,
        )
        db.add(inv)
        created["invoices"] += 1

    for nb in result.bank_txns:
        if nb.external_id:
            exists = db.execute(
                select(BankTransaction).where(BankTransaction.external_id == nb.external_id)
            ).scalar_one_or_none()
            if exists:
                continue
        bt = BankTransaction(
            bank_account_code="1000",
            txn_date=nb.txn_date,
            posted_date=nb.txn_date,
            amount=nb.amount,
            description=nb.description,
            counterparty=nb.counterparty,
            reference=nb.reference,
            txn_type=nb.txn_type,
            currency=getattr(nb, "currency", "USD") or "USD",
            fee_amount=getattr(nb, "fee_amount", 0.0) or 0.0,
            source_system=nb.source_system,
            external_id=nb.external_id,
        )
        db.add(bt)
        created["bank_txns"] += 1

    for nd in result.documents:
        path = docs_dir / nd.filename
        path.write_text(nd.content, encoding="utf-8")
        doc = Document(
            doc_type=nd.doc_type,
            title=nd.title,
            filename=nd.filename,
            content=nd.content,
            related_entity_type=nd.related_entity_type,
            related_entity_id=nd.related_entity_id,
            period=nd.period,
            tags=nd.tags,
        )
        db.add(doc)
        created["documents"] += 1

    for nje in result.journal_entries:
        exists = db.execute(
            select(JournalEntry).where(JournalEntry.entry_number == nje.entry_number)
        ).scalar_one_or_none()
        if exists:
            continue
        missing = [ln.account_code for ln in nje.lines if ln.account_code not in accounts]
        if missing:
            continue
        je = JournalEntry(
            entry_number=nje.entry_number,
            entry_date=nje.entry_date,
            period=nje.period,
            source=nje.source,
            memo=nje.memo,
            created_by=nje.created_by,
            status="posted",
        )
        db.add(je)
        db.flush()
        for ln in nje.lines:
            db.add(
                JournalLine(
                    journal_entry_id=je.id,
                    account_id=accounts[ln.account_code].id,
                    debit=ln.debit,
                    credit=ln.credit,
                    description=ln.description,
                    reference=ln.reference,
                )
            )
        created["journal_entries"] += 1

    batch = ImportBatch(
        batch_id=f"imp-{uuid.uuid4().hex[:10]}",
        source=result.source,
        description=f"Imported {result.source} bundle",
        record_count=sum(created.values()),
        details={"created": created, "meta": result.meta},
    )
    db.add(batch)
    db.commit()
    return {"batch_id": batch.batch_id, "created": created, "meta": result.meta}


def import_real_public_data(db: Session) -> dict:
    bundle = default_real_bundle()
    return apply_adapter_result(db, bundle)
