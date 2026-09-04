"""SQL / ledger query tools."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Account,
    AccountBalance,
    BankTransaction,
    Invoice,
    JournalEntry,
    JournalLine,
    Vendor,
)
from app.tools.base import ToolResult, register_tool


def _serialize_invoice(inv: Invoice) -> dict:
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "direction": inv.direction,
        "invoice_date": inv.invoice_date.isoformat(),
        "due_date": inv.due_date.isoformat(),
        "amount": inv.amount,
        "status": inv.status,
        "description": inv.description,
        "reference": inv.reference,
        "vendor_id": inv.vendor_id,
        "customer_id": inv.customer_id,
        "vendor_name": inv.vendor.name if inv.vendor else None,
        "is_duplicate_flag": inv.is_duplicate_flag,
        "document_id": inv.document_id,
    }


@register_tool("query_ledger")
def query_ledger(
    db: Session,
    account_code: Optional[str] = None,
    period: Optional[str] = None,
    entry_number: Optional[str] = None,
    reference: Optional[str] = None,
    limit: int = 50,
) -> ToolResult:
    q: Select = (
        select(JournalLine, JournalEntry, Account)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
    )
    if account_code:
        q = q.where(Account.account_code == account_code)
    if period:
        q = q.where(JournalEntry.period == period)
    if entry_number:
        q = q.where(JournalEntry.entry_number == entry_number)
    if reference:
        q = q.where(JournalLine.reference == reference)
    q = q.order_by(JournalEntry.entry_date.desc()).limit(limit)
    rows = db.execute(q).all()
    data = []
    for line, entry, account in rows:
        data.append(
            {
                "journal_line_id": line.id,
                "entry_number": entry.entry_number,
                "entry_date": entry.entry_date.isoformat(),
                "period": entry.period,
                "account_code": account.account_code,
                "account_name": account.name,
                "debit": line.debit,
                "credit": line.credit,
                "net": line.debit - line.credit,
                "description": line.description,
                "reference": line.reference,
                "memo": entry.memo,
                "source": entry.source,
            }
        )
    return ToolResult(
        tool="query_ledger",
        ok=True,
        data=data,
        summary=f"Found {len(data)} ledger lines"
        + (f" for account {account_code}" if account_code else "")
        + (f" in {period}" if period else ""),
        records_accessed=[{"type": "journal_line", "id": d["journal_line_id"]} for d in data],
    )


@register_tool("search_transactions")
def search_transactions(
    db: Session,
    query: Optional[str] = None,
    period: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    status: Optional[str] = None,
    bank_account_code: str = "1000",
    limit: int = 50,
) -> ToolResult:
    q = select(BankTransaction).where(BankTransaction.bank_account_code == bank_account_code)
    if query:
        like = f"%{query}%"
        q = q.where(
            or_(
                BankTransaction.description.ilike(like),
                BankTransaction.counterparty.ilike(like),
                BankTransaction.reference.ilike(like),
            )
        )
    if period:
        year, month = map(int, period.split("-"))
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)
        q = q.where(BankTransaction.txn_date >= start, BankTransaction.txn_date < end)
    if min_amount is not None:
        q = q.where(func.abs(BankTransaction.amount) >= min_amount)
    if max_amount is not None:
        q = q.where(func.abs(BankTransaction.amount) <= max_amount)
    if status:
        q = q.where(BankTransaction.reconciliation_status == status)
    q = q.order_by(BankTransaction.txn_date.desc()).limit(limit)
    rows = db.execute(q).scalars().all()
    data = [
        {
            "id": t.id,
            "txn_date": t.txn_date.isoformat(),
            "amount": t.amount,
            "description": t.description,
            "counterparty": t.counterparty,
            "reference": t.reference,
            "txn_type": t.txn_type,
            "reconciliation_status": t.reconciliation_status,
            "match_score": t.match_score,
        }
        for t in rows
    ]
    return ToolResult(
        tool="search_transactions",
        ok=True,
        data=data,
        summary=f"Found {len(data)} bank transactions",
        records_accessed=[{"type": "bank_transaction", "id": d["id"]} for d in data],
    )


@register_tool("retrieve_invoice")
def retrieve_invoice(
    db: Session,
    invoice_number: Optional[str] = None,
    vendor_name: Optional[str] = None,
    status: Optional[str] = None,
    unreconciled_only: bool = False,
    limit: int = 50,
) -> ToolResult:
    q = select(Invoice).options(joinedload(Invoice.vendor))
    if invoice_number:
        q = q.where(Invoice.invoice_number == invoice_number)
    if status:
        q = q.where(Invoice.status == status)
    if vendor_name:
        q = q.join(Vendor).where(Vendor.name.ilike(f"%{vendor_name}%"))
    if unreconciled_only:
        # invoices without a matched bank txn
        matched_ids = select(BankTransaction.matched_invoice_id).where(
            BankTransaction.matched_invoice_id.is_not(None)
        )
        q = q.where(Invoice.id.not_in(matched_ids), Invoice.status.in_(["open", "partial"]))
    q = q.order_by(Invoice.invoice_date.desc()).limit(limit)
    rows = db.execute(q).scalars().unique().all()
    data = [_serialize_invoice(i) for i in rows]
    return ToolResult(
        tool="retrieve_invoice",
        ok=True,
        data=data,
        summary=f"Retrieved {len(data)} invoice(s)",
        records_accessed=[{"type": "invoice", "id": d["id"]} for d in data],
    )


@register_tool("get_account_balances")
def get_account_balances(
    db: Session,
    period: Optional[str] = None,
    account_code: Optional[str] = None,
    account_type: Optional[str] = None,
) -> ToolResult:
    q = select(AccountBalance, Account).join(Account)
    if period:
        q = q.where(AccountBalance.period == period)
    if account_code:
        q = q.where(Account.account_code == account_code)
    if account_type:
        q = q.where(Account.account_type == account_type)
    rows = db.execute(q).all()
    data = [
        {
            "account_code": acc.account_code,
            "account_name": acc.name,
            "account_type": acc.account_type,
            "period": bal.period,
            "ending_balance": bal.ending_balance,
            "debit_total": bal.debit_total,
            "credit_total": bal.credit_total,
            "budget_amount": bal.budget_amount,
            "is_bank": acc.is_bank,
        }
        for bal, acc in rows
    ]
    return ToolResult(
        tool="get_account_balances",
        ok=True,
        data=data,
        summary=f"Returned {len(data)} account balances",
        records_accessed=[{"type": "account_balance", "id": f"{d['account_code']}:{d['period']}"} for d in data],
    )


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "query_ledger",
        "description": "Query general ledger journal lines by account, period, entry, or reference.",
        "parameters": {
            "account_code": "string?",
            "period": "YYYY-MM?",
            "entry_number": "string?",
            "reference": "string?",
            "limit": "int?",
        },
    },
    {
        "name": "search_transactions",
        "description": "Search bank transactions by text, period, amount, or reconciliation status.",
        "parameters": {
            "query": "string?",
            "period": "YYYY-MM?",
            "min_amount": "float?",
            "max_amount": "float?",
            "status": "string?",
            "limit": "int?",
        },
    },
    {
        "name": "retrieve_invoice",
        "description": "Retrieve invoices by number, vendor, status, or unreconciled flag.",
        "parameters": {
            "invoice_number": "string?",
            "vendor_name": "string?",
            "status": "string?",
            "unreconciled_only": "bool?",
            "limit": "int?",
        },
    },
    {
        "name": "get_account_balances",
        "description": "Get period account balances including budget amounts.",
        "parameters": {"period": "YYYY-MM?", "account_code": "string?", "account_type": "string?"},
    },
]
