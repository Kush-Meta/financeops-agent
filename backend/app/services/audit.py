"""Audit trail helpers."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit(
    db: Session,
    workflow_id: str,
    event_type: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
    actor: str = "system",
    duration_ms: Optional[float] = None,
) -> AuditLog:
    entry = AuditLog(
        workflow_id=workflow_id,
        event_type=event_type,
        actor=actor,
        message=message,
        details=details,
        duration_ms=duration_ms,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
