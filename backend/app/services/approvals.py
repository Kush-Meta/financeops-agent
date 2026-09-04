"""Human-in-the-loop approval execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApprovalRequest, BankTransaction, JournalEntry, JournalLine, Account
from app.services.audit import write_audit


SENSITIVE_ACTIONS = {
    "mark_reconciled",
    "approve_match",
    "create_adjustment",
    "propose_journal_entry",
}


def create_approval_request(
    db: Session,
    action_type: str,
    title: str,
    description: str,
    payload: dict[str, Any],
    workflow_id: Optional[str] = None,
) -> ApprovalRequest:
    if action_type not in SENSITIVE_ACTIONS:
        raise ValueError(f"Unsupported action type: {action_type}")
    req = ApprovalRequest(
        request_id=f"apr-{uuid.uuid4().hex[:12]}",
        action_type=action_type,
        title=title,
        description=description,
        payload=payload,
        status="pending",
        workflow_id=workflow_id,
        requested_by="agent",
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
            details={"request_id": req.request_id, "payload": payload},
            actor="agent",
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
    if req.status != "pending":
        raise ValueError(f"Request {request_id} is not pending (status={req.status})")
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")

    req.status = decision
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
            f"Approval {decision} for {req.action_type}",
            details={"request_id": request_id, "reviewed_by": reviewed_by, "note": review_note},
            actor=reviewed_by,
        )

    if decision == "approved":
        _execute(db, req)
    return req


def _execute(db: Session, req: ApprovalRequest) -> None:
    payload = req.payload or {}
    try:
        if req.action_type in ("mark_reconciled", "approve_match"):
            txn_ids = payload.get("bank_txn_ids") or ([payload["bank_txn_id"]] if payload.get("bank_txn_id") else [])
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
            # Positive amount increases cash (debit); negative decreases
            if amount >= 0:
                db.add(JournalLine(journal_entry_id=entry.id, account_id=cash.id, debit=amount, credit=0.0, description=memo, reference=payload.get("reference")))
                db.add(JournalLine(journal_entry_id=entry.id, account_id=offset.id, debit=0.0, credit=amount, description=memo, reference=payload.get("reference")))
            else:
                amt = abs(amount)
                db.add(JournalLine(journal_entry_id=entry.id, account_id=cash.id, debit=0.0, credit=amt, description=memo, reference=payload.get("reference")))
                db.add(JournalLine(journal_entry_id=entry.id, account_id=offset.id, debit=amt, credit=0.0, description=memo, reference=payload.get("reference")))
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
