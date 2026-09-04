"""Deterministic bank ↔ ledger / invoice reconciliation."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import Account, BankTransaction, Invoice, JournalEntry, JournalLine, ReconciliationResult, Vendor
from app.tools.base import ToolResult, register_tool


def _norm_name(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    for noise in ("inc", "llc", "co", "corp", "the", "ach", "wire", "payment", "inv"):
        s = re.sub(rf"\b{noise}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_similarity(a: str | None, b: str | None) -> float:
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 0.95
    return SequenceMatcher(None, na, nb).ratio()


@dataclass
class Candidate:
    journal_line: JournalLine | None
    invoice: Invoice | None
    score: float
    reasons: list[str]
    amount_diff: float
    date_diff_days: int | None
    category: str


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = map(int, period.split("-"))
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def score_match(
    bank: BankTransaction,
    line: JournalLine | None,
    invoice: Invoice | None,
    vendor_name: str | None,
) -> Candidate:
    settings = get_settings()
    reasons: list[str] = []
    score = 0.0

    # Determine comparison amount (bank amount vs cash impact)
    if line is not None:
        # Cash line: deposits are debits, withdrawals credits → signed amount as debit-credit
        gl_signed = line.debit - line.credit
        amount_diff = abs(abs(bank.amount) - abs(gl_signed))
        # Prefer opposite signs matching nature: bank deposit (+) should match debit
        if (bank.amount > 0 and line.debit > 0) or (bank.amount < 0 and line.credit > 0):
            score += 0.25
            reasons.append("direction_aligned")
        date_ref = line.entry.entry_date if line.entry else None
        ref = line.reference
        counterparty = vendor_name
        desc = line.description
    elif invoice is not None:
        amount_diff = abs(abs(bank.amount) - abs(invoice.amount))
        date_ref = invoice.invoice_date
        ref = invoice.invoice_number
        counterparty = invoice.vendor.name if invoice.vendor else None
        desc = invoice.description
        # payables are withdrawals
        if bank.amount < 0 and invoice.direction == "payable":
            score += 0.2
            reasons.append("payable_withdrawal")
        if bank.amount > 0 and invoice.direction == "receivable":
            score += 0.2
            reasons.append("receivable_deposit")
    else:
        return Candidate(None, None, 0.0, ["no_candidate"], 0.0, None, "unmatched")

    date_diff = abs((bank.txn_date - date_ref).days) if date_ref else None

    # Amount
    if amount_diff <= settings.reconcile_amount_tolerance:
        score += 0.4
        reasons.append("exact_amount")
    elif amount_diff <= settings.reconcile_probable_amount_tolerance:
        score += 0.25
        reasons.append("near_amount")
    elif amount_diff <= 50:
        score += 0.1
        reasons.append("loose_amount")
    else:
        score -= 0.3
        reasons.append("amount_mismatch")

    # Date
    if date_diff is not None:
        if date_diff == 0:
            score += 0.2
            reasons.append("same_date")
        elif date_diff <= settings.reconcile_date_window_days:
            score += 0.12
            reasons.append("within_date_window")
        elif date_diff <= 14:
            score += 0.05
            reasons.append("within_two_weeks")
        else:
            score -= 0.15
            reasons.append("date_far")

    # Reference
    bank_ref = (bank.reference or "").lower()
    if ref and bank_ref and (ref.lower() in bank_ref or bank_ref in ref.lower()):
        score += 0.25
        reasons.append("reference_match")
    elif ref and bank.description and ref.lower() in bank.description.lower():
        score += 0.2
        reasons.append("reference_in_description")

    # Counterparty / fuzzy name
    name_score = max(
        _name_similarity(bank.counterparty, counterparty),
        _name_similarity(bank.description, counterparty),
        _name_similarity(bank.description, desc),
    )
    if name_score >= 0.85:
        score += 0.2
        reasons.append("strong_name_match")
    elif name_score >= 0.6:
        score += 0.1
        reasons.append("fuzzy_name_match")

    score = max(0.0, min(1.0, score))

    if score >= 0.75 and amount_diff <= settings.reconcile_probable_amount_tolerance:
        category = "matched"
    elif score >= 0.5:
        category = "probable"
    elif score >= 0.35:
        category = "needs_review"
    else:
        category = "unmatched"

    # Force review for weekend activity or extremely large rounded wires
    risky = bank.txn_date.weekday() >= 5 or (
        abs(bank.amount) >= 100000 and abs(bank.amount) % 10000 == 0
    )
    if risky and category in ("matched", "probable"):
        category = "needs_review"
        reasons.append("forced_review_risk")

    return Candidate(line, invoice, score, reasons, amount_diff, date_diff, category)


def reconcile_period(db: Session, period: str, bank_account_code: str = "1000", persist: bool = True) -> dict:
    settings = get_settings()
    start, end = _period_bounds(period)
    run_id = f"recon-{period}-{uuid.uuid4().hex[:8]}"

    bank_txns = (
        db.execute(
            select(BankTransaction).where(
                BankTransaction.bank_account_code == bank_account_code,
                BankTransaction.txn_date >= start,
                BankTransaction.txn_date < end,
            )
        )
        .scalars()
        .all()
    )

    cash_account = db.execute(select(Account).where(Account.account_code == bank_account_code)).scalar_one()
    cash_lines = (
        db.execute(
            select(JournalLine)
            .options(joinedload(JournalLine.entry), joinedload(JournalLine.vendor), joinedload(JournalLine.invoice))
            .join(JournalEntry)
            .where(
                JournalLine.account_id == cash_account.id,
                JournalEntry.period == period,
            )
        )
        .scalars()
        .unique()
        .all()
    )

    invoices = (
        db.execute(select(Invoice).options(joinedload(Invoice.vendor)).where(Invoice.invoice_date >= start - __import__("datetime").timedelta(days=60), Invoice.invoice_date < end))
        .scalars()
        .unique()
        .all()
    )

    used_lines: set[int] = set()
    used_invoices: set[int] = set()
    results: list[dict] = []

    for bt in bank_txns:
        best: Candidate | None = None

        for line in cash_lines:
            if line.id in used_lines:
                continue
            vendor_name = line.vendor.name if line.vendor else None
            cand = score_match(bt, line, line.invoice, vendor_name)
            if best is None or cand.score > best.score:
                best = cand

        # Also try invoices not already linked via line
        for inv in invoices:
            if inv.id in used_invoices:
                continue
            cand = score_match(bt, None, inv, inv.vendor.name if inv.vendor else None)
            if best is None or cand.score > best.score:
                best = cand

        if best is None or best.category == "unmatched" or best.score < 0.35:
            item = {
                "bank_txn_id": bt.id,
                "bank_amount": bt.amount,
                "bank_date": bt.txn_date.isoformat(),
                "bank_description": bt.description,
                "bank_reference": bt.reference,
                "match_category": "unmatched",
                "score": best.score if best else 0.0,
                "reasons": best.reasons if best else ["no_candidate"],
                "journal_line_id": None,
                "invoice_id": None,
                "amount_diff": None,
                "date_diff_days": None,
            }
            bt.reconciliation_status = "unmatched"
            bt.matched_journal_line_id = None
            bt.matched_invoice_id = None
            bt.match_score = item["score"]
        else:
            jl_id = best.journal_line.id if best.journal_line else None
            inv_id = (
                best.invoice.id
                if best.invoice
                else (best.journal_line.invoice_id if best.journal_line else None)
            )
            if jl_id:
                used_lines.add(jl_id)
            if inv_id:
                used_invoices.add(inv_id)
            item = {
                "bank_txn_id": bt.id,
                "bank_amount": bt.amount,
                "bank_date": bt.txn_date.isoformat(),
                "bank_description": bt.description,
                "bank_reference": bt.reference,
                "match_category": best.category,
                "score": round(best.score, 4),
                "reasons": best.reasons,
                "journal_line_id": jl_id,
                "invoice_id": inv_id,
                "amount_diff": round(best.amount_diff, 2),
                "date_diff_days": best.date_diff_days,
                "gl_description": best.journal_line.description if best.journal_line else None,
                "invoice_number": best.invoice.invoice_number if best.invoice else None,
            }
            bt.reconciliation_status = best.category if best.category != "matched" else "matched"
            bt.matched_journal_line_id = jl_id
            bt.matched_invoice_id = inv_id
            bt.match_score = best.score

        results.append(item)
        if persist:
            db.add(
                ReconciliationResult(
                    run_id=run_id,
                    bank_txn_id=bt.id,
                    journal_line_id=item.get("journal_line_id"),
                    invoice_id=item.get("invoice_id"),
                    match_category=item["match_category"],
                    score=item["score"] or 0.0,
                    reasons=item["reasons"],
                    amount_diff=item.get("amount_diff") or 0.0,
                    date_diff_days=item.get("date_diff_days"),
                )
            )

    # Unmatched cash lines (e.g. outstanding checks)
    unmatched_gl = []
    for line in cash_lines:
        if line.id in used_lines:
            continue
        unmatched_gl.append(
            {
                "journal_line_id": line.id,
                "entry_date": line.entry.entry_date.isoformat() if line.entry else None,
                "amount": line.debit - line.credit,
                "description": line.description,
                "reference": line.reference,
                "match_category": "unmatched_gl",
            }
        )
        if persist:
            db.add(
                ReconciliationResult(
                    run_id=run_id,
                    bank_txn_id=None,
                    journal_line_id=line.id,
                    invoice_id=line.invoice_id,
                    match_category="unmatched_gl",
                    score=0.0,
                    reasons=["no_bank_match"],
                    amount_diff=0.0,
                )
            )

    if persist:
        db.commit()

    summary_counts = {
        "matched": sum(1 for r in results if r["match_category"] == "matched"),
        "probable": sum(1 for r in results if r["match_category"] == "probable"),
        "needs_review": sum(1 for r in results if r["match_category"] == "needs_review"),
        "unmatched": sum(1 for r in results if r["match_category"] == "unmatched"),
        "unmatched_gl": len(unmatched_gl),
    }

    bank_total = sum(t.amount for t in bank_txns)
    gl_total = sum(l.debit - l.credit for l in cash_lines)
    gap = round(bank_total - gl_total, 2)

    return {
        "run_id": run_id,
        "period": period,
        "bank_account_code": bank_account_code,
        "counts": summary_counts,
        "bank_total": round(bank_total, 2),
        "ledger_cash_net": round(gl_total, 2),
        "bank_minus_ledger": gap,
        "amount_tolerance": settings.reconcile_amount_tolerance,
        "results": results,
        "unmatched_gl": unmatched_gl,
    }


@register_tool("reconcile_transactions")
def reconcile_transactions(
    db: Session,
    period: str = "2024-08",
    bank_account_code: str = "1000",
    persist: bool = True,
) -> ToolResult:
    data = reconcile_period(db, period=period, bank_account_code=bank_account_code, persist=persist)
    accessed = [{"type": "bank_transaction", "id": r["bank_txn_id"]} for r in data["results"]]
    accessed += [{"type": "journal_line", "id": g["journal_line_id"]} for g in data["unmatched_gl"]]
    return ToolResult(
        tool="reconcile_transactions",
        ok=True,
        data=data,
        summary=(
            f"Reconciled {period}: {data['counts']['matched']} matched, "
            f"{data['counts']['probable']} probable, {data['counts']['unmatched']} unmatched bank, "
            f"{data['counts']['needs_review']} needs review; bank−ledger gap ${data['bank_minus_ledger']:,.2f}"
        ),
        records_accessed=accessed,
        calculations=[
            {"name": "bank_total", "value": data["bank_total"]},
            {"name": "ledger_cash_net", "value": data["ledger_cash_net"]},
            {"name": "bank_minus_ledger", "value": data["bank_minus_ledger"]},
        ],
    )


@register_tool("detect_duplicates")
def detect_duplicates(db: Session, lookback_days: int = 7) -> ToolResult:
    invoices = db.execute(select(Invoice).options(joinedload(Invoice.vendor))).scalars().unique().all()
    dups = []
    by_key: dict[tuple, list[Invoice]] = {}
    for inv in invoices:
        key = (inv.vendor_id, round(inv.amount, 2), inv.description.strip().lower())
        by_key.setdefault(key, []).append(inv)
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda x: x.invoice_date)
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if abs((a.invoice_date - b.invoice_date).days) <= lookback_days:
                    dups.append(
                        {
                            "invoice_a": a.invoice_number,
                            "invoice_b": b.invoice_number,
                            "amount": a.amount,
                            "vendor": a.vendor.name if a.vendor else None,
                            "date_diff_days": abs((a.invoice_date - b.invoice_date).days),
                        }
                    )
    return ToolResult(
        tool="detect_duplicates",
        ok=True,
        data=dups,
        summary=f"Found {len(dups)} potential duplicate invoice pair(s)",
        records_accessed=[{"type": "invoice", "id": d["invoice_a"]} for d in dups],
    )
