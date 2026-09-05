"""FastAPI route handlers."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app import __version__
from app.agent.workflow import run_investigation
from app.adapters.csv_erp import parse_upload_bundle
from app.adapters.persist import apply_adapter_result, import_customer_erp_data, import_real_public_data
from app.api.schemas import AnomalyRequest, ApprovalDecision, AskRequest, HealthResponse, ReconcileRequest
from app.core.auth import Principal, get_principal, require_role
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    AnomalyFlag,
    ApprovalRequest,
    AuditLog,
    BankTransaction,
    Document,
    ImportBatch,
    Invoice,
    WorkflowRun,
)
from app.services import approvals as approval_service
from app.services.audit import verify_audit_chain
from app.tools.anomalies import detect_anomalies
from app.tools.reconcile import reconcile_transactions
from app.tools.variance import calculate_variance
import app.tools  # noqa: F401

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=__version__, database=settings.database_url.split("://")[0])


@router.get("/auth/me")
def auth_me(principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    settings = get_settings()
    return {
        "user_id": principal.user_id,
        "name": principal.name,
        "role": principal.role,
        "api_key_id": principal.api_key_id,
        "auth_enabled": settings.auth_enabled,
        "maker_checker_enabled": settings.maker_checker_enabled,
        "maker_checker_amount_threshold": settings.maker_checker_amount_threshold,
        "demo_keys": {
            "investigator": "fo_investigator_dev",
            "controller": "fo_controller_dev",
            "admin": "fo_admin_dev",
            "viewer": "fo_viewer_dev",
        },
    }


@router.post("/ask")
def ask(
    body: AskRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("investigator")),
) -> dict[str, Any]:
    try:
        return run_investigation(
            db,
            user_request=body.question,
            actor=principal.name,
            auto_propose_actions=body.auto_propose_actions,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/workflows")
def list_workflows(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(WorkflowRun).order_by(desc(WorkflowRun.created_at)).limit(limit)).scalars().all()
    return [
        {
            "workflow_id": r.workflow_id,
            "status": r.status,
            "user_request": r.user_request,
            "answer": r.answer,
            "requires_approval": r.requires_approval,
            "approval_request_id": r.approval_request_id,
            "latency_ms": r.latency_ms,
            "tools_used": r.tools_used,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.execute(select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)).scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Workflow not found")
    audits = (
        db.execute(select(AuditLog).where(AuditLog.workflow_id == workflow_id).order_by(AuditLog.created_at))
        .scalars()
        .all()
    )
    return {
        "workflow_id": run.workflow_id,
        "status": run.status,
        "user_request": run.user_request,
        "plan": run.plan,
        "tools_used": run.tools_used,
        "evidence": run.evidence,
        "answer": run.answer,
        "citations": run.citations,
        "verification": run.verification,
        "requires_approval": run.requires_approval,
        "approval_request_id": run.approval_request_id,
        "latency_ms": run.latency_ms,
        "estimated_cost_usd": run.estimated_cost_usd,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "audit_trail": [
            {
                "id": a.id,
                "event_type": a.event_type,
                "actor": a.actor,
                "message": a.message,
                "details": a.details,
                "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in audits
        ],
    }


@router.post("/reconcile")
def reconcile(body: ReconcileRequest, db: Session = Depends(get_db)) -> dict:
    result = reconcile_transactions(
        db, period=body.period, bank_account_code=body.bank_account_code, persist=body.persist
    )
    return result.to_dict()


@router.post("/anomalies/detect")
def anomalies_detect(body: AnomalyRequest, db: Session = Depends(get_db)) -> dict:
    result = detect_anomalies(db, period=body.period, persist_flags=body.persist_flags)
    return result.to_dict()


@router.get("/anomalies")
def list_anomalies(
    period: Optional[str] = None,
    ground_truth_only: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    q = select(AnomalyFlag).order_by(desc(AnomalyFlag.score))
    if ground_truth_only:
        q = q.where(AnomalyFlag.is_ground_truth.is_(True))
    rows = db.execute(q).scalars().all()
    data = [
        {
            "id": a.id,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "anomaly_type": a.anomaly_type,
            "severity": a.severity,
            "score": a.score,
            "explanation": a.explanation,
            "evidence": a.evidence,
            "status": a.status,
            "is_ground_truth": a.is_ground_truth,
        }
        for a in rows
    ]
    if period:
        # filter loosely via evidence/entity
        data = [d for d in data if period in str(d.get("evidence")) or period in d["entity_id"]]
    return data


@router.get("/variance")
def variance(
    period: str = "2024-08",
    account_type: str = "expense",
    db: Session = Depends(get_db),
) -> dict:
    return calculate_variance(db, period=period, account_type=account_type).to_dict()


@router.get("/transactions")
def transactions(
    period: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.tools.query import search_transactions

    return search_transactions(db, period=period, status=status, limit=limit).data


@router.get("/invoices")
def invoices(
    status: Optional[str] = None,
    unreconciled_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.tools.query import retrieve_invoice

    return retrieve_invoice(db, status=status, unreconciled_only=unreconciled_only, limit=limit).data


@router.get("/documents")
def documents(
    q: Optional[str] = Query(None),
    period: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    if q:
        from app.tools.documents import search_documents

        return search_documents(db, query=q, period=period).data
    rows = db.execute(select(Document).order_by(desc(Document.created_at)).limit(50)).scalars().all()
    return [
        {
            "id": d.id,
            "doc_type": d.doc_type,
            "title": d.title,
            "filename": d.filename,
            "period": d.period,
            "snippet": d.content[:400],
            "tags": d.tags,
        }
        for d in rows
    ]


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)) -> dict:
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    return {
        "id": d.id,
        "doc_type": d.doc_type,
        "title": d.title,
        "filename": d.filename,
        "content": d.content,
        "period": d.period,
        "tags": d.tags,
        "related_entity_type": d.related_entity_type,
        "related_entity_id": d.related_entity_id,
    }


@router.get("/approvals")
def get_approvals(status: Optional[str] = None, db: Session = Depends(get_db)) -> list[dict]:
    rows = approval_service.list_approvals(db, status=status)
    return [
        {
            "request_id": r.request_id,
            "action_type": r.action_type,
            "title": r.title,
            "description": r.description,
            "payload": r.payload,
            "status": r.status,
            "workflow_id": r.workflow_id,
            "requested_by": r.requested_by,
            "reviewed_by": r.reviewed_by,
            "review_note": r.review_note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "executed_at": r.executed_at.isoformat() if r.executed_at else None,
        }
        for r in rows
    ]


@router.post("/approvals/{request_id}/decide")
def decide(
    request_id: str,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("controller")),
) -> dict:
    try:
        req = approval_service.decide_approval(
            db,
            request_id=request_id,
            decision=body.decision,
            reviewed_by=body.reviewed_by or principal.name,
            review_note=body.review_note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "request_id": req.request_id,
        "status": req.status,
        "payload": req.payload,
        "reviewed_by": req.reviewed_by,
        "requires_second_approval": req.requires_second_approval,
        "first_approver": req.first_approver,
        "second_approver": req.second_approver,
        "executed_at": req.executed_at.isoformat() if req.executed_at else None,
    }


@router.post("/imports/real-public")
def import_real(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> dict:
    try:
        result = import_real_public_data(db)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"status": "ok", "imported_by": principal.name, **result}


@router.post("/imports/customer-erp")
def import_customer_erp(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> dict:
    """Load the bundled Meridian Robotics ERP CSV extract (customer-shaped demo)."""
    try:
        result = import_customer_erp_data(db)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok", "imported_by": principal.name, **result}


@router.post("/imports/csv")
async def import_csv_upload(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("admin")),
) -> dict:
    """Upload one or more customer CSVs (vendors / invoices / bank / GL).

    Filename heuristics: include `vendor`, `invoice`/`ap`/`bill`, `bank`, or `gl`/`journal`.
    """
    if not files:
        raise HTTPException(400, "Upload at least one CSV file")
    parsed: list[tuple[str, str]] = []
    for upload in files:
        name = upload.filename or "upload.csv"
        if not name.lower().endswith(".csv"):
            raise HTTPException(400, f"Only CSV uploads supported (got {name})")
        raw = await upload.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(400, f"Could not decode {name} as UTF-8") from exc
        parsed.append((name, text))
    try:
        bundle = parse_upload_bundle(parsed, source="csv_upload")
        result = apply_adapter_result(db, bundle)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok", "imported_by": principal.name, **result}


@router.get("/imports")
def list_imports(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(ImportBatch).order_by(desc(ImportBatch.created_at)).limit(50)).scalars().all()
    return [
        {
            "batch_id": r.batch_id,
            "source": r.source,
            "description": r.description,
            "record_count": r.record_count,
            "details": r.details,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/audit/chain/verify")
def audit_chain_verify(db: Session = Depends(get_db)) -> dict:
    return verify_audit_chain(db)


@router.get("/audit/{workflow_id}")
def audit(workflow_id: str, db: Session = Depends(get_db)) -> list[dict]:
    rows = (
        db.execute(select(AuditLog).where(AuditLog.workflow_id == workflow_id).order_by(AuditLog.created_at))
        .scalars()
        .all()
    )
    return [
        {
            "id": a.id,
            "event_type": a.event_type,
            "actor": a.actor,
            "message": a.message,
            "details": a.details,
            "duration_ms": a.duration_ms,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    from app.models import Account, JournalEntry, Vendor

    return {
        "vendors": db.query(Vendor).count(),
        "invoices": db.query(Invoice).count(),
        "bank_transactions": db.query(BankTransaction).count(),
        "journal_entries": db.query(JournalEntry).count(),
        "accounts": db.query(Account).count(),
        "documents": db.query(Document).count(),
        "workflows": db.query(WorkflowRun).count(),
        "pending_approvals": db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending").count(),
    }
