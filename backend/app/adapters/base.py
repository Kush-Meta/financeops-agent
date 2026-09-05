"""Data source adapters — normalize external feeds into FinanceOps records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class NormalizedBankTxn:
    txn_date: date
    amount: float
    description: str
    counterparty: Optional[str] = None
    reference: Optional[str] = None
    txn_type: str = "ach"
    currency: str = "USD"
    fee_amount: float = 0.0
    external_id: Optional[str] = None
    source_system: str = "adapter"


@dataclass
class NormalizedVendor:
    vendor_code: str
    name: str
    category: str = "general"


@dataclass
class NormalizedInvoice:
    invoice_number: str
    vendor_code: str
    invoice_date: date
    due_date: date
    amount: float
    direction: str = "payable"
    description: str = ""
    reference: Optional[str] = None
    currency: str = "USD"
    status: str = "open"


@dataclass
class NormalizedDocument:
    doc_type: str
    title: str
    filename: str
    content: str
    period: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None


@dataclass
class NormalizedJournalLine:
    account_code: str
    debit: float = 0.0
    credit: float = 0.0
    description: str = ""
    reference: Optional[str] = None


@dataclass
class NormalizedJournalEntry:
    entry_number: str
    entry_date: date
    period: str
    memo: str
    source: str
    lines: list[NormalizedJournalLine]
    created_by: str = "import"


@dataclass
class AdapterResult:
    source: str
    vendors: list[NormalizedVendor] = field(default_factory=list)
    invoices: list[NormalizedInvoice] = field(default_factory=list)
    bank_txns: list[NormalizedBankTxn] = field(default_factory=list)
    documents: list[NormalizedDocument] = field(default_factory=list)
    journal_entries: list[NormalizedJournalEntry] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
