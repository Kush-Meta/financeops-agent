"""Pydantic API schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=4000)
    actor: str = "user"
    auto_propose_actions: bool = True


class ApprovalDecision(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    reviewed_by: str = "controller"
    review_note: str = ""


class ReconcileRequest(BaseModel):
    period: str = "2024-08"
    bank_account_code: str = "1000"
    persist: bool = True


class AnomalyRequest(BaseModel):
    period: str = "2024-08"
    persist_flags: bool = False


class WorkflowSummary(BaseModel):
    workflow_id: str
    status: str
    user_request: str
    answer: Optional[str] = None
    requires_approval: bool = False
    approval_request_id: Optional[str] = None
    latency_ms: Optional[float] = None
    created_at: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
