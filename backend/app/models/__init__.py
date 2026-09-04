"""ORM models for FinanceOps synthetic ledger."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(80), default="general")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invoices: Mapped[list[Invoice]] = relationship(back_populates="vendor")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    segment: Mapped[str] = mapped_column(String(80), default="commercial")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    account_type: Mapped[str] = mapped_column(String(40))  # asset/liability/equity/revenue/expense
    parent_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    direction: Mapped[str] = mapped_column(String(16))  # payable | receivable
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="open")  # open/paid/partial/void
    description: Mapped[str] = mapped_column(String(500), default="")
    reference: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_duplicate_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)

    vendor: Mapped[Optional[Vendor]] = relationship(back_populates="invoices")
    customer: Mapped[Optional[Customer]] = relationship()
    document: Mapped[Optional[Document]] = relationship()


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)  # YYYY-MM
    source: Mapped[str] = mapped_column(String(40), default="manual")
    memo: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_adjusting: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="posted")

    lines: Mapped[list[JournalLine]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    debit: Mapped[float] = mapped_column(Float, default=0.0)
    credit: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(String(500), default="")
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship()
    vendor: Mapped[Optional[Vendor]] = relationship()
    invoice: Mapped[Optional[Invoice]] = relationship()


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_account_code: Mapped[str] = mapped_column(String(32), index=True)
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    posted_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)  # positive = deposit, negative = withdrawal
    description: Mapped[str] = mapped_column(String(500), default="")
    counterparty: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    txn_type: Mapped[str] = mapped_column(String(40), default="ach")
    reconciliation_status: Mapped[str] = mapped_column(String(32), default="unmatched", index=True)
    # unmatched | matched | probable | needs_review | reconciled
    matched_journal_line_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_lines.id"), nullable=True
    )
    matched_invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_anomaly_seed: Mapped[bool] = mapped_column(Boolean, default=False)


class AccountBalance(Base):
    __tablename__ = "account_balances"
    __table_args__ = (UniqueConstraint("account_id", "period", name="uq_account_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    beginning_balance: Mapped[float] = mapped_column(Float, default=0.0)
    ending_balance: Mapped[float] = mapped_column(Float, default=0.0)
    debit_total: Mapped[float] = mapped_column(Float, default=0.0)
    credit_total: Mapped[float] = mapped_column(Float, default=0.0)
    budget_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    account: Mapped[Account] = relationship()


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(40))  # invoice/receipt/policy/memo
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    related_entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    period: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    anomaly_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    is_ground_truth: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    bank_txn_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bank_transactions.id"), nullable=True)
    journal_line_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_lines.id"), nullable=True)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    match_category: Mapped[str] = mapped_column(String(32))  # matched|probable|unmatched|needs_review
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    amount_diff: Mapped[float] = mapped_column(Float, default=0.0)
    date_diff_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    action_type: Mapped[str] = mapped_column(String(64))
    # mark_reconciled | create_adjustment | approve_match | propose_journal_entry
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # pending | approved | rejected | executed | failed
    workflow_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    requested_by: Mapped[str] = mapped_column(String(80), default="agent")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    # user_request | plan | tool_call | tool_result | evidence | reasoning
    # verification | approval_proposed | approval_decision | final_response | error
    actor: Mapped[str] = mapped_column(String(80), default="system")
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_request: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tools_used: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    citations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    verification: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# Resolve forward refs for Invoice.document
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    pass
