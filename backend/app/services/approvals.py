"""Human-in-the-loop approvals with maker-checker for material amounts."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Account, ApprovalRequest, BankTransaction, JournalEntry, JournalLine
from app.services.audit import write_audit

SENSITIVE_ACTIONS = {
    "mark_reconciled",
    "approve_match",
    "create_adjustment",
    "propose_journal_entry",
}


def _payload_amount(payload: dict[str, Any]) -> float:
    if payload.get("amount") is not None:
        return abs(float(payload["amount"]))
    if payload.get("bank_txn_ids"):
        return abs(float(payload.get("total_amount") or 0))
    return 0.0


def create_approval_request(
    db: Session,
    action_type: str,
    title: str,
    description: str,
    payload: dict[str, Any],
    workflow_id: Optional[str] = None,
    requested_by: str = "agent",
) -> ApprovalRequest:
    if action_type not in SENSITIVE_ACTIONS:
        raise ValueError(f"Unsupported action type: {action_type}")

    settings = get_settings()
    amount = _payload_amount(payload)
    needs_second = bool(
        settings.maker_checker_enabled and amount >= settings.maker_checker_amount_threshold
    )

    req = ApprovalRequest(
        request_id=f"apr-{uuid.uuid4().hex[:12]}",
        action_type=action_type,
        title=title,
        description=description
        + (
            f"\n\nMaker-checker required (amount ${amount:,.2f} ≥ "
            f"${settings.maker_checker_amount_threshold:,.2f})."
            if needs_second
            else ""
        ),
        payload=payload,
        status="pending",
        workflow_id=workflow_id,
        requested_by=requested_by,
        requires_second_approval=needs_second,
        amount=amount,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    if workflow_id:
        write_audit(
            db,
            workflow_id,
            "approval_proposed",
            f"Proposed action {action_type}: {title}",
            details={
                "request_id": req.request_id,
                "payload": payload,
                "requires_second_approval": needs_second,
                "amount": amount,
            },
            actor=requested_by,
        )
    return req


def list_approvals(db: Session, status: Optional[str] = None) -> list[ApprovalRequest]:
    q = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if status:
        q = q.where(ApprovalRequest.status == status)
    return list(db.execute(q).scalars().all())


def decide_approval(
    db: Session,
    request_id: str,
    decision: str,
    reviewed_by: str = "controller",
    review_note: str = "",
) -> ApprovalRequest:
    req = db.execute(select(ApprovalRequest).where(ApprovalRequest.request_id == request_id)).scalar_one()
    if req.status not in ("pending", "awaiting_second_approval"):
        raise ValueError(f"Request {request_id} is not approvable (status={req.status})")
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")

    # Reject always final
    if decision == "rejected":
        req.status = "rejected"
        req.reviewed_by = reviewed_by
        req.review_note = review_note
        req.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(req)
        if req.workflow_id:
            write_audit(
                db,
                req.workflow_id,
                "approval_decision",
                f"Approval rejected for {req.action_type}",
                details={"request_id": request_id, "reviewed_by": reviewed_by, "note": review_note},
                actor=reviewed_by,
            )
        return req

    # Maker-checker path
    if req.requires_second_approval:
        if req.status == "pending":
            if reviewed_by == req.requested_by:
                raise ValueError("Maker cannot also be the first checker for material amounts")
            req.first_approver = reviewed_by
            req.status = "awaiting_second_approval"
            req.review_note = review_note
            req.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            db.refresh(req)
            if req.workflow_id:
                write_audit(
                    db,
                    req.workflow_id,
                    "approval_decision",
                    "First approval recorded; awaiting second controller",
                    details={"request_id": request_id, "first_approver": reviewed_by},
                    actor=reviewed_by,
                )
            return req

        # second approval
        if reviewed_by in {req.requested_by, req.first_approver}:
            raise ValueError("Second approver must be different from maker and first checker")
        req.second_approver = reviewed_by
        req.reviewed_by = reviewed_by
        req.review_note = (req.review_note or "") + f"\nSecond approval: {review_note}".strip()
        req.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        req.status = "approved"
        db.commit()
        db.refresh(req)
        if req.workflow_id:
            write_audit(
                db,
                req.workflow_id,
                "approval_decision",
                "Second approval recorded; executing",
                details={
                    "request_id": request_id,
                    "first_approver": req.first_approver,
                    "second_approver": reviewed_by,
                },
                actor=reviewed_by,
            )
        _execute(db, req)
        return req

    # Single-approval path
    req.status = "approved"
    req.reviewed_by = reviewed_by
    req.review_note = review_note
    req.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(req)
    if req.workflow_id:
        write_audit(
            db,
            req.workflow_id,
            "approval_decision",
            f"Approval approved for {req.action_type}",
            details={"request_id": request_id, "reviewed_by": reviewed_by, "note": review_note},
            actor=reviewed_by,
        )
    _execute(db, req)
    return req


def _execute(db: Session, req: ApprovalRequest) -> None:
    payload = req.payload or {}
    try:
        if req.action_type in ("mark_reconciled", "approve_match"):
            txn_ids = payload.get("bank_txn_ids") or (
                [payload["bank_txn_id"]] if payload.get("bank_txn_id") else []
            )
            for tid in txn_ids:
                txn = db.get(BankTransaction, int(tid))
                if txn:
                    txn.reconciliation_status = "reconciled"
                    if payload.get("journal_line_id"):
                        txn.matched_journal_line_id = int(payload["journal_line_id"])
                    if payload.get("invoice_id"):
                        txn.matched_invoice_id = int(payload["invoice_id"])
        elif req.action_type in ("create_adjustment", "propose_journal_entry"):
            account_code = payload.get("account_code", "1000")
            amount = float(payload["amount"])
            memo = payload.get("memo", "Agent-proposed adjusting entry")
            period = payload.get("period", "2024-08")
            offset_code = payload.get("offset_account_code", "2100")
            cash = db.execute(select(Account).where(Account.account_code == account_code)).scalar_one()
            offset = db.execute(select(Account).where(Account.account_code == offset_code)).scalar_one()
            entry_number = f"JE-ADJ-{uuid.uuid4().hex[:8].upper()}"
            from datetime import date

            year, month = map(int, period.split("-"))
            entry = JournalEntry(
                entry_number=entry_number,
                entry_date=date(year, month, 28),
                period=period,
                source="adjustment",
                memo=memo,
                created_by=req.reviewed_by or "controller",
                is_adjusting=True,
                status="posted",
            )
            db.add(entry)
            db.flush()
            if amount >= 0:
                db.add(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=cash.id,
                        debit=amount,
                        credit=0.0,
                        description=memo,
                        reference=payload.get("reference"),
                    )
                )
                db.add(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=offset.id,
                        debit=0.0,
                        credit=amount,
                        description=memo,
                        reference=payload.get("reference"),
                    )
                )
            else:
                amt = abs(amount)
                db.add(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=cash.id,
                        debit=0.0,
                        credit=amt,
                        description=memo,
                        reference=payload.get("reference"),
                    )
                )
                db.add(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=offset.id,
                        debit=amt,
                        credit=0.0,
                        description=memo,
                        reference=payload.get("reference"),
                    )
                )
            req.payload = {**payload, "created_entry_number": entry_number}

        req.status = "executed"
        req.executed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        if req.workflow_id:
            write_audit(
                db,
                req.workflow_id,
                "approval_decision",
                f"Executed approved action {req.action_type}",
                details={"request_id": req.request_id, "payload": req.payload},
                actor=req.reviewed_by or "controller",
            )
    except Exception as exc:  # noqa: BLE001
        req.status = "failed"
        req.review_note = (req.review_note or "") + f"\nExecution error: {exc}"
        db.commit()
        raise
