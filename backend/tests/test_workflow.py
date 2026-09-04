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
    plan = deterministic_plan("Why is the bank account $82,000 higher than the ledger in August?")
    assert plan["intent"] == "reconciliation"
    assert any(s["tool"] == "reconcile_transactions" for s in plan["steps"])


def test_workflow_explains_gap_and_proposes_approval(db):
    result = run_investigation(
        db,
        "Why is the August bank account $82,000 higher than the ledger?",
        auto_propose_actions=True,
    )
    assert result["status"] == "completed"
    assert "reconcile_transactions" in result["tools_used"]
    assert "45,000" in result["answer"] or "45000" in result["answer"].replace(",", "")
    assert result["requires_approval"] is True
    assert result["verification"]["unsupported_claim_rate"] <= 0.25


def test_approval_execution(db):
    pending = [a for a in list_approvals(db, status="pending")]
    assert pending, "expected at least one pending approval from prior workflow"
    req = decide_approval(db, pending[0].request_id, decision="approved", reviewed_by="tester")
    assert req.status in ("executed", "approved")
