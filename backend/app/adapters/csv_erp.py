"""Customer ERP / bank CSV adapters.

Maps common finance-ops exports into FinanceOps normalized records:

- Bank feed CSV (Chase/Plaid/ERP bank-rec style)
- General ledger / journal export (NetSuite / QuickBooks Online-ish)
- Vendor master + AP invoice export

Column names are case-insensitive and accept common aliases so a first
customer engagement can land without a custom parser rewrite.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from app.adapters.base import (
    AdapterResult,
    NormalizedBankTxn,
    NormalizedInvoice,
    NormalizedJournalEntry,
    NormalizedJournalLine,
    NormalizedVendor,
)
from app.core.config import get_settings

BACKEND_DATA = Path(__file__).resolve().parents[2] / "data"
DEFAULT_CUSTOMER_DIR = BACKEND_DATA / "customer_erp"


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.strip().lower())


def _pick(row: dict[str, str], *aliases: str) -> Optional[str]:
    for alias in aliases:
        key = _norm_header(alias)
        if key in row and row[key] not in (None, ""):
            return row[key].strip()
    return None


def _parse_date(raw: Optional[str]) -> date:
    if not raw:
        raise ValueError("missing date")
    text = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {raw}")


def _parse_amount(raw: Optional[str]) -> float:
    if raw is None or str(raw).strip() == "":
        return 0.0
    text = str(raw).strip().replace(",", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    return float(text)


def _period_from_date(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _read_csv_maps(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({_norm_header(k or ""): (v or "").strip() for k, v in raw.items()})
    return rows


def parse_vendors_csv(text: str) -> list[NormalizedVendor]:
    out: list[NormalizedVendor] = []
    for row in _read_csv_maps(text):
        code = _pick(row, "vendor_code", "vendorid", "vendor", "code", "id")
        name = _pick(row, "vendor_name", "name", "displayname")
        if not code or not name:
            continue
        category = _pick(row, "category", "type", "class") or "general"
        out.append(NormalizedVendor(vendor_code=code, name=name, category=category))
    return out


def parse_bank_csv(text: str, *, source_system: str = "customer_bank_csv") -> list[NormalizedBankTxn]:
    out: list[NormalizedBankTxn] = []
    for idx, row in enumerate(_read_csv_maps(text), start=1):
        raw_date = _pick(row, "txn_date", "date", "posted_date", "postingdate", "transactiondate")
        amount = _parse_amount(_pick(row, "amount", "amt", "transactionamount"))
        # Some bank exports split debit/credit columns
        if amount == 0.0:
            debit = _parse_amount(_pick(row, "debit", "withdrawal", "outflow"))
            credit = _parse_amount(_pick(row, "credit", "deposit", "inflow"))
            amount = credit - debit
        desc = _pick(row, "description", "memo", "narrative", "payee") or "Bank transaction"
        if not raw_date:
            continue
        txn_date = _parse_date(raw_date)
        external_id = _pick(row, "external_id", "bank_txn_id", "id", "fitid", "transactionid")
        if not external_id:
            external_id = f"{source_system}:{txn_date.isoformat()}:{amount:.2f}:{idx}"
        out.append(
            NormalizedBankTxn(
                txn_date=txn_date,
                amount=amount,
                description=desc,
                counterparty=_pick(row, "counterparty", "payee", "merchant", "name"),
                reference=_pick(row, "reference", "check_number", "checknum", "ref"),
                txn_type=_pick(row, "txn_type", "type", "transactiontype") or "ach",
                currency=_pick(row, "currency", "curr") or "USD",
                fee_amount=_parse_amount(_pick(row, "fee_amount", "fee", "bank_fee")),
                external_id=external_id,
                source_system=source_system,
            )
        )
    return out


def parse_invoices_csv(text: str) -> list[NormalizedInvoice]:
    out: list[NormalizedInvoice] = []
    for row in _read_csv_maps(text):
        number = _pick(row, "invoice_number", "invoiceno", "docnumber", "bill_number", "number")
        vendor = _pick(row, "vendor_code", "vendorid", "vendor", "supplier")
        inv_date_raw = _pick(row, "invoice_date", "date", "txndate", "bill_date")
        amount = _parse_amount(_pick(row, "amount", "total", "grandtotal"))
        if not number or not vendor or not inv_date_raw or amount == 0.0:
            continue
        inv_date = _parse_date(inv_date_raw)
        due_raw = _pick(row, "due_date", "duedate")
        due = _parse_date(due_raw) if due_raw else inv_date + timedelta(days=30)
        out.append(
            NormalizedInvoice(
                invoice_number=number,
                vendor_code=vendor,
                invoice_date=inv_date,
                due_date=due,
                amount=amount,
                direction=_pick(row, "direction", "type") or "payable",
                description=_pick(row, "description", "memo") or "",
                reference=_pick(row, "reference", "po_number", "ponumber"),
                currency=_pick(row, "currency") or "USD",
                status=_pick(row, "status") or "open",
            )
        )
    return out


def parse_gl_journal_csv(text: str) -> list[NormalizedJournalEntry]:
    """Parse either one-row-per-line GL export or already-grouped journal lines.

    Expected columns (aliases accepted):
      entry_number, entry_date, account_code, debit, credit, memo/description, reference
    """
    grouped: dict[str, NormalizedJournalEntry] = {}
    for idx, row in enumerate(_read_csv_maps(text), start=1):
        entry_number = _pick(row, "entry_number", "je_number", "journal", "transactionnumber", "docnumber")
        entry_date_raw = _pick(row, "entry_date", "date", "postingdate", "txndate")
        account = _pick(row, "account_code", "account", "acct", "gl_account")
        if not entry_date_raw or not account:
            continue
        entry_date = _parse_date(entry_date_raw)
        if not entry_number:
            entry_number = f"CSV-JE-{entry_date.isoformat()}-{idx}"
        debit = _parse_amount(_pick(row, "debit", "debitamount"))
        credit = _parse_amount(_pick(row, "credit", "creditamount"))
        # Net amount column with side indicator
        if debit == 0.0 and credit == 0.0:
            net = _parse_amount(_pick(row, "amount", "net"))
            side = (_pick(row, "side", "dc", "drcr") or "").lower()
            if side in ("c", "cr", "credit"):
                credit = abs(net)
            elif side in ("d", "dr", "debit"):
                debit = abs(net)
            elif net < 0:
                credit = abs(net)
            else:
                debit = abs(net)
        memo = _pick(row, "memo", "description", "line_memo", "narrative") or ""
        reference = _pick(row, "reference", "ref", "external_id")
        if entry_number not in grouped:
            grouped[entry_number] = NormalizedJournalEntry(
                entry_number=entry_number,
                entry_date=entry_date,
                period=_period_from_date(entry_date),
                memo=memo or f"Imported journal {entry_number}",
                source="csv_gl",
                lines=[],
                created_by="csv_import",
            )
        grouped[entry_number].lines.append(
            NormalizedJournalLine(
                account_code=account,
                debit=debit,
                credit=credit,
                description=memo,
                reference=reference,
            )
        )
    # Drop unbalanced entries — finance systems should not post them
    balanced: list[NormalizedJournalEntry] = []
    for je in grouped.values():
        deb = sum(ln.debit for ln in je.lines)
        cred = sum(ln.credit for ln in je.lines)
        if abs(deb - cred) <= 0.02 and je.lines:
            balanced.append(je)
    return balanced


def load_customer_erp_bundle(directory: Optional[Path] = None) -> AdapterResult:
    """Load the bundled Meridian Robotics ERP extract (or a custom directory)."""
    settings = get_settings()
    root = Path(directory) if directory else Path(getattr(settings, "customer_erp_dir", DEFAULT_CUSTOMER_DIR))
    if not root.exists():
        raise FileNotFoundError(f"Customer ERP directory not found: {root}")

    vendors: list[NormalizedVendor] = []
    invoices: list[NormalizedInvoice] = []
    bank: list[NormalizedBankTxn] = []
    journals: list[NormalizedJournalEntry] = []
    files_used: list[str] = []

    mapping = [
        ("vendors.csv", "vendors"),
        ("ap_invoices.csv", "invoices"),
        ("bank_transactions.csv", "bank"),
        ("gl_journal.csv", "gl"),
    ]
    for filename, kind in mapping:
        path = root / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        files_used.append(filename)
        if kind == "vendors":
            vendors.extend(parse_vendors_csv(text))
        elif kind == "invoices":
            invoices.extend(parse_invoices_csv(text))
        elif kind == "bank":
            bank.extend(parse_bank_csv(text, source_system="meridian_bank_csv"))
        elif kind == "gl":
            journals.extend(parse_gl_journal_csv(text))

    if not any([vendors, invoices, bank, journals]):
        raise FileNotFoundError(f"No recognized CSV files in {root}")

    return AdapterResult(
        source="customer_erp_csv",
        vendors=vendors,
        invoices=invoices,
        bank_txns=bank,
        journal_entries=journals,
        meta={
            "customer": "Meridian Robotics (demo extract)",
            "directory": str(root),
            "files": files_used,
            "counts": {
                "vendors": len(vendors),
                "invoices": len(invoices),
                "bank_txns": len(bank),
                "journal_entries": len(journals),
            },
        },
    )


def parse_upload_bundle(
    files: Iterable[tuple[str, str]],
    *,
    source: str = "csv_upload",
) -> AdapterResult:
    """Parse an uploaded set of (filename, csv_text) pairs."""
    vendors: list[NormalizedVendor] = []
    invoices: list[NormalizedInvoice] = []
    bank: list[NormalizedBankTxn] = []
    journals: list[NormalizedJournalEntry] = []
    used: list[str] = []

    for filename, text in files:
        used.append(filename)
        lower = filename.lower()
        if "vendor" in lower:
            vendors.extend(parse_vendors_csv(text))
        elif "invoice" in lower or "ap_" in lower or "bill" in lower:
            invoices.extend(parse_invoices_csv(text))
        elif "bank" in lower or "cash" in lower:
            bank.extend(parse_bank_csv(text, source_system=source))
        elif "gl" in lower or "journal" in lower or "ledger" in lower:
            journals.extend(parse_gl_journal_csv(text))
        else:
            # Heuristic: bank-like if amount+date headers dominate
            headers = set(_read_csv_maps(text)[0].keys()) if _read_csv_maps(text) else set()
            if "accountcode" in headers or "account" in headers:
                journals.extend(parse_gl_journal_csv(text))
            else:
                bank.extend(parse_bank_csv(text, source_system=source))

    return AdapterResult(
        source=source,
        vendors=vendors,
        invoices=invoices,
        bank_txns=bank,
        journal_entries=journals,
        meta={"files": used, "upload": True},
    )
