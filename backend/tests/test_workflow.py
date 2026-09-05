"""Agent workflow integration tests."""

from __future__ import annotations

import pytest

from app.agent.planner import deterministic_plan
from app.agent.workflow import run_investigation
from app.core.database import Base, SessionLocal, engine
from app.scripts.seed import seed
from app.services.approvals import decide_approval, list_approvals


@pytest.fixture(scope="module")
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed(session)
    yield session
    session.close()


def test_planner_maps_bank_gap_to_reconciliation():
    plan = deterministic_plan("Why is the bank account higher than the ledger in August 2024?")
    assert plan["intent"] == "reconciliation"
    tools = [s.get("tool") for s in plan.get("steps", [])]
    assert any(t and "reconcile" in t for t in tools)
    assert plan.get("period") == "2024-08"


def test_workflow_explains_gap_and_proposes_approval(db):
    result = run_investigation(
        db,
        "Why is the August bank account $82,000 higher than the ledger?",
        auto_propose_actions=True,
    )
    assert result["status"] == "completed"
    assert any("reconcile" in t for t in result["tools_used"])
    answer = result["answer"]
    assert "45,000" in answer or "45000" in answer.replace(",", "")
    assert result["requires_approval"] is True
    assert result["verification"]["unsupported_claim_rate"] <= 0.25


def test_approval_execution(db):
    pending = list_approvals(db, status="pending")
    assert pending, "expected at least one pending approval from prior workflow"
    first = decide_approval(db, pending[0].request_id, decision="approved", reviewed_by="tester")
    if first.status == "awaiting_second_approval":
        req = decide_approval(
            db,
            pending[0].request_id,
            decision="approved",
            reviewed_by="controller-2",
        )
    else:
        req = first
    assert req.status in ("executed", "approved")


def test_real_public_import(db):
    from app.adapters.persist import import_real_public_data
    from app.models import BankTransaction, ImportBatch

    before_txns = db.query(BankTransaction).count()
    before_batches = db.query(ImportBatch).count()
    out = import_real_public_data(db)
    created = out.get("created") or {}
    assert sum(created.values()) >= 1
    assert db.query(ImportBatch).count() >= before_batches + 1
    assert db.query(BankTransaction).count() >= before_txns
