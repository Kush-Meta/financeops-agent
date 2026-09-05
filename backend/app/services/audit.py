"""Immutable, hash-chained audit trail."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import AuditLog


def _canonical(details: Optional[dict[str, Any]]) -> str:
    if not details:
        return ""
    return json.dumps(details, sort_keys=True, default=str, separators=(",", ":"))


def compute_entry_hash(
    *,
    prev_hash: str,
    workflow_id: str,
    event_type: str,
    actor: str,
    message: str,
    details: Optional[dict[str, Any]],
) -> str:
    payload = "|".join(
        [
            prev_hash or "GENESIS",
            workflow_id,
            event_type,
            actor,
            message,
            _canonical(details),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_audit(
    db: Session,
    workflow_id: str,
    event_type: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
    actor: str = "system",
    duration_ms: Optional[float] = None,
) -> AuditLog:
    prev = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    prev_hash = prev.entry_hash if prev and prev.entry_hash else "GENESIS"
    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        workflow_id=workflow_id,
        event_type=event_type,
        actor=actor,
        message=message,
        details=details,
    )
    entry = AuditLog(
        workflow_id=workflow_id,
        event_type=event_type,
        actor=actor,
        message=message,
        details=details,
        duration_ms=duration_ms,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_audit_chain(db: Session, limit: int = 5000) -> dict[str, Any]:
    rows = list(db.execute(select(AuditLog).order_by(AuditLog.id.asc()).limit(limit)).scalars().all())
    broken_at = None
    expected_prev = "GENESIS"
    for row in rows:
        if (row.prev_hash or "GENESIS") != expected_prev:
            broken_at = row.id
            break
        calc = compute_entry_hash(
            prev_hash=row.prev_hash or "GENESIS",
            workflow_id=row.workflow_id,
            event_type=row.event_type,
            actor=row.actor,
            message=row.message,
            details=row.details,
        )
        if row.entry_hash and row.entry_hash != calc:
            broken_at = row.id
            break
        expected_prev = row.entry_hash or expected_prev
    return {
        "ok": broken_at is None,
        "checked": len(rows),
        "broken_at_id": broken_at,
        "tip_hash": rows[-1].entry_hash if rows else None,
    }


def _block_mutation(mapper, connection, target):  # noqa: ANN001
    raise RuntimeError("AuditLog is immutable — updates/deletes are forbidden")


def register_audit_immutability() -> None:
    event.listen(AuditLog, "before_update", _block_mutation)
    event.listen(AuditLog, "before_delete", _block_mutation)
